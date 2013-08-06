from cpython cimport bool
from libc.string cimport strlen

cdef char * HOST = 'host'

cdef bool strs_equal(char *src, char *expected, int length):
    cdef int index = 0
    cdef char lower
    while index < length:
        lower = (src[index] | 0x20)
        if lower != expected[index]:
            return False
    return True

def is_host(char *name):
    return strs_equal(name, HOST, strlen(name))

def header_to_bytes(char *name, object values, object bytes):
    bytes.extend(name)
    bytes.extend(b': ')

    if len(values) > 0:
        bytes.extend(values[0])

    for value in values[1:]:
        bytes.extend(b', ')
        bytes.extend(value)
    bytes.extend(b'\r\n')

def headers_to_bytes(object headers, object bytes):
    for header in headers:
        header_to_bytes(header.name, header.values, bytes)
    bytes.extend(b'\r\n')

def request_to_bytes(object http_request):
    bytes = bytearray()
    bytes.extend(http_request.method)
    bytes.extend(b' ')
    bytes.extend(http_request.url)
    bytes.extend(b' HTTP/')
    bytes.extend(http_request.version)
    bytes.extend(b'\r\n')
    headers_to_bytes(http_request.headers.values(), bytes)
    return str(bytes)

def response_to_bytes(object http_response):
    bytes = bytearray()
    bytes.extend(b'HTTP/')
    bytes.extend(http_response.version)
    bytes.extend(b' ')
    bytes.extend(http_response.status_code)
    bytes.extend(b' -\r\n')
    headers_to_bytes(http_response.headers.values(), bytes)
    return str(bytes)
