import signal
import pynsive

from pyrox.log import get_logger, get_log_manager
from pyrox.config import load_config
from pyrox.http.filtering import HttpFilterPipeline
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


def _build_pipeline_factory(filters):
    filter_cls_list = list()

    # Gather the classes listed in the order they're listed
    for fdef in filters:
        module_name = fdef[:fdef.rfind('.')]
        cls_name = fdef[fdef.rfind('.') + 1:]
        module = pynsive.import_module(module_name)
        cls = getattr(module, cls_name)
        print('Got class: {}'.format(cls))
        filter_cls_list.append(cls)

    # Closure for creation of new pipelines
    def new_filter_pipeline():
        pipeline = HttpFilterPipeline()
        for filter_cls in filter_cls_list:
            pipeline.add_filter(filter_cls())
        return pipeline
    return new_filter_pipeline


def _build_fc_factories(config):
    upstream = _build_pipeline_factory(config.pipeline.upstream)
    downstream = _build_pipeline_factory(config.pipeline.downstream)
    return (upstream, downstream)

def start_pyrox(other_cfg=None):
    config = load_config(other_cfg) if other_cfg else load_config()

    # Init logging
    logging_manager = get_log_manager()
    logging_manager.configure(config)

    # Create a PluginManager
    plugin_manager = pynsive.PluginManager()
    for path in config.core.plugin_paths:
        plugin_manager.plug_into(path)

    # Resolve our filter chains
    try:
        filter_pipeline_factories = _build_fc_factories(config)
    except Exception as ex:
        _LOG.exception(ex)
        return -1

    # Create proxy server ref
    http_proxy = TornadoHttpProxy(
        filter_pipeline_factories,
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
