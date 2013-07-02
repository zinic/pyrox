import unittest
import time
import json

from pyrox.http import HttpParser, Filter, FilterAction


REQUEST_LINE = b'GET /test/12345?field=value#fragment HTTP/1.1\r\n'
HEADER = b'Content-Length: 0\r\n'
MULTI_VALUE_HEADER = b'Test: test\r\nTest: test2\r\n'
ARRAY_HEADER = b'Other: test, test, test\r\n'
END = b'\r\n'


class SimpleValidatingFilter(Filter):

    def __init__(self, test):
        self.test = test

    def on_req_method(self, method):
        self.test.assertEquals('GET', method)

    def on_url(self, url):
        self.test.assertEquals('/test/12345?field=value#fragment', url)

    def on_header(self, name, value):
        self.test.assertEquals('Content-Length', name)
        self.test.assertEquals('0', value)


class MultiValueHeaderFilter(Filter):

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


class WhenParsingRequests(unittest.TestCase):

    def test_init(self):
        parser = HttpParser(None)

    def test_read_request_line(self):
        parser = HttpParser(SimpleValidatingFilter(self))
        datalen = len(REQUEST_LINE)
        read = parser.execute(REQUEST_LINE, datalen)
        self.assertEquals(datalen, read)

    def test_read_request_header(self):
        parser = HttpParser(SimpleValidatingFilter(self))
        parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        datalen = len(HEADER)
        read = parser.execute(HEADER, datalen)
        self.assertEquals(datalen, read)

    def test_read_multi_value_header(self):
        parser = HttpParser(MultiValueHeaderFilter(self))
        parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        datalen = len(MULTI_VALUE_HEADER)
        read = parser.execute(MULTI_VALUE_HEADER, datalen)
        self.assertEquals(datalen, read)


if __name__ == '__main__':
    unittest.main()
