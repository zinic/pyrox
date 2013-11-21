from __future__ import absolute_import, division, print_function,\
    with_statement

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


class StreamClosedError(IOError):
    """Exception raised by `IOStream` methods when the stream is closed.

    Note that the close callback is scheduled to run *after* other
    callbacks on the stream (to allow for buffered data to be processed),
    so you may see this error before you see the close callback.
    """
    pass


class WriteQueue(object):

    def __init__(self):
        self._last_send_idx = 0
        self._write_queue = collections.deque()

    def has_next(self):
        return len(self._write_queue) > 0

    def next(self):
        if self.has_next():
            return (self._write_queue[0], self._last_send_idx)
        return None

    def clear(self):
        self._write_queue.clear()

    def append(self, src):
        self._write_queue.append(src)

    def advance(self, bytes_to_advance):
        next_src = self._write_queue[0]

        if bytes_to_advance + self._last_send_idx >= len(next_src):
            self._write_queue.popleft()
            self._last_send_idx = 0
        else:
            self._last_send_idx += bytes_to_advance


class IOHandler(object):

    def __init__(self, io_loop=None):
        # Bind to the eventloop
        self._io_loop = io_loop or ioloop.IOLoop.current()

        # Error tracking
        self.error = 0

        # Callbacks
        self._connect_cb = None
        self._close_cb = None
        self._read_cb = None
        self._write_cb = None

        # TODO:Review - Is this a good idea?
        self._error_cb = None

    def reading(self):
        raise NotImplementedError()

    def writing(self):
        raise NotImplementedError()

    def closed(self):
        raise NotImplementedError()

    def read(self, callback):
        raise NotImplementedError()

    def write(self, src, callback=None):
        raise NotImplementedError()

    def connect(self, address, callback=None):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()


class FileDescriptorHandle(object):

    def __init__(self, fd, io_loop):
        assert fd is not None
        assert io_loop is not None

        self.fd = fd
        self._io_loop = io_loop
        self._event_interest = None

    def is_reading(self):
        return self._event_interest & self._io_loop.READ

    def is_writing(self):
        return self._event_interest & self._io_loop.WRITE

    def set_handler(self, event_handler):
        """initialize the ioloop event handler"""
        assert event_handler is not None and callable(event_handler)
        self._event_interest = self._io_loop.ERROR

        with stack_context.NullContext():
            self._io_loop.add_handler(
                self.fd,
                event_handler,
                self._event_interest)

    def remove_handler(self):
        self._io_loop.remove_handler(self.fd)

    def disable_reading(self):
        """
        Alias for removing the read interest from the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Halting read events for stream(fd:{})'.format(
                self.fd))
        self._drop_event_interest(self._io_loop.READ)

    def disable_writing(self):
        """
        Alias for removing the send interest from the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Halting write events for stream(fd:{})'.format(
                self.fd))
        self._drop_event_interest(self._io_loop.WRITE)

    def resume_reading(self):
        """
        Alias for adding the read interest to the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Resuming recv events for stream(fd:{})'.format(
                self.fd))
        self._add_event_interest(self._io_loop.READ)

    def resume_writing(self):
        """
        Alias for adding the send interest to the event handler.
        """
        if _SHOULD_LOG_DEBUG_OUTPUT:
            gen_log.debug('Resuming send events for stream(fd:{})'.format(
                self.fd))
        self._add_event_interest(self._io_loop.WRITE)

    def _add_event_interest(self, event_interest):
        """Add io_state to poller."""
        if not self._event_interest & event_interest:
            self._event_interest = self._event_interest | event_interest
            self._io_loop.update_handler(self.fd, self._event_interest)

    def _drop_event_interest(self, event_interest):
        """Stop poller from watching an io_state."""
        if self._event_interest & event_interest:
            self._event_interest = self._event_interest & (~event_interest)
            self._io_loop.update_handler(self.fd, self._event_interest)


class SocketIOHandler(IOHandler):

    def __init__(self, sock, io_loop=None, recv_chunk_size=4096):
        super(SocketIOHandler, self).__init__(io_loop)

        # Socket init
        self._socket = sock

        # Set socket options
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setblocking(0)

        # Initialize our handling of the FD events
        self.handle = FileDescriptorHandle(self._socket.fileno(), self._io_loop)
        self.handle.set_handler(self._handle_events)

        # Flow control vars
        self._connecting = False
        self._closing = False

        # Writing and reading management
        self._write_queue = WriteQueue()

        self._recv_chunk_size = recv_chunk_size
        self._recv_buffer = bytearray(self._recv_chunk_size)

    def on_done_writing(self, callback=None):
        """
        Sets a callback for completed send events and then sets the send
        interest on the event handler.
        """
        if not self._closing:
            assert callback is None or callable(callback)
            self._write_cb = stack_context.wrap(callback)

    def on_close(self, callback):
        """
        Sets a callback to be called after this stream closes.
        """
        if not self._closing:
            assert callback is None or callable(callback)
            self._close_cb = stack_context.wrap(callback)

    def on_error(self, callback):
        """
        Sets a callback to be called after this stream closes.
        """
        if not self._closing:
            assert callback is None or callable(callback)
            self._error_cb = stack_context.wrap(callback)

    def reading(self):
        """Returns True if we are currently receiving from the stream."""
        return not self.closed() and self.handle.is_reading()

    def writing(self):
        """Returns True if we are currently writing to the stream."""
        return not self.closed() and self._write_queue.has_next()

    def closed(self):
        return self._closing or self._socket is None

    def read(self, callback):
        """
        Sets a callback for read events and then sets the read interest on
        the event handler.
        """
        self._assert_not_closed()

        assert callback is None or callable(callback)
        self._read_cb = stack_context.wrap(callback)
        self.handle.resume_reading()

    def write(self, msg, callback=None):
        self._assert_not_closed()

        if not isinstance(msg, basestring) and not isinstance(msg, bytearray):
            raise TypeError("bytes/bytearray/unicode/str objects only")

        # Append the data for writing - this should not copy the data
        self._write_queue.append(msg)
        # Enable writing on the FD
        self.handle.resume_writing()
        # Set our callback - writing None to the method below is okay
        self.on_done_writing(callback)

    def connect(self, address, callback=None):
        self._connecting = True

        try:
            self._socket.connect(address)
        except socket.error as e:
            if (e.args[0] != errno.EINPROGRESS and e.args[0] not in _ERRNO_WOULDBLOCK):
                gen_log.warning("Connect error on fd %d: %s", self.handle.fd, e)
                self.close()
                return

        self._on_connect_cb = stack_context.wrap(callback)
        self.handle.resume_writing()

    def close(self):
        if not self._closing:
            if self._write_queue.has_next():
                self.on_done_writing(self._close)
            else:
                self._close()

            self._closing = True

    def _close(self):
        """Close this stream."""
        if self._socket is not None:
            gen_log.debug('Closing stream(fd: {})'.format(self.handle.fd))

            self.handle.remove_handler()

            self._socket.close()
            self._socket = None

            if self._close_cb:
                self._run_callback(self._close_cb)

    def _assert_not_closed(self):
        if self.closed():
            raise StreamClosedError('Stream closing or closed.')

    def _do_read(self, recv_buffer):
        return self._socket.recv_into(recv_buffer, self._recv_chunk_size)

    def _do_write(self, send_buffer):
        return self._socket.send(send_buffer)

    def _handle_events(self, fd, events):
        #gen_log.debug('Handle event for stream(fd: {})'.format(self.handle.fd))

        if self._socket is None:
            gen_log.warning("Got events for closed stream %d", fd)
            return

        try:
            if self._socket is not None and events & self._io_loop.READ:
                self.handle_read()

            if self._socket is not None and events & self._io_loop.WRITE:
                if self._connecting:
                    self.handle_connect()
                else:
                    self.handle_write()

            if not self.closed() and events & self._io_loop.ERROR:
                self.handle_error(
                    self._socket.getsockopt(
                        socket.SOL_SOCKET, socket.SO_ERROR))
        except Exception:
            self.close()
            raise

    def handle_error(self, error):
        try:
            if self._error_cb is not None:
                callback = self._error_cb
                self._error_cb = None
                self._run_callback(callback, error)

            if error not in _ERRNO_CONNRESET:
                gen_log.warning("Error on stream(fd:%d) caught: %s",
                                self.handle.fd, errno.errorcode[error])
        finally:
            # On error, close the FD
            self.close()

    def handle_read(self):
        try:
            read = self._do_read(self._recv_buffer)

            if read is not None:
                if read > 0 and self._read_cb:
                    self._run_callback(self._read_cb, self._recv_buffer[:read])
                elif read == 0:
                    self.close()
        except (socket.error, IOError, OSError) as ex:
                if ex.args[0] not in _ERRNO_WOULDBLOCK:
                    self.handle_error(ex.args[0])

    def handle_write(self):
        if self._write_queue.has_next():
            try:
                msg = None

                while self._write_queue.has_next():
                    msg, offset = self._write_queue.next()
                    sent = self._do_write(msg[offset:])
                    self._write_queue.advance(sent)
            except (socket.error, IOError, OSError) as ex:
                if ex.args[0] in _ERRNO_WOULDBLOCK:
                    self._write_queue.appendleft(msg)
                else:
                    self._write_queue.clear()
                    self.handle_error(ex.args[0])
        else:
            self.handle.disable_writing()

            if self._write_cb:
                callback = self._write_cb
                self._write_cb = None
                self._run_callback(callback)

    def handle_connect(self):
        if self._on_connect_cb is not None:
            callback = self._on_connect_cb
            self._on_connect_cb = None
            self._run_callback(callback)

        self._connecting = False

    def _run_callback(self, callback, *args, **kwargs):
        """Wrap running callbacks in try/except to allow us to
        close our socket."""

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
            self.close()

            # Re-raise the exception so that IOLoop.handle_callback_exception
            # can see it and log the error
            raise


class SSLSocketIOHandler(SocketIOHandler):
    """A utility class to write to and read from a non-blocking SSL socket.

    If the socket passed to the constructor is already connected,
    it should be wrapped with::

    ssl.wrap_socket(sock, do_handshake_on_connect=False, **kwargs)

    before constructing the `SSLSocketIOHandler`. Unconnected sockets will be
    wrapped when `SSLSocketIOHandler.connect` is finished.
    """
    def __init__(self, *args, **kwargs):
        """The ``ssl_options`` keyword argument may either be a dictionary
        of keywords arguments for `ssl.wrap_socket`, or an `ssl.SSLContext`
        object.
        """
        self._ssl_options = kwargs.pop('ssl_options', {})
        super(SSLSocketIOHandler, self).__init__(*args, **kwargs)
        self._ssl_accepting = True
        self._handshake_reading = False
        self._handshake_writing = False
        self._ssl_on_connect_cb = None
        self._server_hostname = None

        # If the socket is already connected, attempt to start the handshake.
        try:
            self._socket.getpeername()
        except socket.error:
            pass
        else:
            # Indirectly start the handshake, which will run on the next
            # IOLoop iteration and then the real IO event_interest will be set in
            # _handle_events.
            self.handle.resume_writing()

    def reading(self):
        return self._handshake_reading or super(SSLSocketIOHandler, self).reading()

    def writing(self):
        return self._handshake_writing or super(SSLSocketIOHandler, self).writing()

    def _do_ssl_handshake(self):
        # Based on code from test_ssl.py in the python stdlib
        try:
            self._handshake_reading = False
            self._handshake_writing = False
            self._socket.do_handshake()
        except ssl.SSLError as err:
            if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                self._handshake_reading = True
                return
            elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                self._handshake_writing = True
                return
            elif err.args[0] in (ssl.SSL_ERROR_EOF,
                                 ssl.SSL_ERROR_ZERO_RETURN):
                self.close()
                return
            elif err.args[0] == ssl.SSL_ERROR_SSL:
                try:
                    peer = self._socket.getpeername()
                except Exception:
                    peer = '(not connected)'
                gen_log.warning("SSL Error on %d %s: %s",
                                self.handle.fd, peer, err)
                self.close()
                return
            raise
        except socket.error as err:
            if err.args[0] in _ERRNO_CONNRESET:
                self.close()
                return
        except AttributeError:
            # On Linux, if the connection was reset before the call to
            # wrap_socket, do_handshake will fail with an
            # AttributeError.
            self.close()
            return
        else:
            self._ssl_accepting = False
            if not self._verify_cert(self._socket.getpeercert()):
                self.close()
                return
            if self._ssl_on_connect_cb is not None:
                callback = self._ssl_on_connect_cb
                self._ssl_on_connect_cb = None
                self._run_callback(callback)

    def _verify_cert(self, peercert):
        """Returns True if peercert is valid according to the configured
        validation mode and hostname.

        The ssl handshake already tested the certificate for a valid
        CA signature; the only thing that remains is to check
        the hostname.
        """
        if isinstance(self._ssl_options, dict):
            verify_mode = self._ssl_options.get('cert_reqs', ssl.CERT_NONE)
        elif isinstance(self._ssl_options, ssl.SSLContext):
            verify_mode = self._ssl_options.verify_mode

        assert verify_mode in (ssl.CERT_NONE, ssl.CERT_REQUIRED, ssl.CERT_OPTIONAL)

        if verify_mode == ssl.CERT_NONE or self._server_hostname is None:
            return True
        cert = self._socket.getpeercert()
        if cert is None and verify_mode == ssl.CERT_REQUIRED:
            gen_log.warning("No SSL certificate given")
            return False
        try:
            ssl_match_hostname(peercert, self._server_hostname)
        except SSLCertificateError:
            gen_log.warning("Invalid SSL certificate", )
            return False
        else:
            return True

    def handle_read(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
        else:
            super(SSLSocketIOHandler, self).handle_read()

    def handle_write(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
        else:
            super(SSLSocketIOHandler, self).handle_write()

    def connect(self, address, callback=None, server_hostname=None):
        # Save the user's callback and run it after the ssl handshake
        # has completed.
        self._ssl_on_connect_cb = stack_context.wrap(callback)
        self._server_hostname = server_hostname

        super(SSLSocketIOHandler, self).connect(address, callback=None)

    def handle_connect(self):
        # When the connection is complete, wrap the socket for SSL
        # traffic. Note that we do this by overriding handle_connect
        # instead of by passing a callback to super().connect because
        # user callbacks are enqueued asynchronously on the IOLoop,
        # but since _handle_events calls handle_connect immediately
        # followed by handle_write we need this to be synchronous.
        self._socket = ssl_wrap_socket(self._socket, self._ssl_options,
                                       server_hostname=self._server_hostname,
                                       do_handshake_on_connect=False)
        super(SSLSocketIOHandler, self).handle_connect()

    def _do_read(self, recv_buffer):
        if self._ssl_accepting:
            # If the handshake hasn't finished yet, there can't be anything
            # to read (attempting to read may or may not raise an exception
            # depending on the SSL version)
            return -1

        try:
            bytes = self._socket.read(self._recv_chunk_size)
            read = len(bytes)
            recv_buffer[:read] = bytes

            return read
        except ssl.SSLError as e:
            # SSLError is a subclass of socket.error, so this except
            # block must come first.
            if e.args[0] == ssl.SSL_ERROR_WANT_READ:
                return -1
            else:
                raise

    def _do_write(self, send_buffer):
        return self._socket.send(send_buffer)
