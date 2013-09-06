from .model_util import request_to_bytes, response_to_bytes, strval


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


class HttpMessage(object):
    """
    Parent class for requests and responses. Many of the elements in the
    messages share common structures.

    Attributes:
        version     A bytearray or string value representing the major-minor
                    version of the HttpMessage.
    """
    def __init__(self, version='1.1'):
        self.version = version
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
        nameval = strval(name)
        header = self._headers.get(nameval, None)
        if not header:
            header = HttpHeader(name)
            self._headers[nameval] = header
        return header

    def replace_header(self, name):
        """
        Returns a new header with a field set to name. If the header exists
        then the header is removed from the request first.
        """
        self.remove_header(name)
        return self.header(name)

    def get_header(self, name):
        """
        Returns the header that matches the name via case-insensitive matching.
        Unlike the header function, if the header does not exist then a None
        result is returned.
        """
        return self._headers.get(strval(name), None)

    def remove_header(self, name):
        """
        Removes the header that matches the name via case-insensitive matching.
        If the header exists, it is removed and a result of True is returned.
        If the header does not exist then a result of False is returned.
        """
        nameval = strval(name)
        if nameval in self._headers:
            del self._headers[nameval]
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
        return request_to_bytes(self)


class HttpResponse(HttpMessage):
    """
    HttpResponse defines the HTTP response attributes that will be available
    to a HttpFilter.

    Attributes:
        status      A string representing the response's status code and
                    potentially its human readable component delimited by
                    a single space.
    """
    def __init__(self):
        super(HttpResponse, self).__init__()
        self.status = None

    def to_bytes(self):
        return response_to_bytes(self)
