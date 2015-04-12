# [Pyrox](http://pyrox-http.org/)
#### The fast Python HTTP middleware server

## What is Pyrox?

#### Hosted REST Interceptors!

Pyrox is a HTTP reverse proxy that can intercept requests ahead of an upstream
HTTP REST service. This allows reuse of common middleware functions like:
message enhancement, dynamic routing, authentication, authorization, resource
request rate limiting, service distribution, content negotiation and content
transformation. These services can then be scaled horizontally separate the
origin REST endpoint.

Build on top of the [Tornado Async I/O](http://www.tornadoweb.org/en/stable/)
python library, the HTTP code inside Pyrox can scale to thousands of concurrent
clients and proxy them to a similar number of upstream REST services.

## Documentation

#### [Latest Pyrox Documentation](http://pyrox.readthedocs.org/en/latest/)

Thanks [Read the Docs](http://readthedocs.org)!

## Features

* Debian packaging targeting Ubuntu 12.04 LTS
* Extensive plugin support with the ability to source middleware code from multiple, separate plugin paths
* Fast HTTP parser written in C with much of the code based on the [Joyent HTTP Parser](https://github.com/joyent/http-parser)
* Utilizes [Tornado Async I/O](http://www.tornadoweb.org/en/stable/)
* Low dependency footprint

## Building Pyrox

Building pyrox requires only a few dependencies. For development use cases, installing cython is required.

```bash
pip install -r tools/install_requires.txt -r tools/tests_require.txt
python setup.py build_ext --inplace
nosetests
```

## Running Pyrox

After building pyrox you should be able to run it with the proxy shell script
located within the project root.

```
./pyrox_dev.sh

usage: pyrox_dev.sh [-h] [-c [OTHER_CFG]] [-p [PLUGIN_PATHS]] start

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

## Filter Examples

* [Simple request handling](https://github.com/zinic/pyrox/blob/master/examples/filter/simple_example.py)
* [Dynamic routing](https://github.com/zinic/pyrox/blob/master/examples/filter/routing_example.py)
* [Keystone Token Validation](https://github.com/zinic/pyrox-stock/blob/master/pyrox_stock/auth/openstack/keystone.py)
* [Role Based Access Controls (Based on EOM)](https://github.com/zinic/pyrox-stock/blob/master/pyrox_stock/auth/openstack/rbac.py)


## That Legal Thing...

This software library is released to you under the [MIT License](http://opensource.org/licenses/MIT). See [LICENSE](https://github.com/zinic/pyrox/blob/master/LICENSE) for more information.
