from ConfigParser import ConfigParser

from keystoneclient.v2_0 import client

from pyrox.server import new_server
from pyrox.http_filter import HttpFilterChain
from pyrox.stock_filters.keystone_meniscus import MeniscusKeystoneFilter


_FTEST_CONFIG_KEY = 'keystone_meniscus_ftest'


def new_filter_chain():
    chain = HttpFilterChain()
    chain.add_filter(MeniscusKeystoneFilter())
    return chain

# This is a cheesy functional test for the proxy server while I work out
# the async tornado stuff...
proxy = new_server(
    ('127.0.0.1', 8080),
    new_filter_chain,
    #downstream_target=('localhost', 80))
    downstream_target=('coordination.dev.ord.projectmeniscus.org', 8080))
proxy.start_up()
