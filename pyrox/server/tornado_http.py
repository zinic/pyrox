import socket

import tornado
import tornado.ioloop
import tornado.process
import tornado.iostream as iostream
import tornado.tcpserver as tcpserver

from pyrox.env import get_logger
from pyrox.http import (HttpRequest, HttpResponse, RequestParser,
                        ResponseParser, ParserDelegate)


_LOG = get_logger(__name__)


def commit_message_headers(stream, headers):
    for header_key, header in headers.items():
        if len(header.values) == 0:
            # Header has no values, continue to the next one
            continue

        # TODO:Review - Examine the cost of using format like this
        stream.write(b'{}: '.format(header.name))
        stream.write(b'{}'.format(header.values[0]))

        # Write other headers if they're there
        if len(header.values) > 1:
            for header_value in header.values[1:]:
                stream.write(b', {} '.format(header.name))
        stream.write(b'\r\n')
    stream.write(b'\r\n')


def write_response_head_to_stream(stream, response):
    stream.write(b'HTTP/{} {} -\r\n'.format(
        response.version,
        response.status_code))
    commit_message_headers(stream, response.headers)


class ProxyHandler(ParserDelegate):

    def __init__(self, filter_chain, body_stream):
        self.filter_chain = filter_chain
        self.current_header_field = None
        self.body_stream = body_stream
        self.transfer_encoding_chunked = False

    def on_header_field(self, field):
        self.current_header_field = field

    def on_body(self, bytes):
        if self.transfer_encoding_chunked:
            hex_len = hex(len(bytes))[2:].upper()
            self.body_stream.write(hex_len)
            self.body_stream.write(b'\r\n')
            self.body_stream.write(bytes)
            self.body_stream.write(b'\r\n')
        else:
            self.body_stream.write(bytes)

    def on_message_complete(self):
        if self.transfer_encoding_chunked:
            self.body_stream.write(b'0\r\n\r\n')


class UpstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_chain, upstream, downstream, downstream_host):
        super(UpstreamProxyHandler, self).__init__(filter_chain, downstream)
        self.upstream = upstream
        self.downstream = downstream
        self.request = HttpRequest()
        self.downstream_host = downstream_host

    def on_req_method(self, method):
        self.request.method = method

    def on_req_path(self, url):
        self.request.url = url

    def on_http_version(self, major, minor):
        self.request.version = '{}.{}'.format(major, minor)

    def on_header_value(self, value):
        # Change the name to lowercase for comparasion
        lower_name = self.current_header_field.lower()

        # Special case for host
        if lower_name == 'host':
            self.request.add_header(
                self.current_header_field, self.downstream_host)
        elif lower_name == 'transfer-encoding' and value.lower() == 'chunked':
            self.transfer_encoding_chunked = True
        else:
            self.request.add_header(self.current_header_field, value)

    def on_headers_complete(self):
        action = self.filter_chain.on_request(self.request)
        if action.is_rejecting():
            write_response_head_to_stream(self.upstream, action.response)
        else:
            self._commit_request_head_downstream()

    def _commit_request_head_downstream(self):
        self.downstream.write(b'{} {} HTTP/{}\r\n'.format(
            self.request.method,
            self.request.url,
            self.request.version))
        commit_message_headers(self.downstream, self.request.headers)


class DownstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_chain, upstream):
        super(DownstreamProxyHandler, self).__init__(filter_chain, upstream)
        self.upstream = upstream
        self.response = HttpResponse()

    def on_http_version(self, major, minor):
        self.response.version = '{}.{}'.format(major, minor)

    def on_status(self, status_code):
        self.response.status_code = status_code

    def on_header_value(self, value):
        # Change the name to lowercase for comparasion
        lower_name = self.current_header_field.lower()
        # Special case for transfer-encoding
        if lower_name == 'transfer-encoding' and value.lower() == 'chunked':
            self.transfer_encoding_chunked = True
        self.response.add_header(self.current_header_field, value)

    def on_headers_complete(self):
        action = self.filter_chain.on_response(self.response)
        if action.is_rejecting():
            write_response_head_to_stream(self.upstream, action.response)
        else:
            self._commit_response_head_upstream()

    def _commit_response_head_upstream(self):
        self.upstream.write(b'HTTP/{} {} -\r\n'.format(
            self.response.version,
            self.response.status_code))
        commit_message_headers(self.upstream, self.response.headers)


class ProxyConnection(object):

    def __init__(self, filter_chain, upstream, downstream, downstream_host):
        self.upstream = upstream
        self.downstream = downstream
        self.upstream_handler = UpstreamProxyHandler(
            filter_chain, upstream, downstream, downstream_host)
        self.downstream_handler = DownstreamProxyHandler(
            filter_chain, upstream)
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
        #print('Upstream closed')
        pass

    def _on_downstream_close(self):
        #print('Downstream closed')
        pass

    def _on_upstream_read(self, data):
        try:
            self.upstream_parser.execute(data, len(data))
        except Exception as ex:
            raise ex

    def _on_downstream_read(self, data):
        try:
            self.downstream_parser.execute(data, len(data))
        except Exception as ex:
            raise ex


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


def start_server(address, filter_chain_constructor,
               processes=0, downstream_target=None):
    tcp_proxy = TornadoHttpProxy(filter_chain_constructor, downstream_target)
    tcp_proxy.bind(address=address[0], port=address[1])
    tcp_proxy.start()
    tornado.ioloop.IOLoop.instance().start()
