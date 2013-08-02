import re

import pyrox.http as http


ADD_HEADER = 1
REWRITE_HEADER = 2
CONSUME_EVENT = 3
PROXY_REQUEST = 4
REJECT_REQUEST = 5


class MessageControl(object):
    """
    This class is returned to the control plane to aggregrate actions.
    """

    def __init__(self):
        self.control = PROXY_REQUEST
        self.message_actions = list()

    def add_action(self, filter_action):
        self.message_actions.append(filter_action)

    def should_consume(self):
        return self.control == CONSUME_EVENT

    def should_reject(self):
        return self.control == REJECT_REQUEST


class FilterAction(object):

    def __init__(self, kind, *args):
        self.kind = kind
        self.args = args


class HttpFilterChain(object):

    def __init__(self):
        self.chain = list()

    def add_filter(self, http_filter):
        self.chain.append(http_filter)

    def on_header(self, field, value):
        message_control = MessageControl()
        for http_filter in self.chain:
            action_list = http_filter.on_header(field, value)
            if action_list and len(action_list) > 0:
                self._perform_actions(message_control, action_list)
                if message_control.should_consume() or message_control.should_reject():
                        break
        return message_control

    def _perform_actions(self, message_control, actions):
        for action in actions:
            if action.kind == ADD_HEADER and len(action.args) == 2:
                #Adding a header requires the name and value
                message_control.add_action(action)

            elif action.kind == REWRITE_HEADER and len(action.args) == 2:
                #Rewriting a header requires the name and value
                message_control.add_action(action)

            elif action.kind == CONSUME_EVENT:
                message_control.control = CONSUME_EVENT
            elif action.kind == REJECT_REQUEST:
                message_control.control = REJECT_REQUEST
        return message_control


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

    def on_request(self, request_message):
        """
        on_request will accept an HttpRequestMessage object and implement
        the logic that will define the FilterActions to be applied
        to the request
        """
        pass

    def on_response(self, response_message):
        """
        on_response will accept an HttpResponseMessage object and implement
        the logic that will define the FilterActions to be applied
        to the request
        """
        pass


class HttpRequestMessage(object):
    """
    HttpRequestMessage defines the Http request attributes that
    will be available to a HttpFilter
    """
    def __init__(self, url, method, version, headers=None ):
        self.url = url
        self.method = method
        self.version = version
        if headers is None:
            self.headers = dict()

class HttpResponseMessage(object):
    """
    HttpResponseMessage defines the Http response attributes that
    will be available to a HttpFilter
    """
    def __init__(self, status_code, version, headers=None):
        self.status_code = status_code
        self.version = version
        if headers is None:
            self.headers = dict()

class HttpHeader(object):
    """
    defines the fields for a Http header
    """
    def __init__(self, name, value):
        self.name = name
        self.value = value