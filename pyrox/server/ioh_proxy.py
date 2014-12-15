import copy
import threading
import collections
import errno
import socket
import ssl

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
        self._message_complete = False
        self._client_channel = client_channel
        self._preread_body = None

    def _store_chunk(self, body_fragment):
        if not self._preread_body:
            self._preread_body = bytearray()
        self._preread_body.extend(body_fragment)

    def on_req_method(self, method):
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
            if self._http_msg.get_header('content-length'):
                self._http_msg.remove_header('content-length')
                self._http_msg.remove_header('transfer-encoding')

                self._http_msg.header('transfer-encoding').values.append('chunked')

        # If we're replying right away then we're not going to connect to upstream
        if action.intercepts_request():
            self._intercepted = True
            self._response_tuple = action.payload
        else:
            # Since we're not replying right away, hold up on the client side
            # until we're done negotiating connections.
            self._client_channel.disable_reads()

            # We're routing to upstream; we need to know where to go
            if action.is_routing():
                self._connect_upstream(self, self._client_channel, self._http_msg, action.payload)
            else:
                self._connect_upstream(self, self._client_channel, self._http_msg)

    def on_body(self, bytes, length, is_chunked):
        self._chunked = is_chunked

        if self._client_channel.reading():
            # Hold up on the client side until we're done with this chunk
            self._client_channel.handle.disable_reads()

        # Rejections simply discard the body
        if not self._intercepted:
            accumulator = AccumulationStream()
            data = bytes

            self._filter_pl.on_request_body(data, accumulator)

            if accumulator.size() > 0:
                data = accumulator.bytes

            if self.stream_handle.partner_channel is not None:
                # When we write to the stream set the callback to resume
                # reading from downstream.
                _write_to_stream(self.stream_handle.partner_channel, data, is_chunked)
            else:
                # If we're not connected upstream, store the fragment
                # for later
                self._store_chunk(data)

    def on_upstream_connect(self, upstream):
        self.stream_handle.partner_channel = upstream

        if self._preread_body and len(self._preread_body) > 0:
            _write_to_stream(self.stream_handle.partner_channel, self._preread_body, self._chunked)
            self._preread_body = None

        # If the message is complete, start reading from upstream asap
        if self._message_complete:
            # Wait for a response
            upstream.enable_reads()

    def on_message_complete(self, is_chunked, keep_alive):
        self._message_complete = True

        # Enable reading when we're ready later
        self._client_channel.disable_reads()

        if keep_alive:
            self._http_msg = HttpRequest()

        if self._intercepted:
            self._client_channel.send(self._response_tuple[0].to_bytes())
        elif is_chunked or self._chunked:
            # Finish the last chunk and then wait for a response
            self.stream_handle.partner_channel.send(_CHUNK_CLOSE)


class UpstreamHandler(StreamHandler):
    """
    This proxy handler manages data coming from upstream of the proxy. This
    data usually comes from the origin service or it may come from another
    proxy.
    """

    def __init__(self, client_channel, upstream_channel, filters):
        super(UpstreamHandler, self).__init__(filters, HttpResponse())
        self._client_channel = client_channel
        self._upstream_channel = upstream_channel

    def on_status(self, status_code):
        self._http_msg.status = str(status_code)

    def on_headers_complete(self):
        action = self._filters.on_response_head(self._http_msg)

        # If we are intercepting the response body do some negotiation
        if self._filters.intercepts_resp_body():

            # If there's a content length, negotiate the tansfer encoding
            if self._http_msg.get_header('content-length'):
                self._chunked = True
                self._http_msg.remove_header('content-length')
                self._http_msg.remove_header('transfer-encoding')

                self._http_msg.header('transfer-encoding').values.append('chunked')

        if action.is_replying():
            self._intercepted = True
            self._response_tuple = action.payload
        else:
            self._upstream_channel.disable_reads()
            self._client_channel.send(self._http_msg.to_bytes())

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if not self._intercepted:
            accumulator = AccumulationStream()
            data = bytes

            self._filters.on_response_body(data, accumulator.bytes)

            if accumulator.size() > 0:
                data = accumulator.bytes

            # Hold up on the upstream side until we're done sending this chunk
            self._upstream_channel.disable_reads()

            # When we write to the stream set the callback to resume
            # reading from upstream.
            _write_to_stream(
                self._client_channel,
                data,
                is_chunked or self._chunked)

    def on_message_complete(self, is_chunked, keep_alive):
        self._upstream_channel.disable_reads()

        if self._intercepted:
            # Serialize our message to them
            self._client_channel.send(self._http_msg.to_bytes())
        elif is_chunked or self._chunked:
            # Finish the last chunk.
            self._client_channel.send(_CHUNK_CLOSE)

        if keep_alive:
            self._http_msg = HttpResponse()
            self._client_channel.enable_reads()
        else:
            self._upstream_channel.close()


class StreamHandle(object):

    def __init__(self, parser, partner_channel=None):
        self.partner_channel = partner_channel
        self.parser = parser


class ConnectionDriver(ioh.ChannelEventHandler):

    def __init__(self, ds_filters_factory, us_filters_factory, dest_router):
        self._ce_router = None

        self._ds_filters_factory = ds_filters_factory
        self._us_filters_factory = us_filters_factory
        self._dest_router = dest_router

    def init(self, ce_router):
        self._ce_router = ce_router

    def _connect_upstream(self, client_handler, client_channel, request, route=None):
        # This does some type checking for routes passed up via filter
        if route is not None:
            self._dest_router.set_next(route)

        # Where is this request going?
        upstream_target = self._dest_router.get_next()
        us_host, us_port = upstream_target[:2]

        # Are we going somewhere?
        if upstream_target is None:
            client_channel.send(_UPSTREAM_UNAVAILABLE.to_bytes())
            client_channel.enable_writes()
            return

        # Update the request to proxy upstream and store it
        host_header = request.replace_header('host')
        host_header.values.append('{}:{}'.format(us_host, us_port))

        try:
            # Connect upstream and register the socket
            upstream_channel = self._ce_router.register(
                ioh.SocketChannel.Connect((us_host, us_port), socket.AF_INET))

            # Enable writing
            upstream_channel.enable_writes()

            # Create a response parser instance
            response_parser = ResponseParser(
                UpstreamHandler(
                    client_channel,
                    upstream_channel,
                    self._us_filters_factory()))

            # Set up our related information
            upstream_channel.related = (
                client_handler,
                request,
                StreamHandle(response_parser, client_channel))
        except Exception as ex:
            _LOG.exception(ex)

    def on_accept(self, channel):
        # Pull data and see what the client wats
        channel.enable_reads()

        handler = DownstreamHandler(
            channel,
            self._ds_filters_factory(),
            self._connect_upstream)
        request_parser = RequestParser(handler)

        # Link back to make sure upstream gets populated correctly
        stream_handle = StreamHandle(request_parser)
        handler.stream_handle = stream_handle

        # Set related info
        channel.related = (_DOWNSTREAM, stream_handle)

    def on_close(self, channel):
        channel.related[1].parser.destroy()

    def on_error(self, channel):
        channel.related[1].parser.destroy()

    def on_connect(self, channel):
        # Trim related items since we don't need the request anymore
        client_handler, request, stream_handle = channel.related

        # Let our downstream handler know where to stream the body
        client_handler.on_upstream_connect(channel)

        # Set our related information
        channel.related = (_UPSTREAM, stream_handle)

        # Send the request head
        channel.send(request.to_bytes())

    def on_read(self, channel, data):
        channel.related[1].parser.execute(data)

    def on_send_complete(self, channel):
        if channel.related[0] is _DOWNSTREAM:
            channel.related[1].partner_channel.enable_reads()


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
cer.set_event_handler(ConnectionDriver(new_pipeline, new_pipeline, RoundRobinRouter(['http://localhost:8088'])))

cs = SocketChannelServer(cer)
cs.listen(socket.AF_INET, ('0.0.0.0', 8080))
cs.start()
