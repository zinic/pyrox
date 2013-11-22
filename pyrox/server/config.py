from pyrox.util.config import (load_config, ConfigurationPart,
                               ConfigurationError)


_DEFAULTS = {
    'core': {
        'processes': 1,
        'enable_profiling': False,
        'bind_host': 'localhost:8080'
    },
    'ssl': {
        'cert_file': None,
        'key_file': None
    },
    'routing': {
        'upstream_hosts': None
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
        raise ConfigurationError('Malformed host: {}'.format(host_str))


def load_pyrox_config(location='/etc/pyrox/pyrox.conf'):
    return load_config('pyrox.server.config', location, _DEFAULTS)


class CoreConfiguration(ConfigurationPart):
    """
    Class mapping for the Pyrox core configuration section.
    ::
        # Core section
        [core]
    """
    @property
    def processes(self):
        """
        Returns the number of processes Pyrox should spin up to handle
        messages. If unset, this defaults to 1.
        ::
            processes = 75
        """
        return self.getint('processes')

    @property
    def enable_profiling(self):
        """
        Returns a boolean value representing whether or not Pyrox should
        use a special single-process start up and run sequence so that code
        may be profiled. If unset, this defaults to False.

        **NOTE**: If enabled,  the number of processess Pyrox will be allowed
        to spin up will be limited to **1**
        ::
            enable_profiling = True
        """
        return self.getboolean('enable_profiling')

    @property
    def plugin_paths(self):
        """
        Returns a list of directories to plug into when attempting to resolve
        the names of pipeline filters. This option may be a single directory or
        a comma delimited list of directories.
        ::
            # Any of the below are acceptable
            plugin_paths = /usr/share/project/python
            plugin_paths = /usr/share/project/python,/usr/share/other/python
            plugin_paths = /opt/pyrox/stock, /opt/pyrox/contrib
        """
        paths = self.get('plugin_paths')
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
        ::
            bind_host = localhost:8080
        """
        return self.get('bind_host')


class SSLConfiguration(ConfigurationPart):
    """
    Class mapping for the Portal configuration section 'ssl'
    """
    @property
    def cert_file(self):
        """
        Returns the path of the cert file for SSL configuration within
        Pyrox. If left unset the value will default to None.

        ::
            cert_file = /etc/pyrox/ssl/server.cert
        """
        return self.get('cert_file')

    @property
    def key_file(self):
        """
        Returns the path of the key file for SSL configuration within
        Pyrox. If left unset the value will default to None.

        ::
            key_file = /etc/pyrox/ssl/server.key
        """
        return self.get('key_file')


class LoggingConfiguration(ConfigurationPart):
    """
    Class mapping for the Pyrox logging configuration section.
    ::
        # Logging section
        [logging]
    """
    @property
    def console(self):
        """
        Returns a boolean representing whether or not Pyrox should write to
        stdout for logging purposes. This value may be either True of False. If
        unset this value defaults to False.
        ::
            console = True
        """
        return self.get('console')

    @property
    def logfile(self):
        """
        Returns the log file the system should write logs to. When set, Pyrox
        will enable writing to the specified file for logging purposes If unset
        this value defaults to None.
        ::
            logfile = /var/log/pyrox/pyrox.log
        """
        return self.get('logfile')

    @property
    def verbosity(self):
        """
        Returns the type of log messages that should be logged. This value may
        be one of the following: DEBUG, INFO, WARNING, ERROR or CRITICAL. If
        unset this value defaults to WARNING.
        ::
            verbosity = DEBUG
        """
        return self.get('verbosity')


class PipelineConfiguration(ConfigurationPart):
    """
    Class mapping for the Pyrox pipeline configuration section.
    ::
        # Pipeline section
        [pipeline]

    Configuring a pipeline requires the admin to first configure aliases to
    each filter referenced. This is done by adding a named configuration
    option to this section that does not match "upstream" or "downstream."
    Filter aliases must point to a class or function that returns a filter
    instance with the expected entry points.

    After the filter aliases are specified, they may be then organized in
    comma delimited lists and assigned to either the "upstream" option for
    filters that should receive upstream events or the "downstream" option
    for filters that should receive downstream events.

    In the context of Pyrox, upstream events originate from the requesting
    client also known as the request. Downstream events originate from the
    origin service (the upstream request target) and is also known as the
    response.
    ::
        [pipeline]
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
        ::
            use_singletons = True
        """
        return self.getboolean('use_singletons')

    @property
    def upstream(self):
        """
        Returns the list of filters configured to handle upstream events.
        This configuration option must be a comma delimited list of filter
        aliases. If left unset this option defaults to an empty list.
        ::
            upstream = filter_1, filter_2
        """
        return self._pipeline_for('upstream')

    @property
    def downstream(self):
        """
        Returns the list of filters configured to handle downstream events.
        This configuration option must be a comma delimited list of filter
        aliases. If left unset this option defaults to an empty tuple.
        ::
            downstream = filter_3
        """
        return self._pipeline_for('downstream')

    def _pipeline_for(self, stream):
        pipeline = list()
        filters = self._filter_dict()
        pipeline_str = self.get(stream)
        if pipeline_str:
            for pl_filter in _split_and_strip(pipeline_str, ','):
                if pl_filter in filters:
                    pipeline.append(filters[pl_filter])
        return pipeline

    def _filter_dict(self):
        filters = dict()
        for pfalias in self.options():
            if pfalias == 'downstream' or pfalias == 'upstream':
                continue
            filters[pfalias] = self.get(pfalias)
        return filters


class TemplatesConfiguration(ConfigurationPart):
    """
    Class mapping for the Pyrox teplates configuration section.
    ::
        # Templates section
        [templates]
    """
    @property
    def pyrox_error_sc(self):
        """
        Returns the status code to be set for any error that happens within
        Pyrox that would prevent normal service of client requests. If left
        unset this option defaults to 502.
        ::
            pyrox_error_sc = 502
        """
        return self.getint('pyrox_error_sc')

    @property
    def rejection_sc(self):
        """
        Returns the default status code to be set for client request
        rejection made with no provided response object to serialize. If
        left unset this option defaults to 400.
        ::
            rejection_sc = 400
        """
        return self.getint('rejection_sc')


class RoutingConfiguration(ConfigurationPart):
    """
    Class mapping for the Pyrox routing configuration section.
    ::
        # Routing section
        [routing]
    """
    @property
    def upstream_hosts(self):
        """
        Returns a list of downstream hosts to proxy requests to. This may be
        set to either a single valid URL string or a comma delimited list of
        valid URI strings. This option defaults to http://localhost:80 if
        left unset.
        ::
            upstream_hosts = http://host:port, https://host:port
        """
        hosts = self.get('upstream_hosts')

        if hosts is not None:
            return [host for host in _split_and_strip(hosts, ',')]
        return None
