Building Pyrox
==============

Requirements
~~~~~~~~~~~~

Pyrox is a complex daemon that requires a few things installed in your
development environment before it can be built.

* GCC (Tested on versions **4.6.x** and **4.7.x**)
* Python Development Libaries

**Installing Python Dependencies and Building Pyrox**

::

    # This requirements file contains requirements related only to Pyrox development
    pip install -r tools/dev-requires

    # This requirements file contains requirements needed to install and run Pyrox
    pip install -r tools/pip-requires

    # This requirements file contains requirements needed to test Pyrox
    pip install -r tools/test-requires

    # This script will auto-build Pyrox and then launch it
    ./pyrox_dev.sh start
