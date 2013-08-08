import socket

import tornado
import tornado.ioloop
import tornado.process
import tornado.iostream as iostream
import tornado.tcpserver as tcpserver

from pyrox.env import get_logger
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)
from pyrox.http.model_util import is_host

_LOG = get_logger(__name__)


class ProxyHandler(ParserDelegate):

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


class UpstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_chain, upstream, downstream, downstream_host):
        super(UpstreamProxyHandler, self).__init__(filter_chain, downstream)
        self.upstream = upstream
        self.downstream = downstream
        self.downstream_host = downstream_host

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
            header.values.append(self.downstream_host)
        else:
            header = self.request.header(self.current_header_field)
            header.values.append(value)

    def on_headers_complete(self):
        action = self.filter_chain.on_request(self.request)
        if action.is_rejecting():
            self.rejected = True
            self.response = action.response
        else:
            self.downstream.write(self.request.to_bytes())

    def on_message_complete(self, is_chunked, should_keep_alive):
        if self.rejected:
            # Rejections do not stream the body - they discard it, therefore
            # we have to commit the head here.
            if should_keep_alive == 0:
                self.upstream.write(
                    self.response.to_bytes(),
                    callback=self.downstream.close)
            else:
                self.upstream.write(self.response.to_bytes())
        elif is_chunked != 0:
            # Finish the last chunk.
            self.downstream.write(b'0\r\n\r\n')


class DownstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_chain, upstream, downstream):
        super(DownstreamProxyHandler, self).__init__(filter_chain, upstream)
        self.upstream = upstream
        self.downstream = downstream

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
            self.upstream.write(self.response.to_bytes())

    def on_message_complete(self, is_chunked, should_keep_alive):
        if self.rejected:
            # Rejections do not stream the body - they discard it, therefore
            # we have to commit the head here.
            if should_keep_alive == 0:
                self.upstream.write(
                    self.response.to_bytes(),
                    callback=self.downstream.close)
            else:
                self.upstream.write(self.response.to_bytes())
        elif is_chunked != 0:
                if should_keep_alive == 0:
                    # Finish the last chunk.
                    self.upstream.write(
                        b'0\r\n\r\n',
                        callback=self.downstream.close)
                else:
                    self.upstream.write(b'0\r\n\r\n')
        elif should_keep_alive == 0:
            self.downstream.close()


class ProxyConnection(object):

    def __init__(self, filter_chain, upstream, downstream, downstream_host):
        self.upstream = upstream
        self.downstream = downstream
        self.upstream_handler = UpstreamProxyHandler(
            filter_chain, upstream, downstream, downstream_host)
        self.downstream_handler = DownstreamProxyHandler(
            filter_chain, upstream, downstream)
        self.upstream_parser = RequestParser(self.upstream_handler)
        self.downstream_parser = ResponseParser(self.downstream_handler)

    def on_downstream_connect(self):
        # Upstream callbacks
        self.upstream.set_close_callback(self._on_upstream_close)
        self.upstream.read_until_close(
            callback=self._on_upstream_read,
            streaming_callback=self._on_upstream_read)
        # Downstream callbacks
        self.downstream.set_close_callback(self._on_downstream_close)
        self.downstream.read_until_close(
            callback=self._on_downstream_read,
            streaming_callback=self._on_downstream_read)

    def _on_upstream_close(self):
        if not self.downstream.closed():
            self.downstream.close()
        self.upstream_parser.destroy()

    def _on_downstream_close(self):
        if not self.upstream.closed():
            self.upstream.close()
        self.downstream_parser.destroy()

    def _on_upstream_read(self, data):
        try:
            self.upstream_parser.execute(data)
        except iostream.StreamClosedError:
            pass
        except Exception as ex:
            _LOG.exception(ex)

    def _on_downstream_read(self, data):
        try:
            self.downstream_parser.execute(data)
        except iostream.StreamClosedError:
            pass
        except Exception as ex:
            _LOG.exception(ex)


class TornadoHttpProxy(tornado.tcpserver.TCPServer):

    def __init__(self, filter_chain_constructor, downstream_target=None):
        super(TornadoHttpProxy, self).__init__()
        self.downstream_target = downstream_target
        self.filter_chain_constructor = filter_chain_constructor

    def handle_stream(self, upstream, address):
        ds_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        ds_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ds_sock.setblocking(0)
        downstream = tornado.iostream.IOStream(ds_sock)

        connection_handler = ProxyConnection(
            self.filter_chain_constructor(),
            upstream,
            downstream,
            '{}:{}'.format(
                self.downstream_target[0], self.downstream_target[1]))
        downstream.connect(
            self.downstream_target,
            connection_handler.on_downstream_connect)
