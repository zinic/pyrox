from pyrox.server import TornadoHttpProxy, start_io


# This is a cheesy functional test for the proxy server while I work out
# the async tornado stuff...
proxy = TornadoHttpProxy(
    ('127.0.0.1', 8080),
    downstream_target=('www.liblognorm.com', 80))
proxy.start(0)
start_io()
