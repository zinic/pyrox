import pyrox.http.filtering as filtering


class EmptyFilter(filtering.HttpFilter):

    def on_request(self, request_message):
        return filtering.route('google.com:80')
