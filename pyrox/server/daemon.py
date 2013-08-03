import signal
import pyrox.env as env

from tornado.ioloop import IOLoop
from pyrox.server.proxy import TornadoHttpProxy


_LOG = env.get_logger(__name__)


def stop(signum, frame):
    _LOG.debug('Stop called at frame:\n{}'.format(str(frame)))
    IOLoop.instance().stop()

def start(bind_address, downstream_host, fc_factory, processes=0):
    http_proxy = TornadoHttpProxy(fc_factory, downstream_host)
    http_proxy.bind(address=bind_address[0], port=bind_address[1])
    http_proxy.start(processes)
    IOLoop.instance().start()

# Take over SIGTERM and SIGINT
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

