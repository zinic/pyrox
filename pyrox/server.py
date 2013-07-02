from .env import get_logger

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado.tcpserver import TCPServer

from pyrox.http import HttpParser, ParserDelegate


_LOG = get_logger(__name__)


class FilterHandler(ParserDelegate):

    def __init__(self, method_interests, url_matcher):
        self.method_interests = method_interests
        self.url_matcher = url_matcher

    def on_req_method(self, method):
        if self.method_interests and method in self.method_interests:
            print('Capturing request by method')

    def on_url(self, url):
        if self.url_matcher and self.url_matcher.matches(url):
            print('Capturing request by url')

    def on_header(self, name, value):
        pass


class TornadoConnection(object):

    def __init__(self, parser, stream, address):
        self.stream = stream
        self.address = address
        self.parser = parser

        # Set our callbacks
        self.stream.set_close_callback(self._on_close)
        self.stream.read_until_close(
            callback=self._on_read,
            streaming_callback=self._on_stream)

    def _on_stream(self, data):
        self.parser.execute(data, len(data))

    def _on_read(self, data):
        pass

    def _on_close(self):
        pass


class TornadoHttpProxy(TCPServer):

    def __init__(self, address, ssl_options=None):
        super(TornadoHttpProxy, self).__init__(ssl_options=ssl_options)
        self.address = address

    def start(self):
        self.bind(self.address[1], self.address[0])
        super(TornadoHttpProxy, self).start()
        _LOG.info('TCP server ready!')

    def handle_stream(self, stream, address):
        TornadoConnection(HttpParser(FilterHandler(['GET'], None)), stream, address)

def start_io():
    IOLoop.instance().start()
