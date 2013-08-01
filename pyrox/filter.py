import re

import pyrox.http as http


DROP_HEADERS
ADD_HEADERS
REPLACE_HEADERS
CONSUME


class FilterAction(object):

    self __init__(self, action_enum, *args):
        self.action_enum = action_enum
        self.args = args


class HttpFilterChain(object):

    def __init__(self):
        self.chain = list()

    def add_filter(self, http_filter):
        self.chain.append(http_filter)

    def on_header(self, field, value):
        for http_filter in chain:
            action = http_filter.on_header(field, value)
            if action:
                pass #do action


class HttpMessageSelector(object):

    def __init__(
            self,
            interested_codes=None,
            interested_methods=None,
            path_re):
        self.interested_codes =
            interested_codes if interested_codes else list()
        self.interested_methods =
            interested_methods if interested_codes else list()
        self.path_re = re.compile(path_re)

    def wants_status(self, status_code):
        return status_code in interested_codes

    def wants_path(self, path):
        return self.path_re.matches(path)

    def wants_method(self, method):
        return method.lower() in interested_methods


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
        if options.selector.wants_status(status_code):
            self.is_interested = True

    def on_req_method(self, method):
        if options.selector.wants_method(method):
            self.is_interested = True

    def on_req_path(self, url):
        if self.is_interested and not options.selector.wants_path(url):
            self.is_interested = False

    def on_header_field(self, field):
        if self.is_interested:
            self.current_header_field = field

    def on_header_value(self, value):
        if self.is_interested:
            self.filter_chain.on_header(self.current_header_field, value)

    def on_message_complete(self):
        self.is_interested = False


class HttpFilter(object):

    def on_header(self, field, value):
    """
    """
        pass

