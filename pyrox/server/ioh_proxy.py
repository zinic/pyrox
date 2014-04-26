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

    def __init__(self, cer, io_loop=None):
        self._io_loop = io_loop or ioloop.IOLoop.current()
        self._cer = cer

    def start(self):
        self._io_loop.start()

    def listen(self, family, address):
        new_channel = ioh.SocketChannel.Listen(
            address=address,
            family=family,
            io_loop=self._io_loop)

        # Watch the channel and enable reading from it
        self._cer.register(new_channel)
        new_channel.enable_reads()


class MyEventHandler(ioh.ChannelEventHandler):

    def on_accept(self, new_channel):
        new_channel.enable_reads()

    def on_close(self, channel):
        print('close')
        channel.close()

    def on_error(self, channel):
        print('error')
        channel.close()

    def on_connect(self, channel):
        print('connect')

    def on_read(self, channel, message):
        print(message)

        if message.endswith('\n'):
            channel.send('HTTP/1.1 200 OK\r\n')
            channel.send('Content-Length: 0\r\n')
            channel.send('\r\n')

    def on_send(self, channel, message):
        channel.send(message)


io_loop = ioloop.IOLoop.current()

cer = ioh.ChannelEventRouter(MyEventHandler(), io_loop)
cs = SocketChannelServer(cer, io_loop)
cs.listen(socket.AF_INET, ('0.0.0.0', 8080))
cs.start()
