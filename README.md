# Pyrox
The high-speed HTTP middleware proxy for python.

## Features
* Based on much of the code found in the [Joyent HTTP Parser](https://github.com/joyent/http-parser)
* Utilizes [Tornado Async I/O](http://www.tornadoweb.org/en/stable/)

## Building Pyrox

Building pyrox requires a few dependencies. The cython dependency has been
stored in [tools/dev-requires](https://github.com/zinic/pyrox/blob/master/tools/dev-requires)
in the case where the software is being installed as a pre-built package. For
development use cases, installing cython is required.

```bash
pip install -r tools/dev-requires
pip install -r tools/pip-requires
pip install -r tools/test-requires
python setup.py build && python setup.py build_ext --inplace
nosetests
```

## Running Pyrox

After building pyrox you should be able to run it with the proxy shell script
located within the project root.

```bash
./pyrox
```

##That Legal Thing...

This software library is released to you under the [MIT License](http://opensource.org/licenses/MIT). See [LICENSE](https://github.com/zinic/pyrox/blob/master/LICENSE) for more information.

