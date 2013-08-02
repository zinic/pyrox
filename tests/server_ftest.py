from pyrox.server import new_server
from pyrox.http_filter import HttpFilterChain

def new_filter_chain():
    return HttpFilterChain()

# This is a cheesy functional test for the proxy server while I work out
# the async tornado stuff...
proxy = new_server(
    ('127.0.0.1', 8080),
    new_filter_chain,
    downstream_target=('www.liblognorm.com', 80))
proxy.start_up()
