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
        self.event_handler = event_handler
        self._io_loop = io_loop if io_loop != None else ioloop.IOLoop.current()

    def listen(self, family, address):
        new_channel = ioh.SocketChannel.Listen(
            address=address,
            family=family,
            io_loop=self._io_loop)

        return ioh.ChannelHandler(new_channel, self.event_handler)


class MyEventHandler(ioh.EventHandler):

    def on_accept(self, channel):
        print('New connection: {}'.format(channel))

    def on_close(self, channel):
        print('close')

    def on_error(self, channel):
        print('error')

    def on_connect(self, channel):
        print('connect')


io_loop = ioloop.IOLoop.current()
cs = SocketChannelServer(MyEventHandler(), io_loop)
handler = cs.listen(socket.AF_INET, ('0.0.0.0', 8080))

ioloop.IOLoop.current().start()
