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
        self.headers = dict()

    def add_header(self, name, *values):
        lower_name = name.lower()
        if lower_name in self.headers:
            header = self.headers[lower_name]
        else:
            header = HttpHeader(name)
            self.headers[lower_name] = header
        for value in values:
            header.values.append(value)

    def remove_header(self, name):
        lower_name = name.lower()
        if lower_name in self.headers:
            del self.headers[lower_name]


class HttpRequest(HttpMessage):
    """
    HttpRequest defines the HTTP request attributes that
    will be available to a HttpFilter
    """
    def __init__(self):
        super(HttpRequest, self).__init__()
        self.url = None
        self.method = None


class HttpResponse(HttpMessage):
    """
    HttpResponse defines the HTTP response attributes that
    will be available to a HttpFilter
    """
    def __init__(self):
        super(HttpResponse, self).__init__()
        self.status_code = None
        self.headers = dict()
