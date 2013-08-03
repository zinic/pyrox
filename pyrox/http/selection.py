class HttpMessageSelector(object):

    def __init__(
            self,
            path_re,
            interested_codes=None,
            interested_methods=None):
        self.interested_codes =\
            interested_codes if interested_codes else list()
        self.interested_methods =\
            interested_methods if interested_codes else list()
        self.path_re = re.compile(path_re)

    def wants_status(self, status_code):
        return status_code in self.interested_codes

    def wants_path(self, path):
        return self.path_re.matches(path)

    def wants_method(self, method):
        return method.lower() in self.interested_methods


class FilterOptions(object):

    def __init__(self, selector):
        self.selector = selector


class FilterHandler(http.ParserDelegate):

    def __init__(self, filter_chain, options):
        self.filter_chain = filter_chain
        self.options = options
        self.is_interested = False
        self.current_header_field = None

    def on_status(self, status_code):
        if self.options.selector.wants_status(status_code):
            self.is_interested = True

    def on_req_method(self, method):
        if self.options.selector.wants_method(method):
            self.is_interested = True

    def on_req_path(self, url):
        if self.is_interested and not self.options.selector.wants_path(url):
            self.is_interested = False

    def on_header_field(self, field):
        if self.is_interested:
            self.current_header_field = field

    def on_header_value(self, value):
        if self.is_interested:
            self.filter_chain.on_header(self.current_header_field, value)

    def on_message_complete(self):
        self.is_interested = False
