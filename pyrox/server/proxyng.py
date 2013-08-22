import socket

import tornado
import tornado.ioloop
import tornado.process
import tornado.iostream as iostream
import tornado.tcpserver as tcpserver

from pyrox.log import get_logger
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)
from pyrox.http.model_util import is_host

_LOG = get_logger(__name__)


MAX_READ = 1024


class ProxyHandler(ParserDelegate):
    """
    Common class for the stream handlers. This parent class manages the
    following:

    - Handling of header field names.
    - Tracking rejection of message sessions.
    - Streaming of the request/response bodies.
    """
    def __init__(self, filter_pl):
        self.filter_pl = filter_pl
        self.current_header_field = None
        self.rejected = False

    def on_header_field(self, field):
        self.current_header_field = field


def write(stream, bytes, is_chunked):
    if is_chunked:
        chunk = bytearray()
        hex_len = hex(length)[2:]

        # Format and write this chunk
        chunk.extend(hex_len)
        chunk.extend('\r\n')
        chunk.extend(bytes)
        chunk.extend('\r\n')
        stream.write(chunk)
    else:
        stream.write(bytes)


class DownstreamHandler(ProxyHandler):
    """
    This proxy handler manages data coming from downstream of the proxy.
    This data comes from the client initiating the request against the
    proxy.
    """
    def __init__(self, downstream, filter_pl, connect_upstream):
        super(DownstreamHandler, self).__init__(filter_pl)
        self.request = HttpRequest()
        self.downstream = downstream
        self.upstream = None
        self.body_fragment = None
        self.connect_upstream = connect_upstream

    def on_req_method(self, method):
        self.request.method = method

    def on_req_path(self, url):
        self.request.url = url

    def on_http_version(self, major, minor):
        self.request.version = '{}.{}'.format(major, minor)

    def on_header_value(self, value):
        # Special case for host
        if is_host(value):
            header = self.request.header(self.current_header_field)
            header.values.append(self.upstream_host)
        else:
            header = self.request.header(self.current_header_field)
            header.values.append(value)

    def on_headers_complete(self):
        # Execute against the pipeline
        action = self.filter_pl.on_request(self.request)

        # If we're rejecting then we're not going to connect to upstream
        if action.is_rejecting():
            self.rejected = True
            self.response = action.payload
        else:
            # We're routing to upstream; we need to know where to go
            if action.is_routing():
                self.connect_upstream(self.request, action.payload)
            else:
                self.connect_upstream(self.request)

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if self.rejected:
            return

        # If we're not already connected, store the fragment for later
        if not self.upstream:
            self.body_fragment = bytes
        else:
            if self.body_fragment:
                bytes = self.body_fragment.extend(bytes)
                self.body_fragment = None
            write(self.upstream, bytes, is_chunked)

    def on_message_complete(self, is_chunked, should_keep_alive):
        if self.rejected:
            # Rejections do not stream the body - they discard it, therefore
            # we have to commit the head here.
            if should_keep_alive == 0:
                if self.upstream:
                    self.downstream.write(
                        self.response.to_bytes(),
                        callback=self.upstream.close)
                else:
                    self.downstream.write(
                        self.response.to_bytes(),
                        callback=self.downstream.close)
            else:
                self.downstream.write(self.response.to_bytes())
        elif is_chunked != 0:
            # Finish the last chunk.
            self.upstream.write(b'0\r\n\r\n')


class UpstreamHandler(ProxyHandler):
    """
    This proxy handler manages data coming from upstream of the proxy. This
    data usually comes from the origin service or it may come from another
    proxy.
    """
    def __init__(self, downstream, upstream, filter_pl):
        super(UpstreamHandler, self).__init__(filter_pl)
        self.downstream = downstream
        self.upstream = upstream

    def on_http_version(self, major, minor):
        self.response = HttpResponse()
        self.response.version = '{}.{}'.format(major, minor)

    def on_status(self, status_code):
        self.response.status_code = str(status_code)

    def on_header_value(self, value):
        self.response.header(self.current_header_field).values.append(value)

    def on_headers_complete(self):
        action = self.filter_pl.on_response(self.response)
        if action.is_rejecting():
            self.rejected = True
            self.response = action.response
        else:
            self.downstream.write(self.response.to_bytes())

    def on_body(self, bytes, length, is_chunked):
        # Rejections simply discard the body
        if self.rejected:
            return
        write(self.downstream, bytes, is_chunked)

    def on_message_complete(self, is_chunked, should_keep_alive):
        if self.rejected:
            # Rejections do not stream the body - they discard it, therefore
            # we have to commit the head here.
            if should_keep_alive == 0:
                self.downstream.write(
                    self.response.to_bytes(),
                    callback=self.upstream.close)
            else:
                self.downstream.write(self.response.to_bytes())
        elif is_chunked != 0:
                if should_keep_alive == 0:
                    # Finish the last chunk.
                    self.downstream.write(
                        b'0\r\n\r\n',
                        callback=self.upstream.close)
                else:
                    self.downstream.write(b'0\r\n\r\n')
        elif should_keep_alive == 0:
            self.upstream.close()



class ProxyConnection(object):
    """
    A proxy connection manages the lifecycle of the sockets opened during a
    proxied client request against Pyrox.
    """
    def __init__(self, us_filter_pl, ds_filter_pl, downstream, default_upstream_target):
        self.ds_filter_pl = ds_filter_pl
        self.us_filter_pl = us_filter_pl
        self.default_upstream_target = default_upstream_target
        self.hold_downstream = False
        self.downstream = downstream
        self.upstream = None
        self._init_downstream()

    def _init_downstream(self):
        self.downstream_handler = DownstreamHandler(
            self.downstream,
            self.ds_filter_pl,
            self.connect_upstream)
        self.downstream_parser = RequestParser(self.downstream_handler)

        # Downstream callbacks
        self.downstream.set_close_callback(self._on_downstream_close)
        self.downstream.read_bytes(
            num_bytes=MAX_READ,
            callback=self._on_downstream_read,
            streaming_callback=self._on_downstream_read)

    def connect_upstream(self, request, route=None):
        # Hold downstream reads
        self.hold_downstream = True

        # Request to proxy upstream
        self.request = request

        # Set up our upstream socket
        us_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        us_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        us_sock.setblocking(0)

        self.upstream = tornado.iostream.IOStream(us_sock)

        upstream_target = route if route else self.default_upstream_target
        self.upstream.connect(upstream_target, self.on_upstream_connect)

    def on_upstream_connect(self):
        # Upstream callbacks
        self.upstream_handler = UpstreamHandler(self.downstream, self.upstream,
                self.us_filter_pl)
        self.upstream_parser = ResponseParser(self.upstream_handler)
        self.upstream.set_close_callback(self._on_upstream_close)
        self.upstream.read_until_close(
            callback=self._on_upstream_read,
            streaming_callback=self._on_upstream_read)

        # Send the proxied request object
        self.upstream.write(self.request.to_bytes())
        self.request = None

        # Allow downstream reads again
        self.hold_downstream = False
        if not self.downstream.reading():
            self.downstream.read_bytes(
                num_bytes=MAX_READ,
                callback=self._on_downstream_read,
                streaming_callback=self._on_downstream_read)

    def _on_downstream_close(self):
        if self.upstream and not self.upstream.closed():
            self.upstream.close()
        self.downstream_parser.destroy()

    def _on_upstream_close(self):
        if not self.downstream.closed():
            self.downstream.close()
        self.upstream_parser.destroy()

    def _on_downstream_read(self, data):
        print('Read {} bytes from downstream'.format(len(data)))

        if len(data) > 0:
            try:
                self.downstream_parser.execute(data)
            except iostream.StreamClosedError:
                pass
            except Exception as ex:
                _LOG.exception(ex)
        elif not self.hold_downstream:
            self.downstream.read_bytes(
                num_bytes=MAX_READ,
                callback=self._on_downstream_read,
                streaming_callback=self._on_downstream_read)

    def _on_upstream_read(self, data):
        try:
            self.upstream_parser.execute(data)
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
    def __init__(self, pipeline_factories, default_upstream_targets=None):
        super(TornadoHttpProxy, self).__init__()
        self.default_upstream_targets = default_upstream_targets
        self.us_pipeline_factory = pipeline_factories[0]
        self.ds_pipeline_factory = pipeline_factories[1]

    def handle_stream(self, downstream, address):
        connection_handler = ProxyConnection(
            self.us_pipeline_factory(),
            self.ds_pipeline_factory(),
            downstream,
            self.default_upstream_targets)
