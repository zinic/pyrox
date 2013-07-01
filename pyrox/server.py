from .env import get_logger

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado.tcpserver import TCPServer

from http_parser.parser import HttpParser


_LOG = get_logger(__name__)


class TornadoHttpConnection(object):

    def __init__(self, reader, stream, address):
        self.reader = reader
        self.stream = stream
        self.address = address
        self.parser = HttpParser()

        # Set our callbacks
        self.stream.set_close_callback(self._on_close)
        self.stream.read_until_close(
            callback=self._on_read,
            streaming_callback=self._on_stream)

    def _on_stream(self, data):
        pass

    def _on_read(self, data):
        pass

    def _on_close(self):
        pass


class TornadoTcpServer(TCPServer):

    def __init__(self, address, ssl_options=None):
        super(TornadoTcpServer, self).__init__(ssl_options=ssl_options)
        self.address = address

    def start(self):
        self.bind(self.address[1], self.address[0])
        super(TornadoTcpServer, self).start()
        _LOG.info('TCP server ready!')


def start_io():
    IOLoop.instance().start()
