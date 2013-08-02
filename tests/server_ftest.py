from pyrox.server import new_server


# This is a cheesy functional test for the proxy server while I work out
# the async tornado stuff...
proxy = new_server(
    ('127.0.0.1', 8080),
    downstream_target=('www.liblognorm.com', 80))
proxy.start_up()
