from __future__ import print_function

import socket
import tornado

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado.tcpserver import TCPServer

from .env import get_logger
from .http import HttpEventParser, ParserDelegate, REQUEST_PARSER, RESPONSE_PARSER



_LOG = get_logger(__name__)


class ProxyHandler(ParserDelegate):

    def __init__(self, filter_handler, stream):
        self.filter_handler = filter_handler
        self.stream = stream
        self.rewrite_host_header = False
        self.reading_transfer_encoding = False
        self.transfer_encoding_chunked = False

    def on_header_field(self, field):
        lower = field.lower()

        if lower =='transfer-encoding':
            self.reading_transfer_encoding = True
        elif lower == 'host':
            self.rewrite_host_header = True

        print('{}: '.format(field), end='')
        self.stream.write(field)
        self.stream.write(b': ')

    def on_header_value(self, value):
        if self.reading_transfer_encoding and value.lower() == 'chunked':
            self.reading_transfer_encoding = False
            self.transfer_encoding_chunked = True
        print(value)
        self.stream.write(value)
        self.stream.write(b'\r\n')

    def on_headers_complete(self):
        print('\r\n', end='')
        self.stream.write(b'\r\n')

    def on_body(self, bytes):
        if self.transfer_encoding_chunked:
            hex_len = hex(len(bytes))[2:].upper()
            print('{}\r\n'.format(hex_len))
            self.stream.write(hex_len)
            self.stream.write(b'\r\n')
            print(bytes)
            self.stream.write(bytes)
            print('\r\n')
            self.stream.write(b'\r\n')
        else:
            print(bytes)
            self.stream.write(bytes)

    def on_message_complete(self):
        if self.transfer_encoding_chunked:
            self.stream.write(b'0\r\n')


class UpstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_handler, downstream, downstream_host):
        super(UpstreamProxyHandler, self).__init__(filter_handler, downstream)
        self.downstream_host = downstream_host

    def on_req_method(self, method):
        print('{} '.format(method), end='')
        self.stream.write(method)
        self.stream.write(b' ')

    def on_req_path(self, url):
        print(url, end='')
        self.stream.write(url)

    def on_http_version(self, major, minor):
        print(' HTTP/1.1')
        self.stream.write(b' HTTP/1.1\r\n')

    def on_header_value(self, value):
        if self.rewrite_host_header:
            self.rewrite_host_header = False
            print(self.downstream_host)
            self.stream.write(self.downstream_host)
            self.stream.write(b'\r\n')
        else:
            super(UpstreamProxyHandler, self).on_header_value(value)


class DownstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_handler, upstream):
        super(DownstreamProxyHandler, self).__init__(filter_handler, upstream)

    def on_status(self, status_code):
        print('HTTP/1.1 {} SC Not Enabled'.format(status_code))
        self.stream.write(b'HTTP/1.1 {}SC Not Enabled\r\n'.format(status_code))


class FilterHandler(ParserDelegate):

    def __init__(self, method_interests, url_matcher):
        self.method_interests = method_interests
        self.url_matcher = url_matcher

    def on_status(self, status_code):
        _LOG.info('Capturing status code')

    def on_req_method(self, method):
        if self.method_interests and method in self.method_interests:
            _LOG.info('Capturing request by method')

    def on_url(self, url):
        if self.url_matcher and self.url_matcher.matches(url):
            _LOG.info('Capturing request by url')

    def on_header(self, name, value):
        pass


class ProxyConnection(object):

    def __init__(self, upstream, downstream, downstream_host):
        self.upstream = upstream
        self.downstream = downstream
        self.upstream_handler = UpstreamProxyHandler(None, downstream, downstream_host)
        self.upstream_parser = HttpEventParser(self.upstream_handler, REQUEST_PARSER)
        self.downstream_handler = DownstreamProxyHandler(None, upstream)
        self.downstream_parser = HttpEventParser(self.downstream_handler, RESPONSE_PARSER)

    def on_downstream_connect(self):
        # Set our callbacks
        self.downstream.set_close_callback(self._on_downstream_close)
        self.downstream.read_until_close(
            callback=self._on_downstream_read,
            streaming_callback=self._on_downstream_read)
        self.upstream.set_close_callback(self._on_upstream_close)
        self.upstream.read_until_close(
            callback=self._on_upstream_read,
            streaming_callback=self._on_upstream_read)

    def _on_upstream_close(self):
        print('Upstream closed')

    def _on_downstream_close(self):
        print('Downstream closed')

    def _on_upstream_read(self, data):
        try:
            self.upstream_parser.execute(data, len(data))
        except Exception as ex:
            raise ex

    def _on_downstream_read(self, data):
        print(data)
        try:
            self.downstream_parser.execute(data, len(data))
        except Exception as ex:
            raise ex


class TornadoHttpProxy(TCPServer):

    def __init__(self, address, ssl_options=None, downstream_target=None):
        super(TornadoHttpProxy, self).__init__(ssl_options=ssl_options)
        self.address = address
        self.downstream_target = downstream_target

    def start(self, processes=0):
        # bind() args are port, address
        self.bind(self.address[1], self.address[0])
        super(TornadoHttpProxy, self).start(processes)
        _LOG.info('TCP server running on: {0}:{1}',
                  self.address[0], self.address[1])

    def handle_stream(self, upstream, address):
        ds_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        downstream = tornado.iostream.IOStream(ds_sock)

        connection_handler = ProxyConnection(
            upstream,
            downstream,
            '{}:{}'.format(self.downstream_target[0], self.downstream_target[1]))
        downstream.connect(
            self.downstream_target,
            connection_handler.on_downstream_connect)


def start_io():
    IOLoop.instance().start()
