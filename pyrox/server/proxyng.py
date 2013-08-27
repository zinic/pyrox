import socket

import tornado
import tornado.ioloop
import tornado.process
import tornado.iostream as iostream
import tornado.tcpserver as tcpserver

from .routing import RoutingHandler
from pyrox.log import get_logger
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)

_LOG = get_logger(__name__)

# Read 1k at a time
_MAX_READ = 1024
_CHUNK_CLOSE = b'0\r\n\r\n'


def _write_to_stream(stream, bytes, is_chunked):
    if is_chunked:
        # Format and write this chunk
        chunk = bytearray()
        chunk.extend(hex(length)[2:])
        chunk.extend('\r\n')
        chunk.extend(bytes)
        chunk.extend('\r\n')
        stream.write(chunk)
    else:
        stream.write(bytes)


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
        self._body_fragment = None
        self._connect_upstream = connect_upstream

    def _store_body(self, body_fragment):
        if self._body_fragment:
            self._body_fragment.extend(body_fragment)
        else:
            self._body_fragment = body_fragment

    def _get_body(self, next_body_fragment):
        body_fragment = next_body_fragment
        if self._body_fragment:
            self._body_fragment.extend(body_fragment)
            body_fragment = self._body_fragment
            self._body_fragment = None
        return body_fragment

    def on_req_method(self, method):
        self._http_msg.method = method

    def on_req_path(self, url):
        self._http_msg.url = url

    def on_headers_complete(self):
        # Execute against the pipeline
        action = self._filter_pl.on_request(self._http_msg)

        # If we're rejecting then we're not going to connect to upstream
        if action.is_rejecting():
            self._rejected = True
            self._response = action.payload
        else:
            # We're routing to upstream; we need to know where to go
            if action.is_routing():
                self._connect_upstream(self._http_msg, action.payload)
            else:
                self._connect_upstream(self._http_msg)

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if not self._rejected:
            # If we're not already connected, store the fragment for later
            if not self._upstream:
                self._store_body(bytes)
            else:
                _write_to_stream(
                    self._upstream,
                    self._get_body(bytes),
                    is_chunked)

    def on_message_complete(self, is_chunked, keep_alive):
        if self._rejected:
            callback = None if keep_alive else self._downstream.close

            self._downstream.write(
                self._response.to_bytes(),
                callback=callback)
        elif is_chunked:
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
        self._http_msg.status_code = str(status_code)

    def on_headers_complete(self):
        action = self._filter_pl.on_response(self._http_msg)
        if action.is_rejecting():
            self._rejected = True
            self._response = action.response
        else:
            self._downstream.write(self._http_msg.to_bytes())

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if self._rejected:
            return
        _write_to_stream(self._downstream, bytes, is_chunked)

    def on_message_complete(self, is_chunked, keep_alive):
        callback = None if keep_alive else self._downstream.close

        if self._rejected:
            self._downstream.write(
                self._http_msg.to_bytes(),
                callback=callback)
        elif is_chunked:
            # Finish the last chunk.
            self._downstream.write(
                _CHUNK_CLOSE,
                callback=callback)


class ConnectionTracker(object):

    def __init__(self, on_live_cb, pipe_broken_cb):
        self._streams = dict()
        self._target_in_use = None
        self._on_live_cb = on_live_cb
        self._pipe_broken_cb = pipe_broken_cb

    def destroy(self):
        for stream in self._streams.values():
            if not stream.closed():
                stream.close()

    def connect(self, target):
        self._target_in_use = target
        live_stream = self._streams.get(target)

        if live_stream:
            # Make the cb ourselves since the socket's already connected
            self._on_live_cb(live_stream)
        else:
            self._new_connection(target)

    def _new_connection(self, target):
        # Set up our upstream socket
        us_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        us_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        us_sock.setblocking(0)

        # Create and bind the IOStream
        live_stream = tornado.iostream.IOStream(us_sock)
        self._streams[target] = live_stream

        def on_close():
            if self._target_in_use == target:
                self._pipe_broken_cb()
            del self._streams[target]
        live_stream.set_close_callback(on_close)

        def on_connect():
            self._on_live_cb(live_stream)
        live_stream.connect(target, on_connect)


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
            self._on_pipe_broken)

        # TODO:Review - Is this kind of hold really needed? Hmmm...
        self._hold_downstream = False

        # Setup all of the wiring for downstream
        self._downstream = downstream
        self._downstream_handler = DownstreamHandler(
            self._downstream,
            self._ds_filter_pl,
            self._connect_upstream)
        self._downstream_parser = RequestParser(self._downstream_handler)
        self._downstream.set_close_callback(self._on_downstream_close)
        self._downstream.read_bytes(
            num_bytes=_MAX_READ,
            callback=self._on_downstream_read,
            streaming_callback=self._on_downstream_read)

    def _connect_upstream(self, request, route=None):
        if route:
            # This does some type checking for routes passed up via filter
            self._router.set_next(route)
        upstream_target = self._router.get_next()

        # Hold downstream reads
        self._hold_downstream = True

        # Update the request to proxy upstream and store it
        request.replace_header('host').values.append(
            '{}:{}'.format(upstream_target[0], upstream_target[1]))
        self._request = request
        self._upstream_tracker.connect(upstream_target)

    def _on_upstream_live(self, upstream):
        self._upstream_handler = UpstreamHandler(
            self._downstream,
            upstream,
            self._us_filter_pl)

        if self._upstream_parser:
            self._upstream_parser.destroy()
        self._upstream_parser = ResponseParser(self._upstream_handler)

        # Send the proxied request object
        upstream.write(self._request.to_bytes())

        # Set the read callback if it's not already reading
        if not upstream.reading():
            upstream.read_until_close(
                callback=self._on_upstream_read,
                streaming_callback=self._on_upstream_read)

        # Drop the ref to the proxied request head
        self._request = None

        # Allow downstream reads again
        self._hold_downstream = False
        if not self._downstream.reading():
            self._downstream.read_bytes(
                num_bytes=_MAX_READ,
                callback=self._on_downstream_read,
                streaming_callback=self._on_downstream_read)

    def _on_downstream_close(self):
        self._upstream_tracker.destroy()
        self._downstream_parser.destroy()

    def _on_pipe_broken(self):
        if not self._downstream.closed() and not self._downstream.closed():
            self._downstream.close()
        if self._upstream_parser:
            self._upstream_parser.destroy()

    def _on_downstream_read(self, data):
        if len(data) > 0:
            try:
                self._downstream_parser.execute(data)
            except iostream.StreamClosedError:
                pass
            except Exception as ex:
                _LOG.exception(ex)
        elif not self._hold_downstream:
            self._downstream.read_bytes(
                num_bytes=_MAX_READ,
                callback=self._on_downstream_read,
                streaming_callback=self._on_downstream_read)

    def _on_upstream_read(self, data):
        try:
            self._upstream_parser.execute(data)
        except iostream.StreamClosedError:
            pass
        except Exception as ex:
            _LOG.exception(ex)


class TornadoHttpProxy(tornado.tcpserver.TCPServer):
    """
    Subclass of the Tornado TCPServer that lets us set up the Pyrox proxy
    orchestrations.

    :param pipelines: This is a tuple with the upstream filter pipeline factory
                      as the first element and the downstream filter pipeline
                      factory as the second element.
    """
    def __init__(self, pipeline_factories, default_us_targets=None):
        super(TornadoHttpProxy, self).__init__()
        self._router = RoutingHandler(default_us_targets)
        self.us_pipeline_factory = pipeline_factories[0]
        self.ds_pipeline_factory = pipeline_factories[1]

    def handle_stream(self, downstream, address):
        connection_handler = ProxyConnection(
            self.us_pipeline_factory(),
            self.ds_pipeline_factory(),
            downstream,
            self._router)
