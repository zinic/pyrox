from libc.string cimport strlen
from libc.stdlib cimport malloc, free
from cpython cimport bool, PyBytes_FromStringAndSize, PyBytes_FromString


cdef cbuffer * new_cbuffer(size_hint=0):
    return cbuf_new(size_hint)


cdef class CyclicBuffer(object):

    cdef cbuffer *_buffer

    def __init__(self):
        self._buffer = new_cbuffer()

    def destroy(self):
        if self._buffer != NULL:
            cbuf_free(self._buffer)
            self._buffer = NULL

    def __dealloc__(self):
        self.destroy()

    def available(self):
        return self._buffer.available

    def reset(self):
        cbuf_reset(self._buffer)

    def get(self, length):
        cdef size_t read = 0
        cdef object bytes

        cdef char *dest = <char *>malloc(sizeof(char) * length)

        if dest == NULL:
            raise MemoryError()

        read = cbuf_get(self._buffer, dest, length)
        bytes = PyBytes_FromStringAndSize(dest, read)
        free(dest)

        return bytes

    def put(self, data):
        cdef object strval

        if isinstance(data, str) or isinstance(data, bytes):
            strval = data
        else:
            if isinstance(data, list) or isinstance(data, bytearray):
                strval = str(data)
            else:
                raise Exception('Can not coerce type: {} into str.'.format(
                    type(data)))

        cbuf_put(self._buffer, strval, len(strval))
