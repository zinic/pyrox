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
CLOSE = _EPOLLHUP
ERROR = _EPOLLERR


def _is_connect_error(ex):
    error = ex.args[0]
    return error != errno.EINPROGRESS and error not in _ERRNO_WOULDBLOCK


def _callback_wrapper(callback, *cb_args, **cb_kwargs):
    channel = cb_kwargs.get('channel')

    if channel is None:
        raise TypeError('Channel argument must be set in kwargs')

    try:
        # Use a NullContext to ensure that all StackContexts are run
        # inside our blanket exception handler rather than outside.
        with stack_context.NullContext():
            callback(*cb_args, **cb_kwargs)
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

    def __init__(self):
        self.related = None

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

    def errors_enabled(self):
        raise NotImplementedError()

    def reads_enabled(self):
        raise NotImplementedError()

    def writes_enabled(self):
        raise NotImplementedError()

    def disable_errors(self):
        raise NotImplementedError()

    def disable_reads(self):
        raise NotImplementedError()

    def disable_writes(self):
        raise NotImplementedError()

    def enable_errors(self):
        raise NotImplementedError()

    def enable_reads(self):
        raise NotImplementedError()

    def enable_writes(self):
        raise NotImplementedError()


class FileDescriptorChannel(Channel):

    def __init__(self, fileno, io_loop=None):
        super(FileDescriptorChannel, self).__init__()

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

    def __init__(self, sock, io_loop=None):
        super(SocketChannel, self).__init__(sock.fileno(), io_loop)

        # State tracking
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
        new_channel = SocketChannel.Create(family, io_loop)
        new_channel.bind(address)
        new_channel.listen()

        return new_channel

    @classmethod
    def Connect(cls, address, family=socket.AF_UNSPEC, io_loop=None):
        new_channel = SocketChannel.Create(family, io_loop)
        new_channel.connect(address)

        return new_channel

    @classmethod
    def Create(cls, family=socket.AF_UNSPEC, io_loop=None):
        return SocketChannel(socket.socket(family), io_loop)

    def accept(self):
        new_sock, addr = self._socket.accept()
        return SocketChannel(new_sock, self._io_loop)

    def connect(self, address):
        self.connecting = True

        try:
            self._socket.connect(address)
        except socket.error as ex:
            if _is_connect_error(ex):
                self._socket = None
                raise

        self.enable_writes()

    def bind(self, address):
        self._socket.bind(address)

    def listen(self, backlog=128):
        self._socket.listen(backlog)
        self.listening = True

    def has_queued_send(self):
        return self._send_idx < self._send_len

    def recv(self, bufsize):
        return self._socket.recv(bufsize)

    def recv_into(self, buffer, nbytes=0):
        recieved = 0

        try:
            recieved = self._socket.recv_into(buffer, nbytes)
        except Exception as ex:
            gen_log.exception(ex)

        return recieved

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
        if self.closed():
            raise ChannelError('Channel already closed!')

        self._socket.close()
        self._socket = None

    def error(self):
        return self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)

    def __str__(self):
        return '(fd:{}) SocketChannel(addr:{})'.format(
            self.fileno, self._socket.getsockname())


class ManagedChannel(object):

    slots = ('flush', 'send', 'destroy', 'close', 'closing', 'destroyed',
             '__str__', '_channel', '_send_queue')

    def __init__(self, channel):
        self.closing = False
        self.destroyed = False

        self._channel = channel
        self._send_queue = collections.deque()

    def close(self):
        # Don't attempt to close twice
        if not self.closing:
            self.closing = True

            # Disable reads
            if self._channel.reads_enabled():
                self._channel.disable_reads()

            # Enable writes
            if not self._channel.writes_enabled():
                self._channel.enable_writes()

    def destroy(self):
        if not self.destroyed:
            self.destroyed = True

            # Remove the handle and kill the channel
            self._channel.remove_handler()
            self._channel.close()

    def send(self, data):
        if self.closing is True:
            raise ChannelError(
                'Channel closing. Sends are not allowed at this time')

        # Queue the data
        if not self.has_queued_send():
            self._channel.send(data)
        else:
            self._send_queue.append(data)

        # Mark us ready to write if we haven't done so already
        if not self._channel.writes_enabled():
            self._channel.enable_writes()

    def flush(self):
        flushed = False

        if self._channel.flush():
            if len(self._send_queue) > 0:
                self._channel.send(self._send_queue.popleft())
            else:
                flushed = True

                if self._channel.writes_enabled():
                    self._channel.disable_writes()

        return flushed

    def __getattr__(self, name):
        if name in self.slots:
            return getattr(self, name)
        return getattr(self._channel, name)

    def __str__(self):
        return 'ManagedChannel(wrapped_channel:{})'.format(
            self._channel)


class ChannelEventRouter(object):

    def __init__(self, io_loop=None, read_chunk_size=4096):
        self._io_loop = io_loop or ioloop.IOLoop.current()
        self._read_chunk_size = read_chunk_size

        _THREAD_LOCAL.read_buffer = bytearray(self._read_chunk_size)

    def set_event_handler(self, event_handler):
        self._eh = event_handler
        self._eh.init(self)

    def register(self, channel):
        mchan = ManagedChannel(channel)

        # This closure makes life a lot easier
        def on_events(fd, events):
            # Reads check to see if the socket has been reclaimed.
            if events & READ:
                if mchan.listening:
                    self.on_accept(mchan)
                else:
                    self.on_read(mchan)

            if events & WRITE:
                if mchan.connecting:
                    self.on_connect(mchan)
                else:
                    self.on_write_ready(mchan)

            if events & ERROR:
                self.on_error(mchan)


        # Use our new closure to handle events and initial routing
        channel.set_handler(on_events)

        # Return the new managed channel
        return mchan

    def on_error(self, channel):
        self.schedule(self._eh.on_error, channel=channel)

    def on_close(self, channel):
        # Remove the associated handle now that it's dead
        channel.destroy()

        # Let the event handler know that the channel's gone
        self.schedule(self._eh.on_close, channel=channel)

    def on_accept(self, channel):
        new_channel = self.register(channel.accept())
        self.schedule(self._eh.on_accept, channel=new_channel)

    def on_connect(self, channel):
        channel.connecting = False
        self.schedule(self._eh.on_connect, channel=channel)

    def on_read(self, channel):
        read = _THREAD_LOCAL.read_buffer
        bytes_received = channel.recv_into(read, self._read_chunk_size)

        if bytes_received > 0:
            self._eh.on_read(channel, read[:bytes_received])
        else:
            # Zero bytes means client hangup
            self.on_close(channel)

    def on_write_ready(self, channel):
        if channel.flush():
            # We're done writing for now if flush returns true
            channel.disable_writes()

            if not channel.closing:
                # What does the user program want us to do?
                self.schedule(self._eh.on_send_complete, channel=channel)
            else:
                # Complete the close
                self.on_close(channel)

    def schedule(self, callback, *args, **kwargs):
        """
        Wrap running callbacks in try/except to allow us to gracefully
        handle exceptions and errors that bubble up.
        """
        # Add the callback with our nifty little wrapper stuff beolow
        self._io_loop.add_callback(
            _callback_wrapper,
            callback,
            *args,
            **kwargs)


class SocketChannelServer(object):

    def __init__(self, channel_evrouter, io_loop=None, ssl_options=None):
        self._ssl_options = ssl_options
        self._ce_router = channel_evrouter
        self._io_loop = io_loop or ioloop.IOLoop.current()

    def start(self):
        self._io_loop.start()

    def listen(self, socket):
        channel = SocketChannel(socket, io_loop=self._io_loop)
        channel.listen()

        self._ce_router.register(channel)
        channel.enable_reads()

