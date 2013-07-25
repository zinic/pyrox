import unittest

from pyrox.http import HttpEventParser, ParserDelegate


REQUEST_LINE = b'GET /test/12345?field=f1&field2=f2#fragment HTTP/1.1\r\n'
HEADER = b'Content-Length: 0\r\n'
MULTI_VALUE_HEADER = b'Test: test\r\nTest: test2\r\n'
ARRAY_HEADER = b'Other: test, test, test\r\n'
END = b'\r\n'


REQUEST_METHOD_SLOT = 'REQUEST_METHOD'
REQUEST_URI_SLOT = 'REQUEST_URI'
REQUEST_HTTP_VERSION_SLOT = 'REQUEST_HTTP_VERSION'
HEADER_FIELD_SLOT = 'HEADER_FIELD'
HEADER_VALUE_SLOT = 'HEADER_VALUE'


class TrackingDelegate(ParserDelegate):

    def __init__(self, delegate):
        self.hits = {
            REQUEST_METHOD_SLOT: 0,
            REQUEST_URI_SLOT: 0,
            REQUEST_HTTP_VERSION_SLOT: 0,
            HEADER_FIELD_SLOT: 0,
            HEADER_VALUE_SLOT: 0,
        }

        self.delegate = delegate

    def register_hit(self, slot):
        self.hits[slot] += 1

    def validate_hits(self, expected, test):
        for key in expected:
            test.assertEquals(
                expected[key],
                self.hits[key],
                'Failed on expected hits for key: {} - was {} expected {}'.format(key, self.hits[key], expected[key]))

    def on_req_method(self, method):
        self.register_hit(REQUEST_METHOD_SLOT)
        self.delegate.on_req_method(method)

    def on_req_path(self, url):
        self.register_hit(REQUEST_URI_SLOT)
        self.delegate.on_url(url)

    def on_req_http_version(self, major, minor):
        self.register_hit(REQUEST_HTTP_VERSION_SLOT)
        self.delegate.on_req_http_version(major, minor)

    def on_header_field(self, field):
        self.register_hit(HEADER_FIELD_SLOT)
        self.delegate.on_header_field(field)

    def on_header_value(self, value):
        self.register_hit(HEADER_VALUE_SLOT)
        self.delegate.on_header_value(value)


class ValidatingDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test

    def on_req_method(self, method):
        self.test.assertEquals('GET', method)

    def on_req_path(self, url):
        self.test.assertEquals('/test/12345?field=f1&field2=f2#fragment', url)

    def on_req_http_version(self, major, minor):
        self.test.assertEquals(1, major)
        self.test.assertEquals(1, minor)

    def on_header_field(self, field):
        self.test.assertEquals('Content-Length', field)

    def on_header_value(self, value):
        self.test.assertEquals('0', value)


class MultiValueHeaderDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test
        self.second_value = False

    def on_header(self, name, value):
        self.test.assertEquals('Test', name)

        if not self.second_value:
            self.test.assertEquals('test', value)
            self.second_value = True
        else:
            self.test.assertEquals('test2', value)


class ArrayValueHeaderDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test
        self.second_value = False

    def on_header(self, name, value):
        self.test.assertEquals('Other', name)
        self.test.assertEquals('test, test, test', value)


class WhenParsingRequests(unittest.TestCase):

    def test_init(self):
        parser = HttpEventParser(None)

    def test_simple_request_line(self):
        tracker = TrackingDelegate(ValidatingDelegate(self))
        parser = HttpEventParser(tracker)

        parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        tracker.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            REQUEST_HTTP_VERSION_SLOT: 1}, self)

    def test_header(self):
        tracker = TrackingDelegate(ValidatingDelegate(self))
        parser = HttpEventParser(tracker)

        parser.execute(REQUEST_LINE, len(REQUEST_LINE))
        parser.execute(HEADER, len(HEADER))
        parser.execute(HEADER, len(HEADER))

        tracker.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            REQUEST_HTTP_VERSION_SLOT: 1,
            HEADER_FIELD_SLOT: 2,
            HEADER_VALUE_SLOT: 2}, self)


if __name__ == '__main__':
    unittest.main()
