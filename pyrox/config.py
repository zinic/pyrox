import os.path

from ConfigParser import ConfigParser


_CFG_DEFAULTS = {
    'core': {
        'processes': 1,
        'bind_host': 'localhost:8080'
    },
    'routing': {
        'upstream_hosts': 'localhost:80'
    },
    'templates': {
        'pyrox_error_sc': 502,
        'rejection_sc': 400
    },
    'logging': {
        'console': True,
        'logfile': None,
        'verbosity': 'WARNING'
    }
}


def load_config(location='/etc/pyrox/pyrox.conf'):
    if not os.path.isfile(location):
        raise Exception(
            'Unable to locate configuration file: {}'.format(location))
    cfg = ConfigParser()
    cfg.read(location)
    return PyroxConfiguration(cfg)


class PyroxConfiguration(object):
    """
    A Pyrox configuration.
    """
    def __init__(self, cfg):
        self.core = CoreConfiguration(cfg)
        self.routing = RoutingConfiguration(cfg)
        self.pipeline = PipelineConfiguration(cfg)
        self.templates = TemplatesConfiguration(cfg)
        self.logging = LoggingConfiguration(cfg)


class ConfigurationObject(object):
    """
    A configuration object is an OO abstraction for a ConfigParser that allows
    for ease of documentation and usage of configuration options. All
    subclasses of ConfigurationObject must follow a naming convention. A
    configuration object subclass must start with the name of its section. This
    must then be followed by the word "Configuration." This convention results
    in subclasses with names similar to: CoreConfiguration and
    LoggingConfiguration.

    A configuration object subclass will have its section set to the lowercase
    name of the subclass sans the word such that a subclass with the name,
    "LoggingConfiguration" will reference the ConfigParser section "logging"
    when looking up options.
    """
    def __init__(self, cfg):
        self._cfg = cfg
        self._namespace = self._format_namespace()

    def _format_namespace(self):
        return type(self).__name__.replace('Configuration', '').lower()

    def _has_option(self, option):
        return self._cfg.has_option(self._namespace, option)

    def _get(self, option):
        if self._has_option(option):
            return self._cfg.get(self._namespace, option)
        else:
            return _CFG_DEFAULTS[self._namespace][option]

    def _getint(self, option):
        if self._has_option(option):
            return self._cfg.getint(self._namespace, option)
        else:
            return int(_CFG_DEFAULTS[self._namespace][option])


class CoreConfiguration(ConfigurationObject):
    """
    Class mapping for the Pyrox configuration section 'core'
    """
    @property
    def processes(self):
        """
        Returns the number of processess Pyrox should spin up to handle
        messages. If unset, this defaults to 1.

        Example
        --------
        processes = 0
        """
        return self._getint('processes')

    @property
    def bind_host(self):
        """
        Returns the host and port the proxy is expected to bind to when
        accepting connections. This option defaults to localhost:8080 if left
        unset.

        Example
        --------
        bind_host = localhost:8080
        """
        return self._get('bind_host')


class LoggingConfiguration(ConfigurationObject):
    """
    Class mapping for the Pyrox configuration section 'logging'
    """
    @property
    def console(self):
        """
        Returns a boolean representing whether or not Pyrox should write to
        stdout for logging purposes. This value may be either True of False. If
        unset this value defaults to False.
        """
        return self._get('console')

    @property
    def logfile(self):
        """
        Returns the log file the system should write logs to. When set, Pyrox
        will enable writing to the specified file for logging purposes If unset
        this value defaults to None.
        """
        return self._get('logfile')

    @property
    def verbosity(self):
        """
        Returns the type of log messages that should be logged. This value may
        be one of the following: DEBUG, INFO, WARNING, ERROR or CRITICAL. If
        unset this value defaults to WARNING.
        """
        return self._get('verbosity')


class PipelineConfiguration(ConfigurationObject):
    """
    Class mapping for the Pyrox configuration section 'pipeline'
    """
    @property
    def upstream(self):
        pass

    @property
    def downstream(self):
        pass

    @property
    def downstream(self):
        pass



class TemplatesConfiguration(ConfigurationObject):
    """
    Class mapping for the Pyrox configuration section 'templates'
    """
    @property
    def pyrox_error_sc(self):
        """
        Returns the status code to be set for any error that happens within
        Pyrox that would prevent normal service of client requests. If left
        unset this option defaults to 502.
        """
        return self._getint('pyrox_error_sc')

    @property
    def rejection_sc(self):
        """
        Returns the default status code to be set for client request
        rejection made with no provided response object to serialize. If
        left unset this option defaults to 400.
        """
        return self._getint('rejection_sc')


def _host_to_tuple(raw_host):
    parts = raw_host.split(':')
    if len(parts) == 1:
        return (parts[0], 80)
    elif len(parts) == 2:
        return (parts[0], int(parts[1]))
    else:
        raise Exception('Malformed host: {}'.format(host))


class RoutingConfiguration(ConfigurationObject):
    """
    Class mapping for the Pyrox configuration section 'routing'
    """
    @property
    def upstream_hosts(self):
        """
        Returns a list of downstream hosts to proxy requests to. This may be
        set to either a single host and port or a comma delimited list of hosts
        and their associated ports. This option defaults to localhost:80 if
        left unset.

        Examples
        --------
        upstream_hosts = host:port
        upstream_hosts = host:port,host:port,host:port
        upstream_hosts = host:port, host:port, host:port
        """
        ds_hosts = self._get('upstream_hosts')
        if ',' in ds_hosts:
            hosts = (host.strip() for host in ds_hosts.split(','))
        else:
            hosts = (ds_hosts,)
        return [_host_to_tuple(host) for host in hosts]
