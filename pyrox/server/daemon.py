import signal

from pyrox.log import get_logger, get_log_manager
from pyrox.config import load_config
from tornado.ioloop import IOLoop
from pyrox.server.proxy import TornadoHttpProxy


_LOG = get_logger(__name__)


class ConfigurationError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return 'Config error halted daemon start. Reason: {}'.format(self.msg)


def stop(signum, frame):
    _LOG.debug('Stop called at frame:\n{}'.format(frame))
    IOLoop.instance().stop()


def start_pyrox(fc_factory, other_cfg=None):
    config = load_config(other_cfg) if other_cfg else load_config()

    # Init logging
    logging_manager = get_log_manager()
    logging_manager.configure(config)

    # Create proxy server ref
    http_proxy = TornadoHttpProxy(
        fc_factory,
        config.routing.downstream_hosts[0])

    # Set bind host
    bind_host = config.core.bind_host.split(':')
    if len(bind_host) != 2:
        raise ConfigurationError('bind_host must have a port specified')
    http_proxy.bind(address=bind_host[0], port=int(bind_host[1]))

    # Start Tornado
    http_proxy.start(config.core.processes)
    IOLoop.instance().start()


# Take over SIGTERM and SIGINT
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
