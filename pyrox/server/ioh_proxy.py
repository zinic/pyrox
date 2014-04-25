import copy
import threading
import collections
import errno
import socket
import ssl

from tornado import ioloop
from tornado.netutil import bind_sockets

import pyrox.iohandling as ioh


class SocketChannelServer(object):

    def __init__(self, event_handler, io_loop=None):
        self._io_loop = io_loop or ioloop.IOLoop.current()
        self._event_handler = event_handler

    def listen(self, family, address):
        new_channel = ioh.SocketChannel.Listen(
            address=address,
            family=family,
            io_loop=self._io_loop)

        # Watch the channel and enable reading from it
        ioh.watch_channel(new_channel, self._event_handler)
        new_channel.enable_reads()


class MyEventHandler(ioh.EventHandler):

    def on_accept(self, channel):
        # Watch the channel and enable reading from it
        ioh.watch_channel(channel, self)
        channel.enable_reads()

    def on_close(self, channel):
        print('close')
        channel.close()

    def on_error(self, channel):
        print('error')
        channel.close()

    def on_connect(self, channel):
        print('connect')


class EchoCodec(ioh.ChannelCodec):

    def on_data(self, channel, data):
        print(data)

        if data.endswith('\n'):
            channel.send(
                'HTTP/1.1 200 OK\r\n'
                'Content-Length: 0\r\n'
                '\r\n')


event_handler = MyEventHandler()
event_handler.set_codec_pipeline(
    ioh.ChannelCodecPipeline(
        downstream_codecs=(EchoCodec(), ),
        upstream_codecs=tuple()))

io_loop = ioloop.IOLoop.current()
cs = SocketChannelServer(event_handler, io_loop)
cs.listen(socket.AF_INET, ('0.0.0.0', 8080))

ioloop.IOLoop.current().start()
