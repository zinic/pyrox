# [Pyrox](http://pyrox-http.org/)
The fast Python HTTP middleware server

## Features
* Fast HTTP parser written in C with much of the code based on the [Joyent HTTP Parser](https://github.com/joyent/http-parser)
* Utilizes [Tornado Async I/O](http://www.tornadoweb.org/en/stable/)
* Low dependency footprint

## Building Pyrox

Building pyrox requires only a few dependencies. The cython dependency has been
stored in [tools/dev-requires](https://github.com/zinic/pyrox/blob/master/tools/dev-requires)
in the case where the software is being installed as a pre-built package. For
development use cases, installing cython is required.

```bash
pip install -r tools/dev-requires -r tools/pip-requires -r tools/test-requires
python setup.py build && python setup.py build_ext --inplace
nosetests
```

## Running Pyrox

After building pyrox you should be able to run it with the proxy shell script
located within the project root.

```
./proxy

usage: proxy [-h] [-c [OTHER_CFG]] [-p [PLUGIN_PATHS]] start

Pyrox, the fast Python HTTP middleware server.

positional arguments:
  start              Starts the daemon.

optional arguments:
  -h, --help         show this help message and exit
  -c [OTHER_CFG]     Sets the configuration file to load on startup. If unset
                     this option defaults to /etc/pyrox/pyrox.conf
  -p [PLUGIN_PATHS]  "/" character separated string of paths to import from
                     when loading plugins.
```

## Using Pyrox

### Configuration

See the configuration documentation here: TODO

* [Configuration Example](https://github.com/zinic/pyrox/blob/master/examples/config/pyrox.conf)

### Filters

Filters in Pyrox allow a programmer to act upon a request or a response. They
may contain custom code and may be loaded from different paths.

#### Examples

* [Simple request handling](https://github.com/zinic/pyrox/blob/master/examples/filter/simple_example.py)
* [Dynamic routing](https://github.com/zinic/pyrox/blob/master/examples/filter/routing_example.py)
* [Keystone auth passthrough](https://github.com/zinic/pyrox/blob/master/examples/filter/keystone_meniscus_example.py)


##That Legal Thing...

This software library is released to you under the [MIT License](http://opensource.org/licenses/MIT). See [LICENSE](https://github.com/zinic/pyrox/blob/master/LICENSE) for more information.

