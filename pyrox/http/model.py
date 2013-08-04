_EMPTY_HEADER_VALUES = ()


class HttpHeader(object):
    """
    Defines the fields for a HTTP header
    """
    def __init__(self, name):
        self.name = name
        self.values = list()


class HttpMessage(object):
    """
    Parent class for requests and responses. Many of the elements in the
    messages share common structures.
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
    HttpRequest defines the HTTP request attributes that
    will be available to a HttpFilter
    """
    def __init__(self):
        super(HttpRequest, self).__init__()
        self.method = None
        self.url = None


class HttpResponse(HttpMessage):
    """
    HttpResponse defines the HTTP response attributes that
    will be available to a HttpFilter
    """
    def __init__(self):
        super(HttpResponse, self).__init__()
        self.status_code = None
