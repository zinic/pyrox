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
    'pipeline': {
        'use_singletons': False
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


def _split_and_strip(values_str, split_on):
    if split_on in values_str:
        return (value.strip() for value in values_str.split(split_on))
    else:
        return (values_str,)


def _host_tuple(host_str):
    parts = host_str.split(':')
    if len(parts) == 1:
        return (parts[0], 80)
    elif len(parts) == 2:
        return (parts[0], int(parts[1]))
    else:
        raise Exception('Malformed host: {}'.format(host))


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

    def __getattr__(self, name):
        return self._get(name)

    def _format_namespace(self):
        return type(self).__name__.replace('Configuration', '').lower()

    def _options(self):
        return self._cfg.options(self._namespace)

    def _has_option(self, option):
        return self._cfg.has_option(self._namespace, option)

    def _get_default(self, option):
        if option in _CFG_DEFAULTS[self._namespace]:
            return _CFG_DEFAULTS[self._namespace][option]
        return None

    def _get(self, option):
        if self._has_option(option):
            return self._cfg.get(self._namespace, option)
        else:
            return self._get_default(option)

    def _getboolean(self, option):
        if self._has_option(option):
            return self._cfg.getboolean(self._namespace, option)
        else:
            return self._get_default(option)

    def _getint(self, option):
        if self._has_option(option):
            return self._cfg.getint(self._namespace, option)
        else:
            return self._get_default(option)


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
    def plugin_paths(self):
        """
        Returns a list of directories to plug into when attempting to resolve
        the names of pipeline filters. This option may be a single directory or
        a comma delimited list of directories.

        Example
        -------
        plugin_paths = /usr/share/project/python
        plugin_paths = /usr/share/project/python,/usr/share/other/python
        """
        paths = self._get('plugin_paths')
        if paths:
            return [path for path in _split_and_strip(paths, ',')]
        else:
            return list()

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

    Configuring a pipeline requires the admin to first configure aliases to
    each filter referenced. This is done by adding a named configuration
    option to this section that does not match "upstream" or "downstream."
    Filter aliases must point to a class or function that returns a filter
    instance with the expected entry points.

    After the filter aliases are specified, they may be then organized in
    comma delimited lists and assigned to either the "upstream" option for
    filters that should recieve upstream events or the "downstream" option
    for filters that should recieve downstream events.

    In the context of Pyrox, upstream events originate from the requesting
    client also known as the request. Downstream events originate from the
    origin service (the upstream request target) and is also known as the
    response.

    Example Pipeline Configuration
    ---------------------
    filter_1 = myfilters.upstream.Filter1
    filter_2 = myfilters.upstream.Filter2
    filter_3 = myfilters.downstream.Filter3

    upstream = filter_1, filter_2
    downstream = filter_3
    """
    @property
    def use_singletons(self):
        """
        Returns a boolean value representing whether or not Pyrox should
        reuse filter instances for up and downstream aliases. This means,
        effectively, that a filter specified in both pipelines will
        maintain its state for the request and response lifecycle. If left
        unset this option defaults to false.
        """
        return self._getboolean('use_singletons')

    @property
    def upstream(self):
        """
        Returns the list of filters configured to handle upstream events.
        This configuration option must be a comma delimited list of filter
        aliases. If left unset this option defaults to an empty list.
        """
        return self._pipeline_for('upstream')

    @property
    def downstream(self):
        """
        Returns the list of filters configured to handle downstream events.
        This configuration option must be a comma delimited list of filter
        aliases. If left unset this option defaults to an empty tuple.
        """
        return self._pipeline_for('downstream')

    def _pipeline_for(self, stream):
        pipeline = list()
        filters = self._filter_dict()
        pipeline_str = self._get(stream)
        if pipeline_str:
            for pl_filter in _split_and_strip(pipeline_str, ','):
                if pl_filter in filters:
                    pipeline.append(filters[pl_filter])
        return pipeline

    def _filter_dict(self):
        filters = dict()
        for pfalias in self._options():
            if pfalias == 'downstream' or pfalias == 'upstream':
                continue
            filters[pfalias] = self._get(pfalias)
        return filters


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
        hosts = self._get('upstream_hosts')
        return [_host_tuple(host) for host in _split_and_strip(hosts, ',')]
