import os.path

from pyrox.env import get_logger
from ConfigParser import ConfigParser

PYROX_CORE = 'core'
PYROX_PLUGINS = 'plugins'
PYROX_PIPELINE = 'pipeline'
PYROX_ROUTING = 'routing'
PYROX_LOGGING = 'logging'
PYROX_DEFAULTS = 'defaults'

_DEFAULT_CFG = '/etc/pyrox/pyrox.conf'

_LOG = get_logger(__name__)

_CFG_DEFAULTS = {
    PYROX_CORE: {
        'processes': 1
    },

    PYROX_PLUGINS: {
    },

    PYROX_PIPELINE: {
    },

    PYROX_ROUTING: {
    },

    PYROX_LOGGING: {
    },

    PYROX_DEFAULTS: {
        'status_code': 400
    }
}


def load_config(location=_DEFAULT_CFG):
    if not os.path.isfile(location):
        config_exception_msg = \
            'Unable to locate configuration file: {}'.format(location)
        _LOG.error(config_exception_msg)
        raise Exception(config_exception_msg)

    cfg = ConfigParser(_CFG_DEFAULTS)
    cfg.read(location)
    _LOG.info('Pyrox configuration file loaded from: {}'.format(location))
    return PyroxConfiguration(cfg)


class PyroxConfiguration(object):

    def __init__(self, cfg):
        self.core = CoreConfiguration(cfg)


class ConfigurationObject(object):

    def __init__(self, cfg):
        self._cfg = cfg
        self._namespace = self._format_namespace()

    def _format_namespace(self):
        clazz = type(self)
        return clazz.__name__.replace('Configuration', '').lower()

    def _get(self, variable):
        return self._cfg.get(self._namespace, variable)

    def _getint(self, variable):
        return self._cfg.getint(self._namespace, variable)


class CoreConfiguration(ConfigurationObject):

    @property
    def processes(self):
        """
        Returns the number of processes Pyrox should spin up to handle
        messages. If unset, this defaults to 0 which informs the system to
        discover the number of available CPUs and assign a process to each.
        """
        return self._getint('processes')
