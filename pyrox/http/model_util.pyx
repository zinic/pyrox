from cpython.version cimport PY_MAJOR_VERSION
from libc.string cimport strlen


cdef unicode _ustring(s):
    if type(s) is unicode:
        return <unicode>s

    elif PY_MAJOR_VERSION < 3 and isinstance(s, bytes):
        return (<bytes>s).decode('ascii')

    elif isinstance(s, unicode):
        return unicode(s)

    else:
        raise TypeError('Unable to marshal string')


cdef char * _cstr(s):
    cdef unicode ustr = _ustring(s)
    return ustr.encode('utf8')


cdef header_to_bytes(char *name, object values, object bytes):
    bytes.extend(name)
    bytes.extend(b': ')

    if len(values) > 0:
        bytes.extend(values[0])

    for value in values[1:]:
        bytes.extend(b', ')
        bytes.extend(value)

    bytes.extend(b'\r\n')


cdef headers_to_bytes(object headers, object bytes):
    cdef int needs_content_length = True
    cdef int has_transfer_encoding = False

    for name, header in headers.items():
        if needs_content_length and name == 'content-length':
            needs_content_length = False

        if not has_transfer_encoding and name == 'transfer-encoding':
            has_transfer_encoding = True

        header_to_bytes(header.name, header.values, bytes)

    if needs_content_length and not has_transfer_encoding:
        header_to_bytes('Content-Length', '0', bytes)

    bytes.extend(b'\r\n')


def request_to_bytes(object http_request):
    bytes = bytearray()
    bytes.extend(http_request.method)
    bytes.extend(b' ')
    bytes.extend(http_request.url)
    bytes.extend(b' HTTP/')
    bytes.extend(http_request.version)
    bytes.extend(b'\r\n')
    headers_to_bytes(http_request.headers, bytes)
    return str(bytes)


def response_to_bytes(object http_response):
    bytes = bytearray()
    bytes.extend(b'HTTP/')
    bytes.extend(http_response.version)
    bytes.extend(b' ')
    bytes.extend(http_response.status)
    bytes.extend(b'\r\n')
    headers_to_bytes(http_response.headers, bytes)
    return str(bytes)
