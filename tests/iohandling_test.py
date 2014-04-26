import socket
import unittest
import tornado
import mock

from pyrox.iohandling import *


class TornadoTestCase(unittest.TestCase):

    def setUp(self):
        self.io_loop = mock.MagicMock()

        # Mock the FD interests
        self.io_loop.ERROR = ERROR
        self.io_loop.READ = READ
        self.io_loop.WRITE = WRITE

    def tearDown(self):
        pass


class FileDescriptorChannelsTests(TornadoTestCase):

    def setUp(self):
        super(FileDescriptorChannelsTests, self).setUp()

        self.fd_channel = FileDescriptorChannel(0, self.io_loop)
        self.fd_channel.closed = lambda: False

    def test_setting_handlers(self):
        event_handler = mock.MagicMock()
        self.fd_channel.set_handler(event_handler)

        self.assertEqual(self.io_loop.ERROR,
            self.fd_channel._event_interests)
        self.assertTrue(self.fd_channel._has_handler)
        self.io_loop.add_handler.assert_called_once_with(0,
            event_handler, self.io_loop.ERROR)

    def test_setting_handlers_on_closed_channels(self):
        self.fd_channel.closed = lambda: True

        event_handler = mock.MagicMock()

        with self.assertRaises(ChannelError):
            self.fd_channel.set_handler(event_handler)

    def test_setting_handlers_twice(self):
        event_handler = mock.MagicMock()
        self.fd_channel.set_handler(event_handler)

        with self.assertRaises(ChannelError):
            self.fd_channel.set_handler(event_handler)

    def test_removing_handlers(self):
        event_handler = mock.MagicMock()

        self.fd_channel.set_handler(event_handler)
        self.fd_channel.remove_handler()

        self.assertEqual(self.io_loop.ERROR,
            self.fd_channel._event_interests)
        self.assertFalse(self.fd_channel._has_handler)
        self.io_loop.remove_handler.assert_called_once_with(0)

    def test_read_interest_controls(self):
        event_handler = mock.MagicMock()
        error_and_read_interests = self.io_loop.ERROR | self.io_loop.READ

        self.fd_channel.set_handler(event_handler)
        self.fd_channel.enable_reads()

        self.assertEqual(error_and_read_interests,
            self.fd_channel._event_interests)
        self.io_loop.update_handler.assert_called_with(0,
            error_and_read_interests)
        self.assertTrue(self.fd_channel.reads_enabled())

        self.fd_channel.disable_reads()

        self.assertEqual(self.io_loop.ERROR,
            self.fd_channel._event_interests)
        self.io_loop.update_handler.assert_called_with(0,
            self.io_loop.ERROR)
        self.assertFalse(self.fd_channel.reads_enabled())

    def test_write_interest_controls(self):
        event_handler = mock.MagicMock()
        error_and_write_interests = self.io_loop.ERROR | self.io_loop.WRITE

        self.fd_channel.set_handler(event_handler)
        self.fd_channel.enable_writes()

        self.assertEqual(error_and_write_interests,
            self.fd_channel._event_interests)
        self.io_loop.update_handler.assert_called_with(0,
            error_and_write_interests)
        self.assertTrue(self.fd_channel.writes_enabled())

        self.fd_channel.disable_writes()

        self.assertEqual(self.io_loop.ERROR,
            self.fd_channel._event_interests)
        self.io_loop.update_handler.assert_called_with(0,
            self.io_loop.ERROR)
        self.assertFalse(self.fd_channel.writes_enabled())

    def test_error_interest_controls(self):
        event_handler = mock.MagicMock()

        self.fd_channel.set_handler(event_handler)
        self.fd_channel.disable_errors()
        self.assertFalse(self.fd_channel.errors_enabled())

        self.assertEqual(0,
            self.fd_channel._event_interests)
        self.io_loop.update_handler.assert_called_with(0, 0)

        self.fd_channel.enable_errors()

        self.assertEqual(self.io_loop.ERROR,
            self.fd_channel._event_interests)
        self.io_loop.update_handler.assert_called_with(0,
            self.io_loop.ERROR)
        self.assertTrue(self.fd_channel.errors_enabled())



class SocketChannelsTests(TornadoTestCase):

    def setUp(self):
        super(SocketChannelsTests, self).setUp()
        self.socket = mock.MagicMock()
        self.socket.fileno = lambda: 0

        self.socket_channel = SocketChannel(self.socket, self.io_loop)

    def test_init(self):
        self.socket.setsockopt.assert_called_with(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setblocking.assert_called_with(0)

    def test_recieving(self):
        self.socket_channel.recv(4)
        self.socket.recv.assert_called_with(4)

    def test_recieving_into(self):
        buffer = mock.MagicMock()

        self.socket_channel.recv_into(buffer, 4)
        self.socket.recv_into.assert_called_with(buffer, 4)

    def test_sending(self):
        self.socket_channel.send(b'test')
        self.assertTrue(self.socket_channel.has_queued_send())

    def test_sending_twice(self):
        self.socket_channel.send(b'test')

        with self.assertRaises(ChannelError):
            self.socket_channel.send(b'test')

    def test_flusing(self):
        self.socket.send.return_value = 2
        self.socket_channel.send(b'test')

        self.assertFalse(self.socket_channel.flush())
        self.assertTrue(self.socket_channel.flush())

    def test_closing(self):
        event_handler = mock.MagicMock()

        self.socket_channel.set_handler(event_handler)

        self.assertFalse(self.socket_channel.closed())
        self.socket_channel.close()
        self.assertTrue(self.socket_channel.closed())

        self.io_loop.remove_handler.assert_called()

    def test_getting_socket_errors(self):
        self.socket_channel.error()
        self.socket.getsockopt.assert_called_with(
            socket.SOL_SOCKET, socket.SO_ERROR)


class WhenTesting(TornadoTestCase):

    def test_magic(self):
        socket = mock.MagicMock()
        socket.fileno.return_value = 25

        channel = SocketChannel(socket, io_loop=self.io_loop)

        event_router = ChannelEventRouter(io_loop=self.io_loop)
        event_router.register(channel)

        self.io_loop.add_handler.assert_called_once_with(socket.fileno(),
            mock.ANY, self.io_loop.ERROR)


if __name__ == '__main__':
    unittest.main()
