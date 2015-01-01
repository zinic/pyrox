import copy
import threading
import collections
import errno
import socket
import ssl
import traceback

import pyrox.iohandling as ioh

from tornado import ioloop
from tornado.netutil import bind_sockets

from pyrox.about import VERSION
from pyrox.log import get_logger
from pyrox.filtering import HttpFilterPipeline
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)


_LOG = get_logger(__name__)

_CONTENT_LENGTH = 'content-length'
_TRANSFER_ENCODING = 'transfer-encoding'
_CHUNKED_ENCODING = 'chunked'

"""
String representing a 0 length HTTP chunked encoding chunk.
"""
_CHUNK_CLOSE = b'0\r\n\r\n'


"""
Default return object on error. This should be configurable.
"""
_BAD_GATEWAY_RESP = HttpResponse()
_BAD_GATEWAY_RESP.version = b'1.1'
_BAD_GATEWAY_RESP.status = '502 Bad Gateway'
_BAD_GATEWAY_RESP.header('Server').values.append('pyrox/{}'.format(VERSION))
_BAD_GATEWAY_RESP.header('Content-Length').values.append('0')

"""
Default return object on no route or upstream not responding. This should
be configurable.
"""
_UPSTREAM_UNAVAILABLE = HttpResponse()
_UPSTREAM_UNAVAILABLE.version = b'1.1'
_UPSTREAM_UNAVAILABLE.status = '503 Service Unavailable'
_UPSTREAM_UNAVAILABLE.header('Server').values.append('pyrox/{}'.format(VERSION))
_UPSTREAM_UNAVAILABLE.header('Content-Length').values.append('0')


def _write_to_stream(stream, data, is_chunked):
    if is_chunked:
        # Format and write this chunk
        chunk = bytearray()
        chunk.extend(hex(len(data))[2:])
        chunk.extend('\r\n')
        chunk.extend(data)
        chunk.extend('\r\n')
        stream.send(chunk)
    else:
        stream.send(data)


class AccumulationStream(object):

    def __init__(self):
        self.bytes = bytearray()

    def send(self, data):
        self.bytes.extend(data)

    def size(self):
        return len(self.bytes)


class StreamHandler(ParserDelegate):
    """
    Common class for the stream handlers. This parent class manages the
    following:

    - Handling of header field names.
    - Tracking rejection of message sessions.
    """
    def __init__(self, filters, http_msg):
        # Refs to our filter pipeline and the message we're building
        self._filters = filters
        self._http_msg = http_msg

        # State management
        self._chunked = False
        self._last_header_field = None
        self._intercepted = False

    def on_http_version(self, major, minor):
        self._http_msg.version = '{}.{}'.format(major, minor)

    def on_header_field(self, field):
        self._last_header_field = field

    def on_header_value(self, value):
        header = self._http_msg.header(self._last_header_field)
        header.values.append(value)


class DownstreamHandler(StreamHandler):

    def __init__(self, filters, connect_upstream):
        super(DownstreamHandler, self).__init__(filters, HttpRequest())

        self.stream_handle = None

        self._connect_upstream = connect_upstream
        self._message_complete = False
        self._preread_body = bytearray()

    def _store_chunk(self, body_fragment):
        self._preread_body.extend(body_fragment)

    def on_req_method(self, method):
        # Req method means a new message
        self._message_complete = False

        # Store the method
        self._http_msg.method = method

    def on_req_path(self, url):
        self._http_msg.url = url

    def on_headers_complete(self):
        # Execute against the pipeline
        action = self._filters.on_request_head(self._http_msg)

        # If we are intercepting the request body do some negotiation
        if self._filters.intercepts_req_body():
            self._chunked = True

            # If there's a content length, negotiate the tansfer encoding
            if self._http_msg.get_header(_CONTENT_LENGTH):
                self._http_msg.remove_header(_CONTENT_LENGTH)
                self._http_msg.remove_header(_TRANSFER_ENCODING)

                self._http_msg.header(_TRANSFER_ENCODING).values.append(
                    _CHUNKED_ENCODING)

        if action.intercepts_request():
            # If we're replying right away then we're not going to connect to
            # upstream so there's no reason to stop reading from the client
            self._intercepted = True
            self._response_tuple = action.payload
        else:
            # Plug future reads for now
            self.stream_handle.plug_reads()

            # Initiate upstream connection management
            if action.is_routing():
                self._connect_upstream(
                    self.stream_handle,
                    self.on_upstream_connect,
                    action.payload)
            else:
                self._connect_upstream(
                    self.stream_handle,
                    self.on_upstream_connect)

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if self._intercepted:
            return

        # Plug our reads
        self.stream_handle.plug_reads()

        # Remember if we're chunked or not
        self._chunked = is_chunked

        accumulator = AccumulationStream()
        data = bytes

        self._filter_pl.on_request_body(data, accumulator)

        if accumulator.size() > 0:
            data = accumulator.bytes

        if self.stream_handle.partner_connected():
            _write_to_stream(self.stream_handle.partner, data, is_chunked)

            # When we write to the stream set the callback to resume
            # reading from downstream.
            self.stream_handle.resume_reads()
        else:
            # If we're not connected upstream, store the fragment
            # for later
            self._store_chunk(data)

    def on_upstream_connect(self, upstream):
        # Set the partner channel
        join_handles(self.stream_handle, upstream)

        # Send the request head
        upstream.send(self._http_msg.to_bytes())

        # Clean up our message object
        # TODO: Find a way to optimize this without object creatoin
        self._http_msg = HttpRequest()

        # Queue up any body fragments we read that fit in our buffer
        if self._preread_body is not None and len(self._preread_body) > 0:
            _write_to_stream(upstream, self._preread_body, self._chunked)
            self._preread_body = None

        if self._message_complete is True:
            # If the message is complete, we want to resume reads after the
            # head and any stored body content are sent
            upstream.resume_reads()

    def on_message_complete(self, is_chunked, keep_alive):
        # Enable reading when we're ready later
        self.stream_handle.plug_reads()

        # Mark that we're complete
        self._message_complete = True

        if self._intercepted:
            self.stream_handle.send(self._response_tuple[0].to_bytes())

            if keep_alive:
                # Resume client reads if this is a keep-alive request
                self.stream_handle.resume_reads()

        elif is_chunked or self._chunked:
            if self.stream_handle.partner_connected():
                # Send the last chunk
                self.stream_handle.partner_channel.send(_CHUNK_CLOSE)

                # Enable reads to wait for the upstream response
                self.stream_handle.partner.resume_reads()
            else:
                # If we're not connected upstream, store the fragment
                self._store_chunk(_CHUNK_CLOSE)
        elif self.stream_handle.partner_connected():
            # Enable reads right away if we're done writing and we're already
            # connected with upstream
            self.stream_handle.partner.resume_reads()


class UpstreamHandler(StreamHandler):
    """
    This proxy handler manages data coming from upstream of the proxy. This
    data usually comes from the origin service or it may come from another
    proxy.
    """

    def __init__(self, client_handle, filters):
        super(UpstreamHandler, self).__init__(filters, HttpResponse())
        self._client_handle = client_handle
        self.stream_handle = None

    def on_status(self, status_code):
        self._http_msg.status = str(status_code)

    def on_headers_complete(self):
        # Hold up on the upstream side until we're done sending this chunk
        self.stream_handle.plug_reads()

        # Execute against the pipeline
        action = self._filters.on_response_head(self._http_msg)

        # If we are intercepting the response body do some negotiation
        if self._filters.intercepts_resp_body():

            # If there's a content length, negotiate the tansfer encoding
            if self._http_msg.get_header(_CONTENT_LENGTH):
                self._chunked = True
                self._http_msg.remove_header(_CONTENT_LENGTH)
                self._http_msg.remove_header(_TRANSFER_ENCODING)

                self._http_msg.header(_TRANSFER_ENCODING).values.append(_CHUNKED_ENCODING)

        if action.is_replying():
            # We're taking over the response ourselves
            self._intercepted = True
            self._response_tuple = action.payload

        else:
            # Stream the response object
            self._client_handle.send(self._http_msg.to_bytes())

            # If we're streaming a response downstream , we need to make sure
            # that we resume our reads from upstream
            self._client_handle.partner.resume_reads()

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if self._intercepted:
            return

        # Hold up on the upstream side until we're done sending this chunk
        self.stream_handle.plug_reads()

        accumulator = AccumulationStream()
        data = bytes

        self._filters.on_response_body(data, accumulator.bytes)

        if accumulator.size() > 0:
            data = accumulator.bytes

        # Write the chunk
        _write_to_stream(
            self._client_handle,
            data,
            is_chunked or self._chunked)

        # Resume reads when the chunk is done
        self.stream_handle.resume_reads()

    def on_message_complete(self, is_chunked, keep_alive):
        # Hold up on the upstream side from further reads
        self._client_handle.partner.plug_reads()

        if self._intercepted:
            # Serialize our message to them
            self._client_handle.send(self._http_msg.to_bytes())
        elif is_chunked or self._chunked:
            # Finish the last chunk.
            self._client_handle.send(_CHUNK_CLOSE)

        if keep_alive:
            self._http_msg = HttpResponse()

            # If we're told to keep this connection alive then we can expect
            # data from the client
            self._client_handle.resume_reads()


def join_handles(downstream_handle, upstream_handle):
    downstream_handle._partner_channel = upstream_handle._origin_channel
    upstream_handle._partner_channel = downstream_handle._origin_channel


class StreamHandle(object):

    def __init__(self, origin_channel, parser, partner_channel=None):
        self._partner_channel = partner_channel
        self._origin_channel = origin_channel
        self.parser = parser
        self.route = None

        # State management
        self._enable_reads = False

    def partner_connected(self):
        return self._partner_channel is not None

    @property
    def channel(self):
        return self._origin_channel

    @property
    def partner(self):
        return self._partner_channel.related if self.partner_connected() else None

    def plug_reads(self):
        self._enable_reads = False

        if self._origin_channel.reads_enabled():
            self._origin_channel.disable_reads()

    def resume_reads(self):
        self._enable_reads = True

    def send(self, data):
        self._origin_channel.send(data)

    def destroy(self):
        # Deref our partner
        self._partner_channel = None

        # Free the parser
        self.parser.destroy()

    def _update(self):
        try:
            if self._enable_reads:
                self._enable_reads = False

                if not self._origin_channel.reads_enabled():
                    self._origin_channel.enable_reads()
        except Expcetion as ex:
            _LOG.error('Exception on updating fileno: {}'.format(
                self._origin_channel.fileno))

    def update(self):
        # Update ourselves first
        self._update()

        # If we have a partner that needs state changes, let's execute them
        # as well
        if self.partner_connected():
            self.partner._update()

    def is_upstream(self):
        raise NotImplementedError()


class UpstreamHandle(StreamHandle):

    def is_upstream(self):
        return True


class DownstreamHandle(StreamHandle):

    def is_upstream(self):
        return False


def kill_channel(channel, connection_tracker):
    # Grab this channel's handle
    handle = channel.related

    # Is this a downstream (client) connection? If so, does it have an active
    # upstream connection we might be able to reuse?
    if not handle.is_upstream() and handle.partner_connected():
        # Check in the channel for reuse
        connection_tracker.check_in(handle.partner)
    else:
        # Retrie the upstream channel if we no longer need it
        connection_tracker.retire(handle)

    # Clean up
    handle.destroy()

class ConnectionTracker(object):

    def __init__(self, ce_router, dest_router, us_filters_factory):
        self._channels = dict()
        self._ce_router = ce_router
        self._dest_router = dest_router
        self._us_filters_factory = us_filters_factory

    def destroy(self):
        for channels in self._channels.values():
            for channel in channels:
                if not channel.closed():
                    channel.close()

    def retire(self, handle):
        # Grab the channel ref
        channel = handle.channel

        _LOG.info('Retiring: {}'.format(channel.fileno))

        # Look up the current channels that have been kept alive
        upstream_channels = self._get(handle.route)

        for idx in range(0, len(upstream_channels)):
            if upstream_channels[idx].fileno == channel.fileno:
                del upstream_channels[idx]
                break

    def check_in(self, handle):
        # Grab the channel ref
        channel = handle.channel

        _LOG.info('Checking in: {}'.format(channel.fileno))

        # Look up the current channels that have been kept alive
        upstream_channels = self._get(handle.route)

        # TODO: Make the max number of upstream connections held open
        # configurable
        if len(upstream_channels) > 5:
            # Close right away if we don't need to keep this channel around
            channel.close()
        else:
            # We enable reads in case upstream decides to close on us
            channel.enable_reads()

            # Make this channel available for reuse
            upstream_channels.append(channel)

    def connect(self, client_channel, on_connect_cb, route=None):
        # This does some type checking for routes passed up via filter
        if route is not None:
            self._dest_router.set_next(route)

        # Where is this request going?
        upstream_target = self._dest_router.get_next()

        if upstream_target is None:
            client_channel.send(_UPSTREAM_UNAVAILABLE.to_bytes())
            return

        # Lets see if we can get a live channel
        upstream_channels = self._get(upstream_target)
        already_connected = False
        upstream_channel = None

        if len(upstream_channels) > 0:
            upstream_channel = upstream_channels.pop()
            already_connected = True
        else:
            upstream_channel = self._open(upstream_target)

        # Create the handler
        handler = UpstreamHandler(
                client_channel,
                self._us_filters_factory())

        # Create a response parser instance
        response_parser = ResponseParser(handler)

        # Create a handle and then bind it to the handler
        upstream_handle = UpstreamHandle(upstream_channel, response_parser, client_channel)
        upstream_handle.route = upstream_target

        handler.stream_handle = upstream_handle

        if already_connected:
            _LOG.info('Viable upstream connection available. Resuing: {}'.format(upstream_channel.fileno))

            # Kill reads
            if upstream_channel.reads_enabled():
                upstream_channel.disable_reads()

            # Already connected, invoke the cb ourselves
            upstream_channel.related = upstream_handle
            on_connect_cb(upstream_handle)
        else:
            _LOG.info('No viable upstream connections available. Created: {}'.format(upstream_channel.fileno))

            # Set up our related information for the async connect
            upstream_channel.related = (on_connect_cb, upstream_handle)

    def _get(self, route):
        available = self._channels.get(route)

        # If there's no available list for this route, create it
        if available is None:
            available = list()
            self._channels[route] = available

        return available

    def _open(self, route):
        # Let's alias some things
        us_host, us_port = route[:2]

        try:
            # Create the channel and register it
            upstream_channel = self._ce_router.register(
                ioh.SocketChannel.Create(socket.AF_INET))

            # Queue our connection attempt and then return the channel
            upstream_channel.connect((us_host, us_port))
            return upstream_channel
        except Exception as ex:
            _LOG.exception(ex)


class ConnectionDriver(ioh.ChannelEventHandler):

    def __init__(self, ds_filters_factory, us_filters_factory, dest_router):
        self._connection_tracker = None
        self._ce_router = None

        self._ds_filters_factory = ds_filters_factory
        self._us_filters_factory = us_filters_factory
        self._dest_router = dest_router

    def init(self, ce_router):
        self._ce_router = ce_router
        self._connection_tracker = ConnectionTracker(
            ce_router, self._dest_router, self._us_filters_factory)

    def on_accept(self, channel):
        # Pull data and see what the client wants
        channel.enable_reads()

        # Init the handler and parser - these guys go hand in hand
        handler = DownstreamHandler(
            self._ds_filters_factory(),
            self._connection_tracker.connect)
        request_parser = RequestParser(handler)

        # Link back to make sure upstream gets populated correctly
        stream_handle = DownstreamHandle(channel, request_parser)
        handler.stream_handle = stream_handle

        # Set related info
        channel.related = stream_handle

    def on_close(self, channel):
        kill_channel(channel, self._connection_tracker)

    def on_error(self, channel):
        kill_channel(channel, self._connection_tracker)

    def on_connect(self, channel):
        # Unpack our goodies
        on_connect_cb, stream_handle = channel.related

        # Trim related items since we don't need the cb anymore after this
        channel.related = stream_handle

        # Let our downstream handler know we're ready for content
        on_connect_cb(stream_handle)

    def on_read(self, channel, data):
        channel.related.parser.execute(data)

    def on_send_complete(self, channel):
        channel.related.update()
