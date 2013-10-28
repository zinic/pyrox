from __future__ import absolute_import, division, print_function, with_statement

import collections
import errno
import numbers
import os
import socket
import ssl
import sys
import re

from tornado import ioloop
from tornado.log import gen_log, app_log
from tornado.netutil import ssl_wrap_socket, ssl_match_hostname,\
    SSLCertificateError
from tornado import stack_context
from tornado.util import bytes_type

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

_ONE_MILLISECOND = timedelta(milliseconds=1)

_READ_CHUNK_SIZE = 4096


class StreamClosedError(IOError):
    """Exception raised by `IOStream` methods when the stream is closed.

    Note that the close callback is scheduled to run *after* other
    callbacks on the stream (to allow for buffered data to be processed),
    so you may see this error before you see the close callback.
    """
    pass


class IOHandler(object):

    def __init__(self, sock, event_loop=None, recv_chunk_size=4096):
        # Error tracking
        self.error = 0

        # Socket init
        self._socket = sock
        self._sfileno = sock.fileno()

        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setblocking(0)

        # Bind to the eventloop
        self._event_loop = event_loop or ioloop.IOLoop.current()

        # Flow control vars
        self._connecting = False
        self._closing = False

        # Callbacks
        self._on_connect_cb = None
        self._close_cb = None
        self._recv_cb = None
        self._send_complete_cb = None
        self._error_cb = None

        # Sending and receiving management
        self._last_send_idx = 0
        self._send_queue = collections.deque()

        self._recv_chunk_size = recv_chunk_size
        self._recv_buffer = bytearray(self._recv_chunk_size)

        # Mark our initial interests
        self._init_event_interest(self._event_loop.ERROR)

    def stop_recv(self):
        """
        Alias for removing the read interest from the event handler.
        """
        if not self._closing:
            gen_log.debug('Halting recv events for stream(fd:{})'.format(
                self._sfileno))
            self._drop_event_interest(self._event_loop.READ)

    def stop_send(self):
        """
        Alias for removing the send interest from the event handler.
        """
        if not self._closing:
            gen_log.debug('Halting send events for stream(fd:{})'.format(
                self._sfileno))
            self._drop_event_interest(self._event_loop.WRITE)

    def resume_recv(self):
        """
        Alias for adding the read interest to the event handler.
        """
        if not self._closing:
            gen_log.debug('Resuming recv events for stream(fd:{})'.format(
                self._sfileno))
            self._add_event_interest(self._event_loop.READ)

    def resume_send(self):
        """
        Alias for adding the send interest to the event handler.
        """
        if not self._closing:
            gen_log.debug('Resuming send events for stream(fd:{})'.format(
                self._sfileno))
            self._add_event_interest(self._event_loop.WRITE)

    def on_recv(self, callback):
        """
        Sets a callback for read events and then sets the read interest on
        the event handler.
        """
        self._check_closed()

        if not self._closing:
            assert callback is None or callable(callback)
            self._recv_cb = stack_context.wrap(callback)
            self.resume_recv()

    def on_send_complete(self, callback=None):
        """
        Sets a callback for completed send events and then sets the send
        interest on the event handler.
        """
        if not self._closing:
            assert callback is None or callable(callback)
            self._send_complete_cb = stack_context.wrap(callback)

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

    def receiving(self):
        """Returns True if we are currently receiving from the stream."""
        return self._event_interest & self._event_loop.READ

    def sending(self):
        """Returns True if we are currently sending to the stream."""
        return len(self._send_queue) > 0

    def closed(self):
        return self._closing or self._socket is None

    def send(self, msg, callback=None):
        self._check_closed()

        if not isinstance(msg, basestring) and not isinstance(msg, bytearray):
            raise TypeError("bytes/bytearray/unicode/str objects only")

        self._send_queue.append(msg)
        self.on_send_complete(callback)
        self.resume_send()

    def connect(self, address, callback=None, server_hostname=None):
        self._connecting = True

        try:
            self._socket.connect(address)
        except socket.error as e:
            if (e.args[0] != errno.EINPROGRESS and e.args[0] not in _ERRNO_WOULDBLOCK):
                gen_log.warning("Connect error on fd %d: %s", self._sfileno, e)
                self.close()
                return

        self._on_connect_cb = stack_context.wrap(callback)
        self._add_event_interest(self._event_loop.WRITE)

    def close(self):
        if not self._closing:
            if self.sending():
                self.on_send_complete(self._close)
            else:
                self._close()

            self._closing = True

    def _close(self):
        """Close this stream."""
        if self._socket is not None:
            gen_log.debug('Closing stream(fd: {})'.format(self._sfileno))

            self._event_loop.remove_handler(self._sfileno)
            self._event_loop.add_timeout(100, self._socket.close)
            self._socket = None

            if self._close_cb:
                self._run_callback(self._close_cb)

    def _check_closed(self):
        if self._socket is None:
            raise StreamClosedError('Stream closing or closed.')

    def _do_recv(self, recv_buffer):
        return self._socket.recv_into(recv_buffer, self._recv_chunk_size)

    def _do_send(self, send_buffer):
        return self._socket.send(send_buffer)

    def _handle_events(self, fd, events):
        if self._socket is None:
            gen_log.warning("Got events for closed stream %d", fd)
            return
        try:
            if self._socket is not None and events & self._event_loop.READ:
                self._handle_recv()

            if self._socket is not None and events & self._event_loop.WRITE:
                if self._connecting:
                    self._handle_connect()
                else:
                    self._handle_send()

            if not self.closed() and events & self._event_loop.ERROR:
                self._handle_error(
                    self._socket.getsockopt(
                        socket.SOL_SOCKET, socket.SO_ERROR))
        except Exception:
            self.close()
            raise

    def _handle_error(self, error):
        try:
            if self._error_cb is not None:
                callback = self._error_cb
                self._error_cb = None
                self._run_callback(callback, error)

            if error not in _ERRNO_CONNRESET:
                gen_log.warning("Error on stream(fd:%d) caught: %s",
                    self._sfileno, errno.errorcode[error])
        finally:
            # On error, close the FD
            self.close()

    def _handle_recv(self):
        try:
#           self._event_loop.add_callback(self._handle_recv)
            read = self._do_recv(self._recv_buffer)

            if read is not None:
                if read > 0 and self._recv_cb:
                    self._run_callback(self._recv_cb, self._recv_buffer[:read])
                elif read == 0:
                    self.close()
        except (socket.error, IOError, OSError) as ex:
                if ex.args[0] not in _ERRNO_WOULDBLOCK:
                    self._handle_error(ex.args[0])

    def _handle_send(self):
        if not self.sending():
            if self._send_complete_cb:
                callback = self._send_complete_cb
                self._send_complete_cb = None
                self._run_callback(callback)
            self.stop_send()
            return

        sent = None

        try:
            while len(self._send_queue) > 0:
                msg = self._send_queue.popleft()
                sent = self._do_send(msg[self._last_send_idx:])

                if (len(msg) - self._last_send_idx) == sent:
                    self._last_send_idx = 0
                else:
                    self._send_queue.appendleft(msg)
                    self._last_send_idx += sent
        except (socket.error, IOError, OSError) as ex:
            if ex.args[0] in _ERRNO_WOULDBLOCK:
                self._send_queue.appendleft(msg)
            else:
                self._handle_error(ex.args[0])

    def _handle_connect(self):
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

    def _add_event_interest(self, event_interest):
        """Add io_state to poller."""
        if not self._event_interest & event_interest:
            self._event_interest = self._event_interest | event_interest
            self._update_handler(self._event_interest)

    def _drop_event_interest(self, event_interest):
        """Stop poller from watching an io_state."""
        if self._event_interest & event_interest:
            self._event_interest = self._event_interest & (~event_interest)
            self._update_handler(self._event_interest)

    def _update_handler(self, event_interest):
        """Update IOLoop handler with event_interest."""
        if self._socket is None:
            return

        self._event_loop.update_handler(
            self._sfileno, event_interest)

    def _init_event_interest(self, event_interest):
        self._event_interest = event_interest
        """initialize the ioloop event handler"""
        with stack_context.NullContext():
            self._event_loop.add_handler(
                self._sfileno,
                self._handle_events,
                self._event_interest)


class SSLIOHandler(IOHandler):
    """A utility class to write to and read from a non-blocking SSL socket.

    If the socket passed to the constructor is already connected,
    it should be wrapped with::

    ssl.wrap_socket(sock, do_handshake_on_connect=False, **kwargs)

    before constructing the `SSLIOHandler`. Unconnected sockets will be
    wrapped when `SSLIOHandler.connect` is finished.
    """
    def __init__(self, *args, **kwargs):
        """The ``ssl_options`` keyword argument may either be a dictionary
        of keywords arguments for `ssl.wrap_socket`, or an `ssl.SSLContext`
        object.
        """
        self._ssl_options = kwargs.pop('ssl_options', {})
        super(SSLIOHandler, self).__init__(*args, **kwargs)
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
            self._add_event_interest(self._event_loop.WRITE)

    def reading(self):
        return self._handshake_reading or super(SSLIOHandler, self).reading()

    def writing(self):
        return self._handshake_writing or super(SSLIOHandler, self).writing()

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
                                self._sfileno, peer, err)
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

    def _handle_recv(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
            return
        super(SSLIOHandler, self)._handle_recv()

    def _handle_send(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
            return
        super(SSLIOHandler, self)._handle_send()

    def connect(self, address, callback=None, server_hostname=None):
        # Save the user's callback and run it after the ssl handshake
        # has completed.
        self._ssl_on_connect_cb = stack_context.wrap(callback)
        self._server_hostname = server_hostname
        super(SSLIOHandler, self).connect(address, callback=None)

    def _handle_connect(self):
        # When the connection is complete, wrap the socket for SSL
        # traffic. Note that we do this by overriding _handle_connect
        # instead of by passing a callback to super().connect because
        # user callbacks are enqueued asynchronously on the IOLoop,
        # but since _handle_events calls _handle_connect immediately
        # followed by _handle_write we need this to be synchronous.
        self._socket = ssl_wrap_socket(self._socket, self._ssl_options,
                                      server_hostname=self._server_hostname,
                                      do_handshake_on_connect=False)
        super(SSLIOHandler, self)._handle_connect()

    def _do_recv(self, recv_buffer):
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

    def _do_send(self, send_buffer):
        return self._socket.send(send_buffer)
