import unittest
import time
import json

from pyrox.http import HttpParser, Filter, FilterAction


REQUEST_LINE = b'GET /test/12345?field=value#fragment HTTP/1.1\r\n'
HEADER = b'Content-Length: 0\r\n'
END = b'\r\n'


class ValidatingFilter(Filter):

    def __init__(self, test):
        self.test = test

    def on_req_method(self, method):
        self.test.assertEquals('GET', method)

    def on_url(self, url):
        self.test.assertEquals('/test/12345?field=value#fragment', url)

    def on_header_field(self, fieldname):
        pass

    def on_header_value(self, fieldname, value):
        pass


class WhenParsingRequests(unittest.TestCase):

    def test_init(self):
        parser = HttpParser(None)

    def test_read_request_line(self):
        parser = HttpParser(ValidatingFilter(self))
        datalen = len(REQUEST_LINE)
        read = parser.execute(REQUEST_LINE, datalen)
        self.assertEquals(datalen, read)

    def test_read_request_header(self):
        parser = HttpParser(ValidatingFilter(self))
        parser.execute(REQUEST_LINE, len(REQUEST_LINE))

        datalen = len(HEADER)
        read = parser.execute(HEADER, datalen)
        self.assertEquals(datalen, read)


if __name__ == '__main__':
    unittest.main()
