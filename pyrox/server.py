from __future__ import print_function

import socket
import tornado

from tornado.ioloop import IOLoop
from tornado.tcpserver import TCPServer

from .env import get_logger
from .http import HttpParser, ParserDelegate



_LOG = get_logger(__name__)


class ProxyHandler(ParserDelegate):

    def __init__(self, filter_handler):
        self.filter_handler = filter_handler

    def on_headers_complete(self):
        print('\r\n', end='')
        self.downstream.write(b'\r\n')

    def on_body(self, bytes):
        print(bytes, end='')
        self.downstream.write(bytes)

    def write_header(self, name, value, stream):
        print('{}: {}'.format(name, value))
        stream.write(name)
        stream.write(b': ')
        stream.write(value)
        stream.write(b'\r\n')


class UpstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_handler, downstream, downstream_host):
        super(UpstreamProxyHandler, self).__init__(filter_handler)
        self.downstream = downstream
        self.downstream_host = downstream_host

    def on_req_method(self, method):
        print('{} '.format(method), end='')
        self.downstream.write(method)
        self.downstream.write(b' ')

    def on_url(self, url):
        print('{} HTTP/1.1\r\n'.format(url), end='')
        self.downstream.write(url)
        self.downstream.write(b' HTTP/1.1\r\n')

    def on_header(self, name, value):
        actual_value = value
        if name.lower() == 'host':
            actual_value = self.downstream_host
        self.write_header(name, actual_value, self.downstream)


class DownstreamProxyHandler(ProxyHandler):

    def __init__(self, filter_handler, upstream):
        super(DownstreamProxyHandler, self).__init__(filter_handler)
        self.upstream = upstream

    def on_status(self, status_code):
        print('HTTP/1.1 {} SC Not Enabled\r\n'.format(status_code), end='')
        self.upstream.write(b'HTTP/1.1 ')
        self.upstream.write(status_code)
        self.upstream.write(b' SC Not Enabled\r\n')

    def on_header(self, name, value):
        self.write_header(name, value, self.upstream)


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
        self.upstream_parser = HttpParser(self.upstream_handler, 0)
        self.downstream_handler = DownstreamProxyHandler(None, upstream)
        self.downstream_parser = HttpParser(self.downstream_handler, 1)

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
        pass

    def _on_downstream_close(self):
        print('Downstream closed')
        pass

    def _on_upstream_read(self, data):
        print('Reading {} upstream bytes...'.format(len(data)))
        print(data)
        try:
            self.upstream_parser.execute(data, len(data))
        except Exception as ex:
            print(ex)

    def _on_downstream_read(self, data):
        print('Reading {} downstream bytes...'.format(len(data)))
        print(data)
        try:
            self.downstream_parser.execute(data, len(data))
        except Exception as ex:
            print(ex)


class TornadoHttpProxy(TCPServer):

    def __init__(self, address, ssl_options=None, downstream_target=None):
        super(TornadoHttpProxy, self).__init__(ssl_options=ssl_options)
        self.address = address
        self.downstream_target = downstream_target

    def start(self, processes=0):
        self.bind(self.address[1], self.address[0])
        super(TornadoHttpProxy, self).start(processes)
        _LOG.info('TCP server running on: {0}:{1}',
                  self.address[1], self.address[0])

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
