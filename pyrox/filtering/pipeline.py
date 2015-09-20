import inspect

from pyrox.http import HttpResponse
from pyrox.log import get_logger

_LOG = get_logger(__name__)


"""
Logging-fu
"""
_CHECKING_DECORATORS = 'Checking function instance {} for decorators'
_HANDLES_REQ_HEAD = 'Function instance {} handles request head'
_HANDLES_REQ_BODY = 'Function instance {} handles request body'
_HANDLES_RES_HEAD = 'Function instance {} handles response head'
_HANDLES_RES_BODY = 'Function instance {} handles response body'


"""
Action enumerations.
"""
NEXT_FILTER = 0
CONSUME = 1
REJECT = 2
ROUTE = 3
REPLY = 4

_ACTION_NAMES = {
    0: 'NEXT_FILTER',
    1: 'CONSUME',
    2: 'REJECT',
    3: 'ROUTE',
    4: 'REPLY'
}

_BREAKING_ACTIONS = (CONSUME, REJECT, ROUTE, REPLY)


class FilterAction(object):
    """
    A filter action allows us to tell upstream controls what the filter has
    decided as the next course of action. Certain filter actions may include
    a response object for serialization out to the client in the case where
    the action enforces a rejection.

    Attributes:
        kind        An integer value representing the kind of action this
                    object is intended to communicate.
        payload     An argument to be passed on to the consumer of this action.
    """
    def __init__(self, kind=NEXT_FILTER, payload=None):
        self.kind = kind
        self.payload = payload

    def breaks_pipeline(self):
        return self.kind in _BREAKING_ACTIONS

    def should_connect_upstream(self):
        return self.kind not in (REPLY, REJECT)

    def is_consuming(self):
        return self.kind == CONSUME

    def is_rejecting(self):
        return self.kind == REJECT

    def is_replying(self):
        return self.kind == REPLY

    def is_routing(self):
        return self.kind == ROUTE

    def __str__(self):
        return 'Action({}) - Is breaking flow: {}'.format(
            _ACTION_NAMES[self.kind], self.breaks_pipeline())


def handles_request_head(request_func):
    """
    This function decorator may be used to mark a method as usable for
    intercepting request head content.

    handles_request_head will accept an HttpRequest object and implement
    the logic that will define the FilterActions to be applied
    to the request
    """
    request_func._handles_request_head = True
    return request_func


def handles_request_body(request_func):
    """
    This function decorator may be used to mark a method as usable for
    intercepting request body content.

    handles_request_body will intercept the HTTP content in chunks as it
    arrives. This method, like others in the filter class may return a
    FilterAction.
    """
    request_func._handles_request_body = True
    return request_func


def handles_response_head(request_func):
    """
    This function decorator may be used to mark a method as usable for
    intercepting response head content.

    handles_response_head will accept an HttpResponse object and implement
    the logic that will define the FilterActions to be applied
    to the request
    """
    request_func._handles_response_head = True
    return request_func


def handles_response_body(request_func):
    """
    This function decorator may be used to mark a method as usable for
    intercepting response body content.

    handles_response_body will intercept the HTTP content in chunks as they
    arrives. This method, like others in the filter class, may return a
    FilterAction.
    """
    request_func._handles_response_body = True
    return request_func


class HttpFilter(object):
    """
    HttpFilter is a marker class that may be utilized for dynamic gathering
    of filter logic.
    """
    pass


"""
Default return object. This should be configurable.
"""
_DEFAULT_REJECT_RESP = HttpResponse()
_DEFAULT_REJECT_RESP.version = b'1.1'
_DEFAULT_REJECT_RESP.status = '400 Bad Request'
_DEFAULT_REJECT_RESP.header('Content-Length').values.append('0')

"""
Default filter action singletons.
"""
_DEFAULT_PASS_ACTION = FilterAction(NEXT_FILTER)
_DEFAULT_CONSUME_ACTION = FilterAction(CONSUME)


def consume():
    """
    Consumes the event and does not allow any further downstream filters to
    see it. This effectively halts execution of the filter chain but leaves the
    request to pass through the proxy.
    """
    return _DEFAULT_CONSUME_ACTION


def reply(response, src=None):
    """
    A special type of rejection that implies willful handling of a request.
    This call may optionally include a stream or a data blob to take the
    place of the response content body.

    :param response: the response object to reply to the client with
    """
    return FilterAction(REPLY, (response, src))


def reject(response=None):
    """
    Rejects the request that this event is related to. Rejection may happen
    during on_request and on_response. The associated response parameter
    becomes the response the client should expect to see. If a response
    parameter is not provided then the function will default to the configured
    default response.

    :param response: the response object to reply to the client with
    """
    if response is None:
        return FilterAction(REPLY, (_DEFAULT_REJECT_RESP, None))
    else:
        return FilterAction(REPLY, (response, None))


def route(upstream_target):
    """
    Routes the request that this event is related to. Usage of this method will
    halt execution of the filter pipeline and begin streaming the request to
    the specified upstream target. This method is invalid for handling an
    upstream response.

    :param upstream_target: the URI string of the upstream target to route
                            to.
    """
    return FilterAction(ROUTE, upstream_target)


def next():
    """
    Passes the current http event down the filter chain. This allows for
    downstream filters a chance to process the event.
    """
    return _DEFAULT_PASS_ACTION


class HttpFilterPipeline(object):
    """
    The filter pipeline represents a series of filters. This pipeline currently
    serves bidirectional filtering (request and response). This chain will have
    the request head and response head events passed through it during the
    lifecycle of a client request. Each request is assigned a new copy of the
    chain, meaning that state may not be shared between requests during the
    lifetime of the filter chain or its filters.


    :param chain: A list of HttpFilter objects organized to act as a pipeline
                  with element 0 being the first to receive events.
    """
    def __init__(self):
        self._req_head_chain = list()
        self._req_body_chain = list()
        self._resp_head_chain = list()
        self._resp_body_chain = list()

    def intercepts_req_body(self):
        return len(self._req_body_chain) > 0

    def intercepts_resp_body(self):
        return len(self._resp_body_chain) > 0

    def add_filter(self, http_filter):
        filter_methods = inspect.getmembers(http_filter, inspect.ismethod)

        for method in filter_methods:
            if len(method) < 1:
                continue

            finst = method[1]
            _LOG.debug(_CHECKING_DECORATORS.format(finst))

            # Assume that if an attribute exists then it is decorated
            if hasattr(finst, '_handles_request_head'):
                _LOG.debug(_HANDLES_REQ_HEAD.format(finst))
                self._req_head_chain.append((http_filter, finst))

            if hasattr(finst, '_handles_request_body'):
                _LOG.debug(_HANDLES_REQ_BODY.format(finst))
                self._req_body_chain.append((http_filter, finst))

            if hasattr(finst, '_handles_response_head'):
                _LOG.debug(_HANDLES_RES_HEAD.format(finst))
                self._resp_head_chain.append((http_filter, finst))

            if hasattr(finst, '_handles_response_body'):
                _LOG.debug(_HANDLES_RES_BODY.format(finst))
                self._resp_body_chain.append((http_filter, finst))

    def _on_head(self, chain, *args):
        last_action = next()

        for http_filter, method in chain:
            try:
                argspec = inspect.getargspec(method)

                if len(argspec.args) == 2:
                    action = method(*args[0:1])
                else:
                    action = method(*args)

            except Exception as ex:
                _LOG.exception(ex)
                action = reject()

            if action is not None:
                last_action = action

                if action.breaks_pipeline():
                    break

        return last_action

    def _on_body(self, chain, *args):
        last_action = next()

        for http_filter, method in chain:
            try:
                argspec = inspect.getargspec(method)
                if len(argspec.args) == 3:
                    action = method(*args[0:2])
                else:
                    action = method(*args)
            except Exception as ex:
                _LOG.exception(ex)
                action = reject()

            if action:
                last_action = action
                if action.breaks_pipeline():
                    break

        return last_action

    def on_request_head(self, request_head):
        return self._on_head(self._req_head_chain, request_head)

    def on_request_body(self, body_part, output):
        return self._on_body(self._req_body_chain, body_part, output)

    def on_response_head(self, *args):
        return self._on_head(self._resp_head_chain, *args)

    def on_response_body(self, *args):
        return self._on_body(self._resp_body_chain, *args)
