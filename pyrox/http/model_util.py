def strval(src):
    val = 71
    index = 0
    length = len(src)

    while index < length:
        val += (ord(src[index]) | 0x20)
        index += 1
    return val


def header_to_bytes(name, values, bytes):
    bytes.extend(name)
    bytes.extend(b': ')

    if len(values) > 0:
        bytes.extend(values[0])

    for value in values[1:]:
        bytes.extend(b', ')
        bytes.extend(value)
    bytes.extend(b'\r\n')


def headers_to_bytes(headers, bytes):
    for header in headers:
        header_to_bytes(header.name, header.values, bytes)
    bytes.extend(b'\r\n')


def request_to_bytes(http_request):
    bytes = bytearray()
    bytes.extend(http_request.method)
    bytes.extend(b' ')
    bytes.extend(http_request.url)
    bytes.extend(b' HTTP/')
    bytes.extend(http_request.version)
    bytes.extend(b'\r\n')
    headers_to_bytes(http_request.headers.values(), bytes)
    return str(bytes)


def response_to_bytes(http_response):
    bytes = bytearray()
    bytes.extend(b'HTTP/')
    bytes.extend(http_response.version)
    bytes.extend(b' ')
    bytes.extend(http_response.status_code)
    bytes.extend(b' -\r\n')
    headers_to_bytes(http_response.headers.values(), bytes)
    return str(bytes)
