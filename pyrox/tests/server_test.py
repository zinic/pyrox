from pyrox.server import TornadoHttpProxy, start_io

proxy = TornadoHttpProxy(('127.0.0.1', 8080))
proxy.start()
start_io()
