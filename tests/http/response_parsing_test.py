import unittest
import time
import json

from pyrox.http import HttpEventParser, ParserDelegate


STATUS_LINE = b'HTTP/1.1 200 OK\r\n'
STATUS_LINE_LF_ONLY = b'HTTP/1.1 200 OK\nTest: test\r\n\r\n'
HEADER = b'Content-Length: 0\r\n'
MULTI_VALUE_HEADER = b'Test: test\r\nTest: test2\r\n'
ARRAY_HEADER = b'Other: test, test, test\r\n'
END = b'\r\n'


FTEST = (
    'HTTP/1.1 200 OK\n'
    'Date: Wed, 17 Jul 2013 20:19:12 GMT\n'
    'Vary: Accept-Encoding\n'
    'Server: Apache/2.2.16\n'
    'Connection: Keep-Alive\n'
    'Content-Type: text/html; charset=UTF-8\n'
    'X-Powered-By: PHP/5.3.3-7+squeeze15\n'
    'Transfer-Encoding: chunked\n\n'
    '4\r\n'
    'TEST\r\n'
    '0\r\n\r\n'
)

STATUS_CODE_SLOT = 'STATUS_CODE'
HEADER_SLOT = 'HEADER'


class TrackingDelegate(ParserDelegate):

    def __init__(self, delegate):
        self.hits = {
            STATUS_CODE_SLOT: 0,
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

    def on_status(self, status_code):
        self.register_hit(STATUS_CODE_SLOT)
        self.delegate.on_status(status_code)

    def on_header(self, name, value):
        self.register_hit(HEADER_SLOT)
        self.delegate.on_header(name, value)


class ValidatingDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test

    def on_status(self, status_code):
        self.test.assertEquals(200, status_code)


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


class WhenParsingResponses(unittest.TestCase):
    pass


if __name__ == '__main__':
    unittest.main()
