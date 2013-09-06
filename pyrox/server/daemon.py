import signal
import pynsive

from pyrox.log import get_logger, get_log_manager
from pyrox.config import load_config
from pyrox.filtering import HttpFilterPipeline
from tornado.ioloop import IOLoop
from pyrox.server.proxyng import TornadoHttpProxy


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


def _resolve_filter_classes(cls_list):
    filter_cls_list = list()
    # Gather the classes listed in the order they're listed
    for cdef in cls_list:
        # If there's a complex module path, process the ends of it
        if '.' not in cdef:
            raise ImportError('Bad filter class: {}'.format(cdef))

        module = pynsive.import_module(cdef[:cdef.rfind('.')])
        try:
            cls = getattr(module, cdef[cdef.rfind('.') + 1:])
            filter_cls_list.append(cls)
        except AttributeError as ae:
            raise ImportError('Unable to import: {}'.format(cdef))
    return filter_cls_list


def _build_plfactory_closure(filter_cls_list):
    # Closure for creation of new pipelines
    def new_filter_pipeline():
        pipeline = HttpFilterPipeline()
        for cls in filter_cls_list:
            pipeline.add_filter(cls())
        return pipeline
    return new_filter_pipeline


def _build_singleton_plfactory_closure(filter_classes, filter_instances):
    # Closure for creation of new singleton pipelines
    def new_filter_pipeline():
        pipeline = HttpFilterPipeline()
        for cls in filter_classes:
            pipeline.add_filter(filter_instances[cls.__name__])
        return pipeline
    return new_filter_pipeline


def _build_singleton_plfactories(config):
    all_classes = list()
    filter_isntances = dict()

    # Gather all the classes
    all_classes.extend(_resolve_filter_classes(config.pipeline.upstream))
    all_classes.extend(_resolve_filter_classes(config.pipeline.downstream))

    for cls in all_classes:
        filter_instances[cls.__name__] = cls()

    upstream = _build_singleton_plfactory_closure(
        config.pipeline.upstream, filter_instances)
    downstream = _build_singleton_plfactory_closure(
        config.pipeline.downstream, filter_instances)
    return (upstream, downstream)


def _build_plfactories(config):
    upstream = _build_plfactory_closure(
        _resolve_filter_classes(config.pipeline.upstream))
    downstream = _build_plfactory_closure(
        _resolve_filter_classes(config.pipeline.downstream))
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
        if config.pipeline.use_singletons:
            filter_pipeline_factories = _build_singleton_plfactories(config)
        else:
            filter_pipeline_factories = _build_plfactories(config)
    except Exception as ex:
        _LOG.exception(ex)
        return -1

    # Create proxy server ref
    http_proxy = TornadoHttpProxy(
        filter_pipeline_factories,
        config.routing.upstream_hosts)
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
