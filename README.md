# Pyrox
The high-speed HTTP middleware proxy for python.

## Features
* Based on much of the code found in the [Joyent HTTP Parser](https://github.com/joyent/http-parser)
* Utilizes [Tornado Async I/O](http://www.tornadoweb.org/en/stable/)

## Building Pyrox
```bash
pip install -r tools/dev-requires
pip install -r tools/pip-requires
pip install -r tools/test-requires
python setup.py build && python setup.py build_ext --inplace
nosetests
```

##That Legal Thing...

This software library is released to you under the [MIT License](http://opensource.org/licenses/MIT). See [LICENSE](https://github.com/zinic/pyrox/blob/master/LICENSE) for more information.

