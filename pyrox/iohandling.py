from __future__ import absolute_import, division, print_function,\
    with_statement

import copy
import threading
import collections
import errno
import socket
import ssl

from tornado import ioloop
from tornado.log import gen_log
from tornado.netutil import ssl_wrap_socket, ssl_match_hostname, \
    SSLCertificateError
from tornado import stack_context

from datetime import timedelta

try:
    from tornado.platform.posix import _set_nonblocking
except ImportError:
    _set_nonblocking = None

# These errnos indicate that a non-blocking operation must be retried
# at a later time. On most platforms they're the same value, but on
# some they differ.
_ERRNO_WOULDBLOCK = (errno.EWOULDBLOCK, errno.EAGAIN)

# These errnos indicate that a connection has been abruptly terminated.
# They should be caught and handled less noisily than other errors.
_ERRNO_CONNRESET = (errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE)

# Nice constant for enabling debug output
_SHOULD_LOG_DEBUG_OUTPUT = gen_log.isEnabledFor('DEBUG')

# Sharable thread local instance
_THREAD_LOCAL = threading.local()

# Constants from the epoll module
_EPOLLIN = 0x001
_EPOLLPRI = 0x002
_EPOLLOUT = 0x004
_EPOLLERR = 0x008
_EPOLLHUP = 0x010
_EPOLLRDHUP = 0x2000
_EPOLLONESHOT = (1 << 30)
_EPOLLET = (1 << 31)

# Our events map exactly to the epoll events
NONE = 0
READ = _EPOLLIN
WRITE = _EPOLLOUT
ERROR = _EPOLLERR | _EPOLLHUP


def _is_connect_error(ex):
    error = ex.args[0]
    return error != errno.EINPROGRESS and error not in _ERRNO_WOULDBLOCK


def ssl_wrap_socket(schannel, address, options=None, remote_host=None):
    # Wrap the socket using the Pyhton SSL socket library
    schannel._socket = ssl_wrap_socket(
        socket=schannel._socket,
        ssl_options=options,
        server_hostname=remote_host,
        do_handshake_on_connect=False)


class ChannelError(IOError):
    pass


class ChannelEventHandler(object):

    def on_accept(self, new_channel):
        pass

    def on_close(self, channel):
        pass

    def on_error(self, channel):
        pass

    def on_connect(self, channel):
        pass

    def on_read(self, channel, message):
        pass

    def on_send(self, channel, message):
        pass


class Channel(object):

    def set_handler(self, event_handler):
        raise NotImplementedError()

    def remove_handler(self):
        raise NotImplementedError()

    def recv(self, bufsize):
        raise NotImplementedError()

    def recv_into(self, buffer, nbytes=0):
        raise NotImplementedError()

    def send(self, data):
        raise NotImplementedError()

    def flush(self):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

    def closed(self):
        raise NotImplementedError()

    def error(self):
        raise NotImplementedError()


class FileDescriptorChannel(Channel):

    def __init__(self, fileno, io_loop=None):
        assert fileno is not None

        self.fileno = fileno
        self._io_loop = io_loop or ioloop.IOLoop.current()
        self._event_interests = ERROR

        # Is there a handler set?
        self._has_handler = False

    def set_handler(self, event_handler):
        """initialize the ioloop event handler"""
        assert event_handler is not None and callable(event_handler)

        if self.closed():
            raise ChannelError('Channel closed.')

        if self._has_handler:
            raise ChannelError('Channel already has a handler set.')

        # Mark that we have a handler now
        self._has_handler = True

        with stack_context.NullContext():
            self._io_loop.add_handler(
                self.fileno, event_handler, self._event_interests)

    def remove_handler(self):
        self._io_loop.remove_handler(self.fileno)
        self._event_interests = ERROR
        self._has_handler = False

    def errors_enabled(self):
        return self._event_interests & ERROR

    def reads_enabled(self):
        return self._event_interests & READ

    def writes_enabled(self):
        return self._event_interests & WRITE

    def disable_errors(self):
        """
        Alias for removing the error interest from the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Halting error events for stream(fd:{})'.format(
                self.fileno))
        self._drop_event_interest(ERROR)

    def disable_reads(self):
        """
        Alias for removing the read interest from the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Halting read events for stream(fd:{})'.format(
                self.fileno))
        self._drop_event_interest(READ)

    def disable_writes(self):
        """
        Alias for removing the send interest from the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Halting write events for stream(fd:{})'.format(
                self.fileno))
        self._drop_event_interest(WRITE)

    def enable_errors(self):
        """
        Alias for adding the error interest from the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Resuming error events for stream(fd:{})'.format(
                self.fileno))
        self._add_event_interest(ERROR)

    def enable_reads(self):
        """
        Alias for adding the read interest to the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Resuming read events for stream(fd:{})'.format(
                self.fileno))
        self._add_event_interest(READ)

    def enable_writes(self):
        """
        Alias for adding the send interest to the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Resuming write events for stream(fd:{})'.format(
                self.fileno))
        self._add_event_interest(WRITE)

    def _add_event_interest(self, event_interest):
        """Add io_state to poller."""
        if not self._event_interests & event_interest:
            self._event_interests = self._event_interests | event_interest
            self._io_loop.update_handler(self.fileno, self._event_interests)

    def _drop_event_interest(self, event_interest):
        """Stop poller from watching an io_state."""
        if self._event_interests & event_interest:
            self._event_interests = self._event_interests & ~event_interest
            self._io_loop.update_handler(self.fileno, self._event_interests)


class SocketChannel(FileDescriptorChannel):

    def __init__(self, sock, address=None, io_loop=None):
        super(SocketChannel, self).__init__(sock.fileno(), io_loop)

        # State tracking
        self.address = address
        self.connecting = False
        self.listening = False

        # Set important socket options
        self._socket = sock
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setblocking(0)

        # Send buffer management
        self._send_idx = 0
        self._send_len = 0
        self._send_data = None

    @classmethod
    def Listen(cls, address, family=socket.AF_UNSPEC, backlog=128, io_loop=None):
        new_channel = SocketChannel(socket.socket(family), address, io_loop)
        new_channel.listen(address)
        return new_channel

    @classmethod
    def Connect(cls, address, family=socket.AF_UNSPEC, io_loop=None):
        new_channel = SocketChannel(socket.socket(family), address, io_loop)
        new_channel.connect(address)
        return new_channel

    def accept(self):
        new_sock, addr = self._socket.accept()
        return SocketChannel(new_sock, addr, self._io_loop)

    def connect(self, address):
        self._socket.connect(address)
        self.connecting = True

    def listen(self, address, backlog=128):
        self._socket.bind(address)
        self._socket.listen(backlog)
        self.listening = True

    def connect_socket(socket_channel, address):
        try:
            socket_channel._socket.connect(address)
        except socket.error as ex:
            if _is_connect_error(ex):
                raise

    def has_queued_send(self):
        return self._send_idx < self._send_len

    def recv(self, bufsize):
        return self._socket.recv(bufsize)

    def recv_into(self, buffer, nbytes=0):
        return self._socket.recv_into(buffer, nbytes)

    def send(self, data):
        if self.has_queued_send():
            raise ChannelError('Not yet finished sending the previous data')

        self._send_idx = 0
        self._send_len = len(data)
        self._send_data = data

    def flush(self):
        if self.has_queued_send():
            written = self._socket.send(self._send_data[self._send_idx:])
            self._send_idx += written
        return not self.has_queued_send()

    def closed(self):
        return self._socket is None

    def close(self):
        if not self.closed():
            self._socket.close()
            self._socket = None

        if self._has_handler:
            self.remove_handler()

    def error(self):
        self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)

    def __str__(self):
        return '(fd:{}) SocketChannel(addr:{})'.format(
            self.fileno, self._socket.getsockname())


class ManagedChannel(object):

    def __init__(self, channel):
        self.closing = False
        self.was_reading = False

        self.actual_channel = channel
        self._send_queue = collections.deque()

    def close(self):
        # Try not to close twice
        if not self.closing and not self.closed():
            self.closing = True
            self.disable_reads()

            if self.has_queued_send():
                # We need to flush everything before closing
                self.enable_writes()
            else:
                # If there's nothing left to flush close ASAP
                self.actual_channel.close()

    def release_send_queue(self):
        queue_ref = self._send_queue
        self._send_queue = collections.deque()
        return queue_ref

    def has_queued_send(self):
        return len(self._send_queue) > 0

    def send(self, data):
        if self.closing:
            raise ChannelError('Channel closing. Sends are not allowed at this time')

        self._send_queue.append(data)

    def flush(self):
        flushed = False

        if self.actual_channel.flush():
            if len(self._send_queue) > 0:
                self.actual_channel.send(self._send_queue.popleft())
            else:
                flushed = True
        return flushed

    def __getattr__(self, name):
        if name == 'flush':
            return self.flush
        elif name == 'send':
            return self.send
        elif hasattr(self.actual_channel, name):
            return getattr(self.actual_channel, name)

        return AttributeError('No attribute named: {}.'.format(name))


class ChannelEventRouter(object):

    def __init__(self, event_handler=None, io_loop=None, read_chunk_size=4096):
        self._io_loop = io_loop or ioloop.IOLoop.current()
        self._eh = event_handler or ChannelEventHandler()
        self._read_chunk_size = read_chunk_size

        _THREAD_LOCAL.read_buffer = bytearray(self._read_chunk_size)

    def set_event_handler(self, event_handler):
        self._eh = event_handler

    def register(self, channel):
        mchan = ManagedChannel(channel)

        # This closure makes life a lot easier
        def on_events(fd, events):
            # Read and writes only check to see if the socket has been
            # reclaimed.
            if not mchan.closing and events & READ:
                if mchan.listening:
                    self.on_accept(mchan)
                elif mchan.connecting:
                    self.on_connect(mchan)
                else:
                    self.on_read(mchan)

            if events & WRITE:
                if mchan.connecting:
                    self.on_connect(mchan)
                else:
                    self.on_write_ready(mchan)

            if events & ERROR:
                self._eh.on_error(mchan)

            if mchan.closing and not mchan.has_queued_send():
                self.on_close(mchan)

        # Use our new closure to handle events and initial routing
        channel.set_handler(on_events)

    def on_close(self, channel):
        # Close the actual channel
        channel.actual_channel.close()

        # Let the event handler know that the channel's gone
        self._eh.on_close(channel)

    def on_accept(self, channel):
        new_channel = channel.accept()
        self.register(new_channel)
        self._eh.on_accept(new_channel)

    def on_connect(self, channel):
        self._eh.on_connect(channel)
        channel.connecting = False

    def on_read(self, channel):
        read = _THREAD_LOCAL.read_buffer
        bytes_received = channel.recv_into(read, self._read_chunk_size)

        if bytes_received > 0:
            try:
                self._eh.on_read(channel, read[:bytes_received])
            finally:
                if channel.has_queued_send():
                    # We disable further reads to maintain that writes
                    # happen in a serial manner
                    if channel.reads_enabled():
                        channel.disable_reads()
                        channel.was_reading = True

                    # Process the write chain
                    self.schedule(
                        callback=self._send,
                        channel=channel,
                        send_queue=channel.release_send_queue())
        else:
            # Zero bytes means client hangup
            self.schedule(
                callback=self.on_close,
                channel=channel)

    def on_write_ready(self, channel):
        if channel.flush():
            channel.disable_writes()

            # If reading before sending data out resume reads
            if channel.was_reading:
                channel.was_reading = False
                channel.enable_reads()

    def _send(self, channel, send_queue):
        if len(send_queue) > 0:
            self._eh.on_send(channel, send_queue.popleft())
            self.schedule(
                callback=self._send,
                channel=channel,
                send_queue=send_queue)
        else:
            # We're done processing what was in the queue so let's flush it
            channel.enable_writes()

    def schedule(self, callback, *args, **kwargs):
        """Wrap running callbacks in try/except to allow us to
        close our socket."""

        channel = kwargs['channel']

        if channel is None:
            raise TypeError('Channel argument must be specified for callbacks')

        def _callback_wrapper():
            try:
                # Use a NullContext to ensure that all StackContexts are run
                # inside our blanket exception handler rather than outside.
                with stack_context.NullContext():
                    callback(*args, **kwargs)
            except Exception as ex:
                gen_log.error("Uncaught exception: %s", ex)

                # Close the socket on an uncaught exception from a user callback
                # (It would eventually get closed when the socket object is
                # gc'd, but we don't want to rely on gc happening before we
                # run out of file descriptors)
                channel.close()

                # Re-raise the exception so that IOLoop.handle_callback_exception
                # can see it and log the error
                raise

        # Add the callback
        self._io_loop.add_callback(_callback_wrapper)
