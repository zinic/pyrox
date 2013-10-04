import pyrox.filtering as filtering


class RoutingFilter(filtering.HttpFilter):
    """
    This is an example on how to specify an upstream route when a request is
    intercepted.
    """

    @filtering.handles_request_head
    def on_request(self, request_message):
        return filtering.route('google.com:80')
