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
    def on_resp_head(self, request_head):
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


if __name__ == '__main__':
    unittest.main()
