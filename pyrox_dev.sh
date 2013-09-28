#!/bin/sh

MAIN_PY=pkg/layout/usr/share/pyrox/main.py

export PYTHONPATH=${PYTHONPATH}:./

#python -m cProfile -o /tmp/profile.prof ${MAIN_PY} ${@}
python ${MAIN_PY} ${@}
