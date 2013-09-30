#!/bin/sh

MAIN_PY=pkg/layout/usr/share/pyrox/bin/main.py

export PYTHONPATH=${PYTHONPATH}:./

# Build the project
python setup.py build >> /dev/null 2>&1

if [ ${?} -ne 0 ]; then
    python setup.py build
    exit 1
fi

# Build the shared libraries
python setup.py build_ext --inplace >> /dev/null 2>&1

if [ ${?} -ne 0 ]; then
    python setup.py build_ext --inplace
else
    #python -m cProfile -o /tmp/profile.prof ${MAIN_PY} ${@}
    python ${MAIN_PY} ${@}
fi
