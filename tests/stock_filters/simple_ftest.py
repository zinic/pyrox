#
# To run from project root:
# python -m unittest discover --pattern=simple_ftest.py
#
# You can add wildcards in the pattern to run other tests:
# python -m unittest discover --pattern=*test*.py
#
import unittest

import pyrox.http as http
import pyrox.filtering as http_filtering

import pynsive


class WhenFuncTestingSimpleFilter(unittest.TestCase):
    def setUp(self):
        self.req_message = http.HttpRequest()
        self.req_message.url = 'http://127.0.0.1'
        self.req_message.method = 'GET'
        self.req_message.version = "1.0"

        plugin_manager = pynsive.PluginManager()
        plugin_manager.plug_into('examples/filter')
        simple_filter_plugin = pynsive.import_module('simple_example')
        self.simple_filter = simple_filter_plugin.SimpleFilter()

    def test_simple_filter_returns_reject_action(self):
        returned_action = self.simple_filter.on_request(self.req_message)
        self.assertEqual(returned_action.kind, http_filtering.REJECT)

    def test_simple_filter_returns_pass_action(self):
        auth_header = self.req_message.header(name="user-agent")
        auth_header.values.append('Unittest HTTP Request')
        returned_action = self.simple_filter.on_request(self.req_message)
        self.assertEqual(returned_action.kind, http_filtering.NEXT_FILTER)


if __name__ == '__main__':
    unittest.main()
