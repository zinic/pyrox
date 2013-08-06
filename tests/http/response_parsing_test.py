import unittest

from pyrox.http import ResponseParser, ParserDelegate

NORMAL_RESPONSE = """HTTP/1.1 200 OK\r
Content-Length: 12\r\n\r
This is test"""

CHUNKED_RESPONSE = """HTTP/1.1 200 OK\r
Transfer-Encoding: chunked\r\n\r
1e\r\nall your base are belong to us\r
0\r
"""


RESPONSE_HTTP_VERSION_SLOT = 'RESPONSE_HTTP_VERSION'
RESPONSE_CODE_SLOT = 'RESPONSE_CODE'
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
            RESPONSE_HTTP_VERSION_SLOT: 0,
            RESPONSE_CODE_SLOT: 0,
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

    def on_status(self, status_code):
        self.register_hit(RESPONSE_CODE_SLOT)
        self.delegate.on_status(status_code)

    def on_http_version(self, major, minor):
        self.register_hit(RESPONSE_HTTP_VERSION_SLOT)
        self.delegate.on_http_version(major, minor)

    def on_header_field(self, field):
        self.register_hit(HEADER_FIELD_SLOT)
        self.delegate.on_header_field(field)

    def on_header_value(self, value):
        self.register_hit(HEADER_VALUE_SLOT)
        self.delegate.on_header_value(value)

    def on_body(self, data, length, is_chunked):
        self.register_hit(BODY_SLOT)
        self.delegate.on_body(data, length, is_chunked)

    def on_message_complete(self, is_chunked, should_keep_alive):
        self.register_hit(BODY_COMPLETE_SLOT)


class ValidatingDelegate(ParserDelegate):

    def __init__(self, test):
        self.test = test

    def on_http_version(self, major, minor):
        self.test.assertEquals(1, major)
        self.test.assertEquals(1, minor)

    def on_status(self, status_code):
        self.test.assertEquals(200, status_code)

    def on_header_field(self, field):
        if field not in ['Transfer-Encoding', 'Content-Length', 'Connection']:
            pass  # raise Exception('Unexpected header field {}'.format(field))

    def on_header_value(self, value):
        if value not in ['keep-alive', 'chunked', '12']:
            pass  # raise Exception('Unexpected header value {}'.format(value))

    def on_body(self, data, length, is_chunked):
        print('got {}'.format(data))


class WhenParsingResponses(unittest.TestCase):

    def test_reading_request_with_content_length(self):
        tracker = TrackingDelegate(ValidatingDelegate(self))
        parser = ResponseParser(tracker)

        chunk_message(NORMAL_RESPONSE, parser)

        tracker.validate_hits({
            RESPONSE_HTTP_VERSION_SLOT: 1,
            RESPONSE_CODE_SLOT: 1,
            HEADER_FIELD_SLOT: 1,
            HEADER_VALUE_SLOT: 1,
            BODY_SLOT: 3,
            BODY_COMPLETE_SLOT: 1}, self)

    def test_reading_chunked_request(self):
        tracker = TrackingDelegate(ValidatingDelegate(self))
        parser = ResponseParser(tracker)

        chunk_message(CHUNKED_RESPONSE, parser)

        tracker.validate_hits({
            RESPONSE_HTTP_VERSION_SLOT: 1,
            RESPONSE_CODE_SLOT: 1,
            HEADER_FIELD_SLOT: 1,
            HEADER_VALUE_SLOT: 1,
            BODY_SLOT: 4,
            BODY_COMPLETE_SLOT: 1}, self)


if __name__ == '__main__':
    unittest.main()
