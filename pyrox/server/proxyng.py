import socket

import tornado
import tornado.ioloop
import tornado.process

from .routing import RoundRobinRouter, PROTOCOL_HTTP, PROTOCOL_HTTPS

from pyrox.tstream.iostream import (SSLSocketIOHandler, SocketIOHandler,
                                    StreamClosedError)
from pyrox.tstream.tcpserver import TCPServer

from pyrox.log import get_logger
from pyrox.about import VERSION
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)
import traceback

_LOG = get_logger(__name__)


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


def _write_to_stream(stream, data, is_chunked, callback=None):
    if is_chunked:
        # Format and write this chunk
        chunk = bytearray()
        chunk.extend(hex(len(data))[2:])
        chunk.extend('\r\n')
        chunk.extend(data)
        chunk.extend('\r\n')
        stream.write(chunk, callback)
    else:
        stream.write(data, callback)


class AccumulationStream(object):

    def __init__(self):
        self.bytes = bytearray()

    def write(self, data):
        self.bytes.extend(data)

    def size(self):
        return len(self.bytes)


class ProxyHandler(ParserDelegate):
    """
    Common class for the stream handlers. This parent class manages the
    following:

    - Handling of header field names.
    - Tracking rejection of message sessions.
    """
    def __init__(self, filter_pl, http_msg):
        self._filter_pl = filter_pl
        self._http_msg = http_msg
        self._chunked = False
        self._last_header_field = None
        self._rejected = False

    def on_http_version(self, major, minor):
        self._http_msg.version = '{}.{}'.format(major, minor)

    def on_header_field(self, field):
        self._last_header_field = field

    def on_header_value(self, value):
        header = self._http_msg.header(self._last_header_field)
        header.values.append(value)
        self._last_header_field = None


class DownstreamHandler(ProxyHandler):
    """
    This proxy handler manages data coming from downstream of the proxy.
    This data comes from the client initiating the request against the
    proxy.
    """

    def __init__(self, downstream, filter_pl, connect_upstream):
        super(DownstreamHandler, self).__init__(filter_pl, HttpRequest())
        self._downstream = downstream
        self._upstream = None
        self._preread_body = None
        self._connect_upstream = connect_upstream

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
        action = self._filter_pl.on_request_head(self._http_msg)

        # If we are intercepting the request body do some negotiation
        if self._filter_pl.intercepts_req_body():
            self._chunked = True

            # If there's a content length, negotiate the tansfer encoding
            if self._http_msg.get_header('content-length'):
                self._http_msg.remove_header('content-length')
                self._http_msg.remove_header('transfer-encoding')

                self._http_msg.header('transfer-encoding').values.append('chunked')

        # If we're rejecting then we're not going to connect to upstream
        if action.is_rejecting():
            self._rejected = True
            self._response = action.payload
        else:
            # Hold up on the client side until we're done negotiating
            # connections.
            self._downstream.handle.disable_reading()

            # We're routing to upstream; we need to know where to go
            if action.is_routing():
                self._connect_upstream(self._http_msg, action.payload)
            else:
                self._connect_upstream(self._http_msg)

    def on_body(self, bytes, length, is_chunked):
        self._chunked = is_chunked

        if self._downstream.reading():
            # Hold up on the client side until we're done with this chunk
            self._downstream.handle.disable_reading()

        # Rejections simply discard the body
        if not self._rejected:
            accumulator = AccumulationStream()
            data = bytes

            self._filter_pl.on_request_body(data, accumulator)

            if accumulator.size() > 0:
                data = accumulator.bytes

            if self._upstream:
                # When we write to the stream set the callback to resume
                # reading from downstream.
                _write_to_stream(self._upstream, data, is_chunked,
                                 self._downstream.handle.resume_reading)
            else:
                # If we're not connected upstream, store the fragment
                # for later
                self._store_chunk(data)

    def on_upstream_connect(self, upstream):
        self._upstream = upstream

        if self._preread_body and len(self._preread_body) > 0:
            _write_to_stream(self._upstream, self._preread_body,
                             self._chunked,
                             self._downstream.handle.resume_reading)
            self._preread_body = None

    def on_message_complete(self, is_chunked, keep_alive):
        # Enable reading when we're ready later
        self._downstream.handle.disable_reading()

        if keep_alive:
            self._http_msg = HttpRequest()

        if self._rejected:
            self._downstream.write(self._response.to_bytes())
        elif is_chunked or self._chunked:
            # Finish the last chunk.
            self._upstream.write(_CHUNK_CLOSE)


class UpstreamHandler(ProxyHandler):
    """
    This proxy handler manages data coming from upstream of the proxy. This
    data usually comes from the origin service or it may come from another
    proxy.
    """

    def __init__(self, downstream, upstream, filter_pl):
        super(UpstreamHandler, self).__init__(filter_pl, HttpResponse())
        self._downstream = downstream
        self._upstream = upstream

    def on_status(self, status_code):
        self._http_msg.status = str(status_code)

    def on_headers_complete(self):
        action = self._filter_pl.on_response_head(self._http_msg)

        # If we are intercepting the response body do some negotiation
        if self._filter_pl.intercepts_resp_body():

            # If there's a content length, negotiate the tansfer encoding
            if self._http_msg.get_header('content-length'):
                self._chunked = True
                self._http_msg.remove_header('content-length')
                self._http_msg.remove_header('transfer-encoding')

                self._http_msg.header('transfer-encoding').values.append('chunked')

        if action.is_rejecting():
            self._rejected = True
            self._response = action.payload
        else:
            self._downstream.write(self._http_msg.to_bytes())

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if not self._rejected:
            accumulator = AccumulationStream()
            data = bytes

            self._filter_pl.on_response_body(data, accumulator)

            if accumulator.size() > 0:
                data = accumulator.bytes

            # Hold up on the upstream side until we're done sending this chunk
            self._upstream.handle.disable_reading()

            # When we write to the stream set the callback to resume
            # reading from upstream.
            _write_to_stream(
                self._downstream,
                data,
                is_chunked or self._chunked,
                self._upstream.handle.resume_reading)

    def on_message_complete(self, is_chunked, keep_alive):
        callback = self._upstream.close
        self._upstream.handle.disable_reading()

        if keep_alive:
            self._http_msg = HttpResponse()
            callback = self._downstream.handle.resume_reading

        if self._rejected:
            # Serialize our message to them
            self._downstream.write(self._http_msg.to_bytes(), callback)
        elif is_chunked or self._chunked:
            # Finish the last chunk.
            self._downstream.write(_CHUNK_CLOSE, callback)
        else:
            callback()


class ConnectionTracker(object):

    def __init__(self, on_stream_live, on_target_closed, on_target_error):
        self._streams = dict()
        self._target_in_use = None
        self._on_stream_live = on_stream_live
        self._on_target_closed = on_target_closed
        self._on_target_error = on_target_error

    def destroy(self):
        for stream in self._streams.values():
            if not stream.closed():
                stream.close()

    def connect(self, target):
        self._target_in_use = target
        live_stream = self._streams.get(target)

        if live_stream:
            # Make the cb ourselves since the socket's already connected
            self._on_stream_live(live_stream)
        else:
            self._new_connection(target)

    def _new_connection(self, target):
        host, port, protocol = target

        # Set up our upstream socket
        us_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)

        # Create and bind the IO Handler based on selected protocol
        if protocol == PROTOCOL_HTTP:
            live_stream = SocketIOHandler(us_sock)
        elif protocol == PROTOCOL_HTTPS:
            live_stream = SSLSocketIOHandler(us_sock)
        else:
            raise Exception('Unknown protocol: {}.'.format(protocol))

        # Store the stream reference for later use
        self._streams[target] = live_stream

        # Build and set the on_close callback
        def on_close():
            # Disable error cb on close
            live_stream.on_error(None)

            del self._streams[target]
            if self._target_in_use == target:
                self.destroy()
                self._on_target_closed()
        live_stream.on_close(on_close)

        # Build and set the on_error callback
        def on_error(error):
            # Dsiable close cb on error
            live_stream.on_close(None)

            if self._target_in_use == target:
                del self._streams[target]
                if self._target_in_use == target:
                    self.destroy()
                    self._on_target_error(error)
        live_stream.on_error(on_error)

        # Build and set the on_connect callback and then connect
        def on_connect():
            self._on_stream_live(live_stream)
        live_stream.connect((host, port), on_connect)


class ProxyConnection(object):
    """
    A proxy connection manages the lifecycle of the sockets opened during a
    proxied client request against Pyrox.
    """
    def __init__(self, us_filter_pl, ds_filter_pl, downstream, router):
        self._ds_filter_pl = ds_filter_pl
        self._us_filter_pl = us_filter_pl
        self._router = router
        self._upstream_parser = None
        self._upstream_tracker = ConnectionTracker(
            self._on_upstream_live,
            self._on_upstream_close,
            self._on_upstream_error)

        # Setup all of the wiring for downstream
        self._downstream = downstream
        self._downstream_handler = DownstreamHandler(
            self._downstream,
            self._ds_filter_pl,
            self._connect_upstream)
        self._downstream_parser = RequestParser(self._downstream_handler)
        self._downstream.on_close(self._on_downstream_close)
        self._downstream.read(self._on_downstream_read)

    def _connect_upstream(self, request, route=None):
        if route is not None:
            # This does some type checking for routes passed up via filter
            self._router.set_next(route)
        upstream_target = self._router.get_next()

        if upstream_target is None:
            self._downstream.write(_UPSTREAM_UNAVAILABLE.to_bytes(),
                self._downstream.handle.resume_reading)
            return

        # Hold downstream reads
        self._hold_downstream = True

        # Update the request to proxy upstream and store it
        request.replace_header('host').values.append(
            '{}:{}'.format(upstream_target[0], upstream_target[1]))
        self._request = request

        try:
            self._upstream_tracker.connect(upstream_target)
        except Exception as ex:
            _LOG.exception(ex)

    def _on_upstream_live(self, upstream):
        self._upstream_handler = UpstreamHandler(
            self._downstream,
            upstream,
            self._us_filter_pl)

        if self._upstream_parser:
            self._upstream_parser.destroy()
        self._upstream_parser = ResponseParser(self._upstream_handler)

        # Set the read callback
        upstream.read(self._on_upstream_read)

        # Send the proxied request object
        upstream.write(self._request.to_bytes())

        # Drop the ref to the proxied request head
        self._request = None

        # Set up our downstream handler
        self._downstream_handler.on_upstream_connect(upstream)

    def _on_downstream_close(self):
        self._upstream_tracker.destroy()
        self._downstream_parser.destroy()
        self._downstream_parser = None

    def _on_downstream_error(self, error):
        _LOG.error('Downstream error: {}'.format(error))
        if not self._downstream.closed():
            self._downstream.close()

    def _on_upstream_error(self, error):
        if not self._downstream.closed():
            self._downstream.write(_BAD_GATEWAY_RESP.to_bytes())

    def _on_upstream_close(self):
        if not self._downstream.closed():
            self._downstream.close()

        if self._upstream_parser is not None:
            self._upstream_parser.destroy()
            self._upstream_parser = None

    def _on_downstream_read(self, data):
        try:
            self._downstream_parser.execute(data)
        except StreamClosedError:
            pass
        except Exception as ex:
            _LOG.exception(ex)

    def _on_upstream_read(self, data):
        try:
            self._upstream_parser.execute(data)
        except StreamClosedError:
            pass
        except Exception as ex:
            _LOG.exception(ex)


class TornadoHttpProxy(TCPServer):
    """
    Subclass of the Tornado TCPServer that lets us set up the Pyrox proxy
    orchestrations.

    :param pipelines: This is a tuple with the upstream filter pipeline factory
                      as the first element and the downstream filter pipeline
                      factory as the second element.
    """
    def __init__(self, pipeline_factories, default_us_targets=None,
                 ssl_options=None):
        super(TornadoHttpProxy, self).__init__(ssl_options=ssl_options)
        self._router = RoundRobinRouter(default_us_targets)
        self.us_pipeline_factory = pipeline_factories[0]
        self.ds_pipeline_factory = pipeline_factories[1]

    def handle_stream(self, downstream, address):
        connection_handler = ProxyConnection(
            self.us_pipeline_factory(),
            self.ds_pipeline_factory(),
            downstream,
            self._router)
