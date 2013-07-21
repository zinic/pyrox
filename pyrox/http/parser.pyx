from libc.stdlib cimport malloc, free

from cpython cimport bool, PyBytes_FromStringAndSize, PyBytes_FromString


class ParserDelegate(object):

    def on_status(self, status_code):
        pass

    def on_req_method(self, method):
        pass

    def on_url(self, url):
        pass

    def on_header(self, name, value):
        pass

    def on_headers_complete(self):
        pass

    def on_body_begin(self):
        pass

    def on_body(self, bytes):
        pass

    def on_body_complete(self):
        pass


cdef size_t MAX_BUFFER_SIZE = 8192


ctypedef struct c_buffer:
    char *bytes
    size_t position


cdef allocate_buffer(size_t size_hint):
    cdef c_buffer new_buf
    new_buf.bytes = <char *>malloc(sizeof(char) * size_hint)


cdef void copy(char *source, char *dest, size_t dest_offset, size_t length):
    cdef size_t pos = 0
    while pos < length:
        dest[dest_offset + pos] = source[pos]
        pos += 1


cdef int append_to(c_buffer buf, char *source, size_t length):
    if c_buffer.position + length < MAX_BUFFER_SIZE:
        copy(source, buf.bytes, buf.position, length)
        return 0
    return -1


cdef class ParserBuffer(object):

    cdef CBuffer buf

    def __cinit__(self):
        self.buf.buffer_ptr = <char *>malloc(sizeof(char) * MAX_BUFFER_SIZE)
        self.buf.position = 0

    def __dealoc__(self):
        if self.buffer_ptr is not NULL:
            free(self.buffer_ptr)


cdef class HttpRequestParser(object):

    cdef c_buffer buf

    def __cinit__(self):
        self.buffer_ptr = <char *>malloc(sizeof(char) * MAX_BUFFER_SIZE)
        self.position = 0

    def __dealoc__(self):
        if self.buffer_ptr is not NULL:
            free(self.buffer_ptr)

    cdef int append(self, char *source, size_t length):
        if self.position + length < MAX_BUFFER_SIZE:
            copy(source, self.buffer_ptr, self.position, length)
            return 0
        return -1
