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


class ProxyHandler(ParserDelegate):
    """
    Common class for the stream handlers. This parent class manages the
    following:

    - Handling of header field names.
    - Tracking rejection of message sessions.
    - Streaming of the request/response bodies.
    """
    def __init__(self, filter_chain, stream):
        self.filter_chain = filter_chain
        self.current_header_field = None
        self.rejected = False
        self.stream = stream

    def on_header_field(self, field):
        self.current_header_field = field

    def on_body(self, bytes, length, is_chunked):
        if not self.rejected:
            if is_chunked:
                hex_len = hex(length)[2:]
                self.stream.write(b'{}\r\n{}\r\n'.format(hex_len, bytes))
            else:
                self.stream.write(bytes)


class DownstreamProxyHandler(ProxyHandler):
    """
    This proxy handler manages data coming from downstream of the proxy.
    This data comes from the client initiating the request against the
    proxy.
    """
    def __init__(self, filter_chain, downstream, upstream, upstream_host):
        super(DownstreamProxyHandler, self).__init__(filter_chain, upstream)
        self.downstream = downstream
        self.upstream = upstream
        self.upstream_host = upstream_host

    def on_req_method(self, method):
        self.request = HttpRequest()
        self.response = HttpResponse()
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
        action = self.filter_chain.on_request(self.request)
        if action.is_rejecting():
            self.rejected = True
            self.response = action.response
        else:
            self.upstream.write(self.request.to_bytes())

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
            # Finish the last chunk.
            self.upstream.write(b'0\r\n\r\n')


class UpstreamProxyHandler(ProxyHandler):
    """
    This proxy handler manages data coming from upstream of the proxy. This
    data usually comes from the origin service or it may come from another
    proxy.
    """
    def __init__(self, filter_chain, downstream, upstream):
        super(UpstreamProxyHandler, self).__init__(filter_chain, downstream)
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
        action = self.filter_chain.on_response(self.response)
        if action.is_rejecting():
            self.rejected = True
            self.response = action.response
        else:
            self.downstream.write(self.response.to_bytes())

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
    def __init__(self, us_filter_pipeline, ds_filter_pipeline, downstream,
            upstream, upstream_host):
        self.downstream = downstream
        self.upstream = upstream
        self.downstream_handler = DownstreamProxyHandler(
            ds_filter_pipeline, downstream, upstream, upstream_host)
        self.upstream_handler = UpstreamProxyHandler(
            us_filter_pipeline, downstream, upstream)
        self.downstream_parser = RequestParser(self.downstream_handler)
        self.upstream_parser = ResponseParser(self.upstream_handler)

    def on_upstream_connect(self):
        # Downstream callbacks
        self.downstream.set_close_callback(self._on_downstream_close)
        self.downstream.read_until_close(
            callback=self._on_downstream_read,
            streaming_callback=self._on_downstream_read)
        # Upstream callbacks
        self.upstream.set_close_callback(self._on_upstream_close)
        self.upstream.read_until_close(
            callback=self._on_upstream_read,
            streaming_callback=self._on_upstream_read)

    def _on_downstream_close(self):
        if not self.upstream.closed():
            self.upstream.close()
        self.downstream_parser.destroy()

    def _on_upstream_close(self):
        if not self.downstream.closed():
            self.downstream.close()
        self.upstream_parser.destroy()

    def _on_downstream_read(self, data):
        try:
            self.downstream_parser.execute(data)
        except iostream.StreamClosedError:
            pass
        except Exception as ex:
            _LOG.exception(ex)

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
    def __init__(self, pipeline_factories, upstream_target=None):
        super(TornadoHttpProxy, self).__init__()
        self.upstream_target = upstream_target
        self.us_pipeline_factory = pipeline_factories[0]
        self.ds_pipeline_factory = pipeline_factories[1]

    def handle_stream(self, downstream, address):
        ds_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        ds_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ds_sock.setblocking(0)
        upstream = tornado.iostream.IOStream(ds_sock)

        connection_handler = ProxyConnection(
            self.us_pipeline_factory(),
            self.ds_pipeline_factory(),
            downstream,
            upstream,
            '{}:{}'.format(
                self.upstream_target[0], self.upstream_target[1]))
        upstream.connect(
            self.upstream_target,
            connection_handler.on_upstream_connect)
