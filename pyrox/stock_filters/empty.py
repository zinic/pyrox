import pyrox.filtering as filtering


class EmptyFilter(filtering.HttpFilter):

    @filtering.handles_request_head
    def on_request_head(self, request):
        pass
