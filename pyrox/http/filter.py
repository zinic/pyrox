class Filter(object):

    def on_req_method(self, method):
        pass

    def on_url(self, url):
        pass

    def on_header_field(self, fieldname):
        pass

    def on_header_value(self, fieldname, value):
        pass


class FilterAction(object):
    pass

