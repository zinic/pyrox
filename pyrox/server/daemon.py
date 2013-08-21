import signal
import pynsive

from pyrox.log import get_logger, get_log_manager
from pyrox.config import load_config
from tornado.ioloop import IOLoop
from pyrox.server.proxy import TornadoHttpProxy


_LOG = get_logger(__name__)


class ConfigurationError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return 'Config error halted daemon start. Reason: {}'.format(
            self.msg)


def stop(signum, frame):
    _LOG.debug('Stop called at frame:\n{}'.format(frame))
    IOLoop.instance().stop()


def build_fc_factories(cfg):
    resolved_filters = dict()

    for alias in cfg.pipeline.upstream():
        fdef = getattr(cfg.pipeline, alias)
        print('Would import {}'.format(fdef))

    for alias in cfg.pipeline.downstream():
        fdef = getattr(cfg.pipeline, alias)
        print('Would import {}'.format(fdef))


def start_pyrox(fc_factory, other_cfg=None):
    config = load_config(other_cfg) if other_cfg else load_config()

    # Init logging
    logging_manager = get_log_manager()
    logging_manager.configure(config)

    # Resolve our filter chains
    try:
        fc_factories = build_fc_factories(config)
    except Exception as ex:
        _LOG.exception(ex)
        return -1

    # Create proxy server ref
    http_proxy = TornadoHttpProxy(
        fc_factory,
        config.routing.upstream_hosts[0])
    _LOG.info('Upstream targets are: {}'.format(
        ['http://{0}:{1}'.format(dst[0], dst[1])
            for dst in config.routing.upstream_hosts]))

    # Set bind host
    bind_host = config.core.bind_host.split(':')
    if len(bind_host) != 2:
        raise ConfigurationError('bind_host must have a port specified')

    # Bind the server
    http_proxy.bind(address=bind_host[0], port=int(bind_host[1]))
    _LOG.info('Pyrox listening on: http://{0}:{1}'.format(
        bind_host[0], bind_host[1]))

    # Start Tornado
    http_proxy.start(config.core.processes)
    IOLoop.instance().start()


# Take over SIGTERM and SIGINT
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
