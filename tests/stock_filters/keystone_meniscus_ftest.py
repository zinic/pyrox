#
# To run from project root:
# python -m unittest discover --pattern=keystone_meniscus_ftest.py
#
# You can add wildcards in the pattern to run other tests:
# python -m unittest discover --pattern=*test*.py
#
from ConfigParser import ConfigParser
import unittest
import pyrox.http as http
import pyrox.filtering as http_filtering

from keystoneclient.v2_0 import client

import pynsive

_FTEST_CONFIG_KEY = 'keystone_meniscus_ftest'


class WhenFuncTestingKeystoneMeniscus(unittest.TestCase):
    def setUp(self):
        self.config = ConfigParser()
        self.config.read("examples/config/pyrox.conf")

        self.username = self.config.get(_FTEST_CONFIG_KEY, 'username')
        self.password = self.config.get(_FTEST_CONFIG_KEY, 'password')
        self.tenant_name = self.config.get(_FTEST_CONFIG_KEY, 'tenant_name')
        self.auth_url = self.config.get(_FTEST_CONFIG_KEY, 'auth_url')

        self.host = self.config.get(_FTEST_CONFIG_KEY, 'host')
        self.tenant_id = self.config.get(_FTEST_CONFIG_KEY, 'tenant_id')

        plugin_manager = pynsive.PluginManager()
        plugin_manager.plug_into('examples/filter')
        keystone_filter_plugin = pynsive.import_module(
            'keystone_meniscus_example')
        self.keystone_filter = keystone_filter_plugin.MeniscusKeystoneFilter()

    def test_meniscus_keystone_returns_proxy_action(self):

        url = "http://{host}:8080/v1/tenant/{tenant_id}".format(
            host=self.host, tenant_id=self.tenant_id)

        keystone = client.Client(username=self.username,
                                 password=self.password,
                                 tenant_name=self.tenant_name,
                                 auth_url=self.auth_url)
        token = keystone.auth_token

        req_message = http.HttpRequest()
        req_message.url = url
        req_message.method = 'GET'
        req_message.version = "1.0"

        auth_header = req_message.header(name="X-AUTH-TOKEN")
        auth_header.values.append(token)

        returned_action = self.keystone_filter.on_request(req_message)
        self.assertEqual(returned_action.kind, http_filtering.NEXT_FILTER)

    def test_meniscus_keystone_returns_reject_action(self):

        url = "http://{host}:8080/v1/tenant/{tenant_id}".format(
            host=self.host, tenant_id=self.tenant_id)

        req_message = http.HttpRequest()
        req_message.url = url
        req_message.method = 'GET'
        req_message.version = "1.0"

        auth_header = req_message.header(name="X-AUTH-TOKEN")
        auth_header.values.append('BAD_TOKEN')

        returned_action = self.keystone_filter.on_request(req_message)
        self.assertEqual(returned_action.kind, http_filtering.REJECT)


if __name__ == '__main__':
    unittest.main()
