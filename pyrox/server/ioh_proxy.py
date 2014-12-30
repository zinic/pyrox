import copy
import threading
import collections
import errno
import socket
import ssl
import traceback

import pyrox.iohandling as ioh
import pyrox.server.routing as routing

from pyrox.server.routing import RoundRobinRouter, PROTOCOL_HTTP, PROTOCOL_HTTPS

from tornado import ioloop
from tornado.netutil import bind_sockets

from pyrox.about import VERSION
from pyrox.log import get_logger
from pyrox.filtering import HttpFilterPipeline
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)


_LOG = get_logger(__name__)

_DOWNSTREAM = True
_UPSTREAM = False

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


class ParserDelegate(object):

    def on_status(self, status_code):
        pass

    def on_req_method(self, method):
        pass

    def on_http_version(self, major, minor):
        pass

    def on_req_path(self, url):
        pass

    def on_header_field(self, field):
        pass

    def on_header_value(self, value):
        pass

    def on_headers_complete(self):
        pass

    def on_body(self, bytes, length, is_chunked):
        pass

    def on_message_complete(self, is_chunked, should_keep_alive):
        pass


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

    def __init__(self, client_channel, filters, connect_upstream):
        super(DownstreamHandler, self).__init__(filters, HttpRequest())

        self.stream_handle = None

        self._connect_upstream = connect_upstream
        self._client_channel = client_channel

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
        # Plug future reads
        self.stream_handle.plug_reads()

        # Execute against the pipeline
        action = self._filters.on_request_head(self._http_msg)

        # If we are intercepting the request body do some negotiation
        if self._filters.intercepts_req_body():
            self._chunked = True

            # If there's a content length, negotiate the tansfer encoding
            if self._http_msg.get_header(_CONTENT_LENGTH):
                self._http_msg.remove_header(_CONTENT_LENGTH)
                self._http_msg.remove_header(_TRANSFER_ENCODING)

                self._http_msg.header(_TRANSFER_ENCODING).values.append(_CHUNKED_ENCODING)

        if action.intercepts_request():
            # If we're replying right away then we're not going to connect to upstream
            self._intercepted = True
            self._response_tuple = action.payload
        else:
            # Initiate upstream connection management
            if action.is_routing():
                self._connect_upstream(
                    self._client_channel, self.on_upstream_connect, action.payload)
            else:
                self._connect_upstream(
                    self._client_channel, self.on_upstream_connect)

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
            _write_to_stream(self.stream_handle.partner_channel, data, is_chunked)

            # When we write to the stream set the callback to resume
            # reading from downstream.
            self.stream_handle.resume_reads()
        else:
            # If we're not connected upstream, store the fragment
            # for later
            self._store_chunk(data)

    def on_upstream_connect(self, upstream):
        # Set the partner channel
        self.stream_handle.partner_channel = upstream

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
            # Save a reference to the stream handle for ease of use
            _, upstream_handle = upstream.related

            # If the message is complete, we want to resume reads after the
            # head and any stored body content are sent
            upstream_handle.resume_reads()

    def on_message_complete(self, is_chunked, keep_alive):
        # Enable reading when we're ready later
        self.stream_handle.plug_reads()

        # Mark that we're complete
        self._message_complete = True

        if self._intercepted:
            self._client_channel.send(self._response_tuple[0].to_bytes())

            if keep_alive:
                # Resume client reads if this is a keep-alive request
                self.stream_handle.resume_reads()

        elif is_chunked or self._chunked:
            if self.stream_handle.partner_connected():
                # Send the last chunk
                self.stream_handle.partner_channel.send(_CHUNK_CLOSE)

                # Enable reads to wait for the upstream response
                self.stream_handle.resume_partner_reads()
            else:
                # If we're not connected upstream, store the fragment
                self._store_chunk(_CHUNK_CLOSE)
        elif self.stream_handle.partner_connected():
            # Enable reads right away if we're done writing and we're already
            # connected with upstream
            _, upstream_handle = self.stream_handle.partner_channel.related

            # If the message is complete, we want to resume reads after the
            # head and any stored body content are sent
            upstream_handle.resume_reads()


class UpstreamHandler(StreamHandler):
    """
    This proxy handler manages data coming from upstream of the proxy. This
    data usually comes from the origin service or it may come from another
    proxy.
    """

    def __init__(self, client_channel, filters):
        super(UpstreamHandler, self).__init__(filters, HttpResponse())
        self._client_channel = client_channel
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
            self._client_channel.send(self._http_msg.to_bytes())

            # If we're streaming a response downstream , we need to make sure
            # that we resume our reads from upstream
            _, client_stream_handle = self._client_channel.related
            client_stream_handle.resume_partner_reads()

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
            self._client_channel,
            data,
            is_chunked or self._chunked)

        # Resume reads when the chunk is done
        _, client_stream_handle = self._client_channel.related
        client_stream_handle.resume_partner_reads()

    def on_message_complete(self, is_chunked, keep_alive):
        # This is the last bit of data so unpack our stream handle for use
        _, client_stream_handle = self._client_channel.related

        # Hold up on the upstream side from further reads
        client_stream_handle.plug_partner_reads()

        if self._intercepted:
            # Serialize our message to them
            self._client_channel.send(self._http_msg.to_bytes())
        elif is_chunked or self._chunked:
            # Finish the last chunk.
            self._client_channel.send(_CHUNK_CLOSE)

        if keep_alive:
            self._http_msg = HttpResponse()

            # If we're told to keep this connection alive then we can expect
            # data from the client
            client_stream_handle.resume_reads()


class StreamHandle(object):

    def __init__(self, stream_type, parser, origin_channel, partner_channel=None):
        self.partner_channel = partner_channel
        self.origin_channel = origin_channel
        self.stream_type = stream_type
        self.parser = parser

        self._enable_partner_reads = False
        self._enable_reads = False

    def plug_reads(self):
        self._enable_reads = False

        if self.origin_channel.reads_enabled():
            self.origin_channel.disable_reads()

    def plug_partner_reads(self):
        self._enable_partner_reads = False

        if self.partner_channel.reads_enabled():
            self.partner_channel.disable_reads()

    def resume_reads(self):
        self._enable_reads = True

    def resume_partner_reads(self):
        self._enable_partner_reads = True

    def partner_connected(self):
        return self.partner_channel is not None

    def destroy(self):
        self.parser.destroy()

    def update(self):
        try:
            if self._enable_reads:
                self._enable_reads = False

                if not self.origin_channel.reads_enabled():
                    self.origin_channel.enable_reads()
        except Expcetion as ex:
            print('Exception on updating fileno: {}'.format(self.origin_channel.fileno))

        try:
            if self._enable_partner_reads:
                self._enable_partner_reads = False

                if not self.partner_channel.reads_enabled():
                    self.partner_channel.enable_reads()
        except Expcetion as ex:
            print('Exception on updating fileno: {}'.format(self.partner_channel.fileno))


def kill_channel(channel, connection_tracker):
    # Clean up
    _, handle = channel.related
    handle.destroy()

    if handle.stream_type is _DOWNSTREAM and handle.partner_connected():
        # Grap a ref to upstream and unpack its route
        upstream = handle.partner_channel
        us_route, _ = upstream.related

        # Dump related info for this channel
        upstream.related = None

        # Check in the channel for reuse
        connection_tracker.check_in(upstream, us_route)


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

    def check_in(self, channel, route):
        upstream_channels = self._get(route)
        if len(upstream_channels) > 5:
            channel.close()
        else:
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

        # No channel? Create it
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
        upstream_handle = StreamHandle(_UPSTREAM, response_parser, upstream_channel, client_channel)
        handler.stream_handle = upstream_handle

        if already_connected:
            # Already connected, invoke the cb ourselves
            upstream_channel.related = (upstream_target, upstream_handle)
            on_connect_cb(upstream_channel)
        else:
            # Set up our related information for the async connect
            upstream_channel.related = (
                upstream_target,
                on_connect_cb,
                upstream_handle)

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
                ioh.SocketChannel.Create((us_host, us_port), socket.AF_INET))

            # Queue our connection attempt and then return the channel
            upstream_channel.connect()
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
            channel,
            self._ds_filters_factory(),
            self._connection_tracker.connect)
        request_parser = RequestParser(handler)

        # Link back to make sure upstream gets populated correctly
        stream_handle = StreamHandle(_DOWNSTREAM, request_parser, channel)
        handler.stream_handle = stream_handle

        # Set related info
        channel.related = (None, stream_handle)

    def on_close(self, channel):
        kill_channel(channel, self._connection_tracker)

    def on_error(self, channel):
        kill_channel(channel, self._connection_tracker)

    def on_connect(self, channel):
        # Trim related items since we don't need the request anymore
        route, on_connect_cb, stream_handle = channel.related

        # Reset our related information
        channel.related = (route, stream_handle)

        # Let our downstream handler know where to stream the body
        on_connect_cb(channel)

    def on_read(self, channel, data):
        _, stream_handle = channel.related
        stream_handle.parser.execute(data)

    def on_send_complete(self, channel):
        _, stream_handle = channel.related
        stream_handle.update()


class SocketChannelServer(object):

    def __init__(self, channel_evrouter, io_loop=None, default_us_targets=None, ssl_options=None):
        self._ce_router = channel_evrouter
        self._ssl_options = ssl_options
        self._io_loop = io_loop or ioloop.IOLoop.current()

    def start(self):
        self._io_loop.start()

    def listen(self, family, address):
        new_channel = ioh.SocketChannel.Listen(
            address=address,
            family=family,
            io_loop=self._io_loop)

        # Watch the channel and enable reading from it
        self._ce_router.register(new_channel)
        new_channel.enable_reads()


def new_pipeline():
    return HttpFilterPipeline()


cer = ioh.ChannelEventRouter()
cer.set_event_handler(ConnectionDriver(new_pipeline, new_pipeline, RoundRobinRouter(['http://google.com'])))

cs = SocketChannelServer(cer)
cs.listen(socket.AF_INET, ('0.0.0.0', 8080))
cs.start()
