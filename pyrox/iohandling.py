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


class ChannelError(IOError):
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


def _is_connect_error(ex):
    error = ex.args[0]
    return error != errno.EINPROGRESS and error not in _ERRNO_WOULDBLOCK


def watch_channel(channel, event_handler):
    handler = ChannelHandler(channel, event_handler)
    channel.set_handler(handler.on_events)

    return handler

def connect_ssl_socket(socket_channel, address,
        ssl_options=None, server_hostname=None):
    # Wrap the socket using the Pyhton SSL socket library
    socket_channel._socket = ssl_wrap_socket(
        socket=self._socket,
        ssl_options=self._ssl_options,
        server_hostname=self._server_hostname,
        do_handshake_on_connect=False)

    connect_socket(socket_channel, address)


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


class BufferedChannel(object):

    def __init__(self, channel):
        self.actual_channel = channel
        self._send_queue = collections.deque()

    def release_send_queue(self):
        queue_ref = self._send_queue
        self._send_queue = collections.deque()

        return queue_ref

    def has_queued_send(self):
        return len(self._send_queue) > 0

    def send(self, data):
        self._send_queue.append(data)

    def flush(self):
        flushed = False

        if self.actual_channel.flush():
            if len(self._send_queue) > 0:
                self.actual_channel.send(self._send_queue.popleft())
                flushed = self.actual_channel.flush()
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


class ChannelHandler(object):

    def __init__(self, channel, event_handler, recv_chunk_size=4096):
        # Channel init
        self.channel = BufferedChannel(channel)

        # Create a reference to the event handler
        self._event_handler = event_handler

    def on_events(self, fd, events):
        # Read and writes only check to see if the socket has been
        # reclaimed.
        if events & READ:
            if self.channel.listening:
                self._event_handler.on_accept(self.channel.accept())
            else:
                self._event_handler.on_read_ready(self.channel)

        if events & WRITE:
            if self.channel.connecting:
                self._event_handler.on_connect(self.channel)
                self.channel.connecting = False
            else:
                self._event_handler.on_write_ready(self.channel)

        if events & ERROR:
            self._event_handler.on_error(self.channel)


class ChannelCodec(object):

    def on_data(self, channel, data):
        pass


class ChannelCodecPipeline(object):

    def __init__(self, upstream_codecs=None, downstream_codecs=None):
        self.upstream = upstream_codecs or tuple()
        self.downstream = downstream_codecs or tuple()


class EventHandler(object):

    def __init__(self, io_loop=None, read_chunk_size=4096):
        self._io_loop = io_loop or ioloop.IOLoop.current()

        self._delegate = None

        self._codecs = ChannelCodecPipeline()
        self._send_queue = None

        self._read_chunk_size = read_chunk_size
        self._was_reading = False

        _THREAD_LOCAL.read_buffer = bytearray(self._read_chunk_size)

    def set_codec_pipeline(self, codec_pipeline):
        self._codecs = codec_pipeline

    def on_accept(self, channel):
        pass

    def on_close(self, channel):
        pass

    def on_error(self, channel):
        pass

    def on_connect(self, channel):
        pass

    def on_read_ready(self, channel):
        recv_buffer = _THREAD_LOCAL.read_buffer
        bytes_received = channel.recv_into(
            recv_buffer, self._read_chunk_size)

        if bytes_received > 0:
            self._add_callback(self._on_read, channel,
                recv_buffer[:bytes_received], 0)
        else:
            self._add_callback(self.on_close, channel)

    """
    TODO:Enhancement - pass along the codec pipeline so we don't rely on the
    reference stored within the class. This would allow the class' version
    of the codec pipeline to change without interrupting what is already
    being processed.
    """
    def _on_read(self, channel, message, codec_idx):
        """Process through the downstream (read) codec pipeline"""
        read_codecs = self._codecs.downstream

        # Check if another codec is awaiting processing
        if codec_idx < len(read_codecs):
            try:
                result = read_codecs[codec_idx].on_data(channel, message)

                # Results are passed down the codec pipeline. Any resulut
                # that is not None is assumed to imply that the result
                # should be passed along and that codec pipeline
                # processing may continue
                if result is not None:
                    self._add_callback(self._on_read, channel,
                        result, codec_idx + 1)
                    return
            except Exception as ex:
                gen_log.error('Failure on codec({}) - {}'.format(
                    codec_idx, ex))

        if channel.has_queued_send():
            # We disable further reads to maintain that writes happen in a
            # serial manner
            if channel.reads_enabled():
                channel.disable_reads()
                self._was_reading = True

            # Process the write chain
            self._add_callback(self._process_send_queue, channel,
                channel.release_send_queue())

    def on_write_ready(self, channel):
        if channel.flush():
            channel.disable_writes()

            if self._was_reading:
                self._was_reading = False
                channel.enable_reads()

    def _process_send_queue(self, channel, send_queue):
        if len(send_queue) > 0:
            self._process_message(channel, send_queue, send_queue.popleft())
        else:
            channel.enable_writes()

    def _process_message(self, channel, send_queue, message, codec_idx=0):
        write_codecs = self._codecs.upstream

        if codec_idx < len(write_codecs):
            try:
                result = write_codecs[codec_idx].on_data(channel, message)

                # Results are passed down the codec pipeline
                if result is not None:
                    self._add_callback(self._process_message, channel,
                        send_queue, result, codec_idx + 1)
                    return
            except Exception as ex:
                gen_log.error('Failure on codec({}) - {}'.format(
                    codec_idx, ex))

        if message is not None:
            channel.send(message)

        self._add_callback(self._process_send_queue, channel, send_queue)

    def _add_callback(self, callback, *args, **kwargs):
        """Wrap running callbacks in try/except to allow us to
        close our socket."""

        # TODO: Find a better way to do this
        channel = args[0]

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
