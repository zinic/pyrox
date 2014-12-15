#!/bin/sh

MAIN_PY=scripts/pyrox

export PYTHONPATH=${PYTHONPATH}:./

find ./pyrox -name '*.so' >> /dev/null 2>&1

case $(find ./pyrox -name '*.so' -print -quit) in
    '')
        # Build the project
        python setup.py build >> /dev/null 2>&1

        if [ ${?} -ne 0 ]; then
            python setup.py build
            exit ${?}
        fi

        # Build the shared libraries
        python setup.py build_ext --inplace >> /dev/null 2>&1
        ;;
esac

if [ ${?} -ne 0 ]; then
    python setup.py build_ext --inplace
else
    python ${PYTHON_ARGS} ${MAIN_PY} ${@}
fi
