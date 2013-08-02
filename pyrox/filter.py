import re

import pyrox.http as http


ADD_HEADER = 1
REWRITE_HEADER = 2
CONSUME_EVENT = 3
PROXY_REQUEST = 4
REJECT_REQUEST = 5


class FilterAction(object):

    def __init__(self, kind, *args):
        self.kind = kind
        self.args = args


class HttpFilterChain(object):

    def __init__(self, stream):
        self.chain = list()
        self.stream = stream

    def add_filter(self, http_filter):
        self.chain.append(http_filter)

    def on_header(self, field, value):
        request_control = PROXY_REQUEST
        for http_filter in self.chain:
            action_list = http_filter.on_header(field, value)
            if action_list and len(action_list) > 0:
                request_control = self._perform_actions(action_list)
                if request_control and (request_control == REJECT_REQUEST or request_control == CONSUME_EVENT):
                        break
        return request_control

    def _perform_actions(self, current_header_field, actions):
        request_control = None
        for action in actions:
            if action.kind == ADD_HEADER and len(action.args) == 2:
                self.stream.write(b'{}: {}\r\n'.format(
                    action.args[0],
                    action.args[1]))
            elif action.kind == REWRITE_HEADER and len(action.args) == 1:
                self.stream.write(b'{}: {}\r\n'.format(
                    current_header_field,
                    action.args[0]))
            elif action.kind == CONSUME_EVENT:
                request_control = CONSUME_EVENT
            elif action.kind == REJECT_REQUEST:
                request_control = REJECT_REQUEST
        return request_control


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


class HttpFilter(object):

    def on_header(self, field, values):
        pass
