import mock
import unittest

import pyrox.filtering as filtering


class TestFilterWithAllDecorators(filtering.HttpFilter):

    def __init__(self):
        self.on_req_head_called = False
        self.on_req_body_called = False
        self.on_resp_head_called = False
        self.on_resp_body_called = False

    def were_expected_calls_made(self):
        return self.on_req_head_called and \
            self.on_req_body_called and \
            self.on_resp_head_called and \
            self.on_resp_body_called

    @filtering.handles_request_head
    def on_req_head(self, request_head):
        self.on_req_head_called = True

    @filtering.handles_request_body
    def on_req_body(self, body_part, output):
        self.on_req_body_called = True

    @filtering.handles_response_head
    def on_resp_head(self, response_head):
        self.on_resp_head_called = True

    @filtering.handles_response_body
    def on_resp_body(self, body_part, output):
        self.on_resp_body_called = True


class WhenBuildingPipelines(unittest.TestCase):

    def test_adding_filters(self):
        pipeline = filtering.HttpFilterPipeline()

        http_filter = TestFilterWithAllDecorators()
        http_filter.on_req_head(mock.MagicMock())
        pipeline.add_filter(http_filter)

        pipeline.on_request_head(mock.MagicMock())
        pipeline.on_request_body(mock.MagicMock(), mock.MagicMock())
        pipeline.on_response_head(mock.MagicMock())
        pipeline.on_response_body(mock.MagicMock(), mock.MagicMock())

        self.assertTrue(http_filter.were_expected_calls_made())


class TestHttpFilterPipeline(unittest.TestCase):
    def test_response_methods_pass_optional_request(self):
        resp_head = mock.MagicMock()
        resp_body = mock.MagicMock()
        req_head = mock.MagicMock()
        msg_part = mock.MagicMock()
        out = mock.MagicMock()

        assertEqual = self.assertEqual

        class ResponseFilterUsesRequest():
            def __init__(self):
                self.on_resp_head_called = False
                self.on_resp_body_called = False

            def were_expected_calls_made(self):
                return self.on_resp_head_called and \
                       self.on_resp_body_called

            @filtering.handles_response_head
            def on_response_head(self, response_head, request_head):
                assertEqual(resp_head, response_head)
                assertEqual(req_head, request_head)
                self.on_resp_head_called = True
                
            @filtering.handles_response_body
            def on_response_body(self, message_part, output, request_head):
                assertEqual(msg_part, message_part)
                assertEqual(out, output)
                assertEqual(req_head, request_head)
                self.on_resp_body_called = True


        pipeline = filtering.HttpFilterPipeline()

        resp_filter = ResponseFilterUsesRequest()
        pipeline.add_filter(resp_filter)

        pipeline.on_response_head(resp_head, req_head)
        pipeline.on_response_body(msg_part, out, req_head)
        self.assertTrue(resp_filter.were_expected_calls_made())
    

if __name__ == '__main__':
    unittest.main()
