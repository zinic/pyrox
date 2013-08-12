import unittest

from pyrox.http import RequestParser, ParserDelegate

UNEXPECTED_HEADER_REQUEST = (
    'GET /test/12345?field=f1&field2=f2#fragment HTTP/1.1\r\n'
    'Test: test\r\n'
    'Connection: keep-alive\r\n'
    'Content-Length: 12\r\n\r\n'
    'This is test'
)

NORMAL_REQUEST = (
    'GET /test/12345?field=f1&field2=f2#fragment HTTP/1.1\r\n'
    'Connection: keep-alive\r\n'
    'Content-Length: 12\r\n\r\n'
    'This is test'
)

CHUNKED_REQUEST = (
    'GET /test/12345?field=f1&field2=f2#fragment HTTP/1.1\r\n'
    'Connection: keep-alive\r\n'
    'Transfer-Encoding: chunked\r\n\r\n'
    '1e\r\nall your base are belong to us\r\n'
    '0\r\n'
)

REQUEST_METHOD_SLOT = 'REQUEST_METHOD'
REQUEST_URI_SLOT = 'REQUEST_URI'
REQUEST_HTTP_VERSION_SLOT = 'REQUEST_HTTP_VERSION'
HEADER_FIELD_SLOT = 'HEADER_FIELD'
HEADER_VALUE_SLOT = 'HEADER_VALUE'
BODY_SLOT = 'BODY'
BODY_COMPLETE_SLOT = 'BODY_COMPLETE'


def chunk_message(data, parser, chunk_size=10, limit=-1):
    if limit <= 0:
        limit = len(data)
    index = 0
    while index < limit:
        next_index = index + chunk_size
        end_index = next_index if next_index < limit else limit
        parser.execute(data[index:end_index])
        index = end_index


class TrackingDelegate(ParserDelegate):

    def __init__(self, delegate):
        self.hits = {
            REQUEST_METHOD_SLOT: 0,
            REQUEST_URI_SLOT: 0,
            REQUEST_HTTP_VERSION_SLOT: 0,
            HEADER_FIELD_SLOT: 0,
            HEADER_VALUE_SLOT: 0,
            BODY_SLOT: 0,
            BODY_COMPLETE_SLOT: 0
        }

        self.delegate = delegate

    def register_hit(self, slot):
        self.hits[slot] += 1

    def validate_hits(self, expected, test):
        for key in expected:
            test.assertEquals(
                expected[key],
                self.hits[key],
                'Failed on expected hits for key: {} - was {} expected {}'
                .format(key, self.hits[key], expected[key]))

    def on_req_method(self, method):
        self.register_hit(REQUEST_METHOD_SLOT)
        self.delegate.on_req_method(method)

    def on_req_path(self, url):
        self.register_hit(REQUEST_URI_SLOT)
        self.delegate.on_req_path(url)

    def on_http_version(self, major, minor):
        self.register_hit(REQUEST_HTTP_VERSION_SLOT)
        self.delegate.on_http_version(major, minor)

    def on_header_field(self, field):
        self.register_hit(HEADER_FIELD_SLOT)
        self.delegate.on_header_field(field)

    def on_header_value(self, value):
        self.register_hit(HEADER_VALUE_SLOT)
        self.delegate.on_header_value(value)

    def on_body(self, data, length, is_chunked):
        self.register_hit(BODY_SLOT)
        print('Body get: {}'.format(data))
        self.delegate.on_body(data, length, is_chunked)

    def on_message_complete(self, is_chunked, should_keep_alive):
        self.register_hit(BODY_COMPLETE_SLOT)
        self.delegate.on_message_complete(is_chunked, should_keep_alive)


class ValidatingDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test

    def on_req_method(self, method):
        self.test.assertEquals('GET', method)

    def on_req_path(self, url):
        self.test.assertEquals('/test/12345?field=f1&field2=f2#fragment', url)

    def on_http_version(self, major, minor):
        self.test.assertEquals(1, major)
        self.test.assertEquals(1, minor)

    def on_header_field(self, field):
        if field not in ['Transfer-Encoding', 'Content-Length', 'Connection']:
            self.test.fail('Unexpected header field {}'.format(field))

    def on_header_value(self, value):
        if value not in ['keep-alive', 'chunked', '12']:
            self.test.fail('Unexpected header value {}'.format(value))


class NonChunkedValidatingDelegate(ValidatingDelegate):

    def on_message_complete(self, is_chunked, should_keep_alive):
        self.test.assertEqual(is_chunked, 0)


class WhenParsingRequests(unittest.TestCase):

    def test_reading_request_with_content_length(self):
        tracker = TrackingDelegate(NonChunkedValidatingDelegate(self))
        parser = RequestParser(tracker)

        chunk_message(NORMAL_REQUEST, parser)

        tracker.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            REQUEST_HTTP_VERSION_SLOT: 1,
            HEADER_FIELD_SLOT: 2,
            HEADER_VALUE_SLOT: 2,
            BODY_SLOT: 2,
            BODY_COMPLETE_SLOT: 1}, self)

    def test_exception_propagation(self):
        tracker = TrackingDelegate(ValidatingDelegate(self))
        parser = RequestParser(tracker)

        with self.assertRaises(Exception):
            chunk_message(UNEXPECTED_HEADER_REQUEST, parser)

    def test_reading_chunked_request(self):
        tracker = TrackingDelegate(ValidatingDelegate(self))
        parser = RequestParser(tracker)

        chunk_message(CHUNKED_REQUEST, parser)

        tracker.validate_hits({
            REQUEST_METHOD_SLOT: 1,
            REQUEST_URI_SLOT: 1,
            REQUEST_HTTP_VERSION_SLOT: 1,
            HEADER_FIELD_SLOT: 2,
            HEADER_VALUE_SLOT: 2,
            BODY_SLOT: 4,
            BODY_COMPLETE_SLOT: 1}, self)


if __name__ == '__main__':
    unittest.main()
