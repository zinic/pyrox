import unittest
import mock

import pyrox.filtering as filtering
from pyrox.filtering import HttpFilterPipeline
from pyrox.server.proxyng import UpstreamHandler

request = None
on_head_got_request = False
on_body_got_request = False

class ResponseFilterUsesRequest(filtering.HttpFilter):
    @filtering.handles_response_head
    def on_response_head_with_request(self, response, req):
        global request, on_head_got_request
        assert req == request
        on_head_got_request = True
        return filtering.next()

    @filtering.handles_response_body
    def on_response_body_with_request(self, msg_part, body, req):
        global request, on_body_got_request
        assert req == request
        on_body_got_request = True
        return filtering.next()


class ResponseFilterDoesNotUseRequest(filtering.HttpFilter):
    @filtering.handles_response_head
    def on_response_head_no_request(self, head):
        return filtering.next()

    @filtering.handles_response_body
    def on_response_body_no_request(self, msg_part, body):
        return filtering.next()
    

class TestUpstreamHandler(unittest.TestCase):
    def test_on_headers_complete_passes_request(self):
        global request, on_head_got_request, on_body_got_request

        pipeline = HttpFilterPipeline()
        pipeline.add_filter(ResponseFilterUsesRequest())
        pipeline.add_filter(ResponseFilterDoesNotUseRequest())

        downstream = mock.MagicMock()
        downstream.write = mock.Mock(return_value=None)

        upstream = mock.MagicMock()
        request = mock.Mock()

        handler = UpstreamHandler(downstream, upstream, pipeline, request)
        handler.on_status(200) # Make response non-empty to prevent errors
        handler.on_headers_complete()
        handler.on_body(bytes='', length=0, is_chunked=False)

        self.assertTrue(on_head_got_request)
        self.assertTrue(on_body_got_request)
