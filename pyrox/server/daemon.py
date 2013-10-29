import os
import sys
import errno
import signal
import pynsive
import inspect
import socket
import multiprocessing

from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets
from tornado.process import cpu_count

from pyrox.log import get_logger, get_log_manager
from pyrox.filtering import HttpFilterPipeline
from pyrox.util.config import ConfigurationError
from pyrox.server.config import load_pyrox_config
from pyrox.server.proxyng import TornadoHttpProxy


_LOG = get_logger(__name__)
_active_children_pids = list()


class FunctionWrapper(object):

    def __init__(self, func):
        self._func = func

    def on_request(self, request):
        return self._func(request)

    def on_response(self, response):
        return self._func(response)


def stop_child(signum, frame):
    IOLoop.instance().add_callback_from_signal(
        lambda: IOLoop.current().stop())


def stop_parent(signum, frame):
    for pid in _active_children_pids:
        os.kill(pid, signal.SIGTERM)


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
            if inspect.isclass(cls):
                filter_cls_list.append(cls)
            elif inspect.isfunction(cls):
                def create():
                    return FunctionWrapper(cls)
                filter_cls_list.append(create)
            else:
                raise TypeError(
                    'Type of a filter must be a function or a class')
        except AttributeError:
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
    filter_instances = dict()

    # Gather all the classes
    all_classes.extend(_resolve_filter_classes(config.pipeline.upstream))
    all_classes.extend(_resolve_filter_classes(config.pipeline.downstream))

    for cls in all_classes:
        filter_instances[cls.__name__] = cls()

    upstream = _build_singleton_plfactory_closure(
        _resolve_filter_classes(config.pipeline.upstream), filter_instances)
    downstream = _build_singleton_plfactory_closure(
        _resolve_filter_classes(config.pipeline.downstream), filter_instances)
    return upstream, downstream


def _build_plfactories(config):
    upstream = _build_plfactory_closure(
        _resolve_filter_classes(config.pipeline.upstream))
    downstream = _build_plfactory_closure(
        _resolve_filter_classes(config.pipeline.downstream))
    return upstream, downstream


def start_proxy(sockets, config):
    # Take over SIGTERM and SIGINT
    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)

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

    # Load any SSL configurations
    ssl_options = None

    cert_file = config.ssl.cert_file
    key_file = config.ssl.key_file

    if None not in (cert_file, key_file):
        ssl_options = dict()
        ssl_options['certfile'] = cert_file
        ssl_options['keyfile'] = key_file

        _LOG.debug('SSL enabled: {}'.format(ssl_options))

    # Create proxy server ref
    http_proxy = TornadoHttpProxy(
        filter_pipeline_factories,
        config.routing.upstream_hosts,
        ssl_options)

    # Add our sockets for watching
    http_proxy.add_sockets(sockets)

    # Start tornado
    IOLoop.current().start()

    # import cProfile
    # cProfile.runctx('IOLoop.current().start()', globals(), locals())


def start_pyrox(other_cfg=None):
    config = load_pyrox_config(other_cfg) if other_cfg else load_pyrox_config()

    # Init logging
    logging_manager = get_log_manager()
    logging_manager.configure(config)

    _LOG.info('Upstream targets are: {}'.format(
        [dst for dst in config.routing.upstream_hosts]))

    # Set bind host
    bind_host = config.core.bind_host.split(':')
    if len(bind_host) != 2:
        raise ConfigurationError('bind_host must have a port specified')

    # Bind the sockets in the main process
    sockets = bind_sockets(port=bind_host[1], address=bind_host[0])

    # Bind the server port(s)
    _LOG.info('Pyrox listening on: http://{0}:{1}'.format(
        bind_host[0], bind_host[1]))

    # Start Tornado
    num_processes = config.core.processes

    if num_processes <= 0:
        num_processes = cpu_count()

    global _active_children_pids

    for i in range(num_processes):
        pid = os.fork()
        if pid == 0:
            print('Starting process {}'.format(i))
            start_proxy(sockets, config)
            sys.exit(0)
        else:
            _active_children_pids.append(pid)

    # Take over SIGTERM and SIGINT
    signal.signal(signal.SIGTERM, stop_parent)
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    while len(_active_children_pids):
        try:
            pid, status = os.wait()
        except OSError as oserr:
            if oserr.errno != errno.EINTR:
                _LOG.exception(oserr)
            continue
        except Exception as ex:
            _LOG.exception(ex)
            continue

        _LOG.info('Child process {} exited with status {}'.format(
            pid, status))
        _active_children_pids.remove(pid)
