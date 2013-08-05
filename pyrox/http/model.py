_EMPTY_HEADER_VALUES = ()


class HttpHeader(object):
    """
    Defines the fields for a HTTP header

    Attributes:
        name        A bytearray or string value representing the field-name of
                    the header.
    """
    def __init__(self, name):
        self.name = name
        self.values = list()

    def to_bytes(self):
        bytes = bytearray(self.name)
        bytes.extend(b': ')

        if len(self.values) > 0:
            bytes.extend(self.values[0])

        for value in self.values[1:]:
            bytes.extend(b', ')
            bytes.extend(value)
        bytes.extend(b'\r\n')
        return str(bytes)


class HttpMessage(object):
    """
    Parent class for requests and responses. Many of the elements in the
    messages share common structures.

    Attributes:
        version     A bytearray or string value representing the major-minor
                    version of the HttpMessage.
    """
    def __init__(self):
        self.version = None
        self._headers = dict()

    @property
    def headers(self):
        return self._headers

    def header(self, name):
        """
        Returns the header that matches the name via case-insensitive matching.
        If the header does not exist, a new header is created, attached to the
        message and returned. If the header already exists, then it is
        returned.
        """
        lower_name = name.lower()
        header = self._headers.get(lower_name, None)
        if not header:
            header = HttpHeader(name)
            self._headers[lower_name] = header
        return header

    def get_header(self, name):
        """
        Returns the header that matches the name via case-insensitive matching.
        Unlike the header function, if the header does not exist then a None
        result is returned.
        """
        lower_name = name.lower()
        return self._headers.get(lower_name, None)

    def remove_header(self, name):
        """
        Removes the header that matches the name via case-insensitive matching.
        If the header exists, it is removed and a result of True is returned.
        If the header does not exist then a result of False is returned.
        """
        lower_name = name.lower()
        if lower_name in self._headers:
            del self._headers[lower_name]
            return True
        return False


class HttpRequest(HttpMessage):
    """
    HttpRequest defines the HTTP request attributes that will be available
    to a HttpFilter.

    Attributes:
        method      A bytearray or string value representing the request's
                    method verb.
        url         A bytearray or string value representing the requests'
                    uri path including the query and fragment string.
    """
    def __init__(self):
        super(HttpRequest, self).__init__()
        self.method = None
        self.url = None

    def to_bytes(self):
        bytes = bytearray()
        bytes.extend(self.method)
        bytes.extend(b' ')
        bytes.extend(self.url)
        bytes.extend(b' HTTP/')
        bytes.extend(self.version)
        bytes.extend(b'\r\n')
        for header in self.headers.values():
            bytes.extend(header.to_bytes())
        bytes.extend(b'\r\n')
        return str(bytes)

class HttpResponse(HttpMessage):
    """
    HttpResponse defines the HTTP response attributes that will be available
    to a HttpFilter.

    Attributes:
        status_code      An integer representing the response's status code
    """
    def __init__(self):
        super(HttpResponse, self).__init__()
        self.status_code = None

    def to_bytes(self):
        bytes = bytearray()
        bytes.extend(b'HTTP/')
        bytes.extend(self.version)
        bytes.extend(b' ')
        bytes.extend(self.status_code)
        bytes.extend(b' -\r\n')
        for header in self.headers.values():
            bytes.extend(header.to_bytes())
        bytes.extend(b'\r\n')
        return str(bytes)
