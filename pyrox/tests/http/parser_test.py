import unittest
import time
import json

from pyrox.http import HttpParser, ParserDelegate


REQUEST_LINE = b'GET /test/12345?field=value&field2=value#fragment HTTP/1.1\r\n'
HEADER = b'Content-Length: 0\r\n'
MULTI_VALUE_HEADER = b'Test: test\r\nTest: test2\r\n'
ARRAY_HEADER = b'Other: test, test, test\r\n'
END = b'\r\n'


REQUEST_METHOD_SLOT = 'REQUEST_METHOD'
REQUEST_URI_SLOT = 'REQUEST_URI'
HEADER_SLOT = 'HEADER'


class TrackingDelegate(ParserDelegate):

    def __init__(self, delegate):
        self.hits = {
            REQUEST_METHOD_SLOT: 0,
            REQUEST_URI_SLOT: 0,
            HEADER_SLOT: 0
        }

        self.delegate = delegate

    def register_hit(self, slot):
        self.hits[slot] += 1

    def validate_hits(self, expected, test):
        for key in expected:
            test.assertEquals(
                expected[key],
                self.hits[key],
                'Failed on expected hits for key: {}'.format(key))

    def on_req_method(self, method):
        self.register_hit(REQUEST_METHOD_SLOT)
        self.delegate.on_req_method(method)

    def on_url(self, url):
        self.register_hit(REQUEST_URI_SLOT)
        self.delegate.on_url(url)

    def on_header(self, name, value):
        self.register_hit(HEADER_SLOT)
        self.delegate.on_header(name, value)


class ValidatingDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test

    def on_req_method(self, method):
        self.test.assertEquals('GET', method)

    def on_url(self, url):
        self.test.assertEquals('/test/12345?field=value&field2=value#fragment', url)

    def on_header(self, name, value):
        self.test.assertEquals('Content-Length', name)
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
        parser = HttpParser(None)

    def test_read_request_line(self):
        test_filter = TrackingDelegate(ValidatingDelegate(self))
        parser = HttpParser(test_filter)

        datalen = len(REQUEST_LINE)
        read = parser.execute(REQUEST_LINE, datalen)
        self.assertEquals(datalen, read)
        test_filter.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1}, self)

    def test_read_partial_request_line(self):
        test_filter = TrackingDelegate(ValidatingDelegate(self))
        parser = HttpParser(test_filter)

        datalen = len(REQUEST_LINE) / 2
        read = parser.execute(REQUEST_LINE[:datalen], datalen)
        self.assertEquals(datalen, read)
        test_filter.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 0}, self)

    def test_read_request_header(self):
        test_filter = TrackingDelegate(ValidatingDelegate(self))
        parser = HttpParser(test_filter)

        read = parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        datalen = len(HEADER)
        read = parser.execute(HEADER, datalen)
        self.assertEquals(datalen, read)
        test_filter.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            HEADER_SLOT: 1}, self)

    def test_read_multi_value_header(self):
        test_filter = TrackingDelegate(MultiValueHeaderDelegate(self))
        parser = HttpParser(test_filter)

        parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        datalen = len(MULTI_VALUE_HEADER)
        read = parser.execute(MULTI_VALUE_HEADER, datalen)
        self.assertEquals(datalen, read)
        test_filter.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            HEADER_SLOT: 2}, self)

    def test_read_array_value_header(self):
        test_filter = TrackingDelegate(ArrayValueHeaderDelegate(self))
        parser = HttpParser(test_filter)

        parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        datalen = len(ARRAY_HEADER)
        read = parser.execute(ARRAY_HEADER, datalen)
        self.assertEquals(datalen, read)
        test_filter.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            HEADER_SLOT: 1}, self)


if __name__ == '__main__':
    unittest.main()
