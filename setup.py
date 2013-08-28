# -*- coding: utf-8 -*-
import sys
import os

import pyrox.http.parser as parser

from setuptools import setup, find_packages
from distutils.extension import Extension

try:
    from Cython.Compiler.Main import compile
    from Cython.Distutils import build_ext
    has_cython = True
except ImportError:
    has_cython = False


def read(relative):
    contents = open(relative, 'r').read()
    return [l for l in contents.split('\n') if l != '']


ext_modules = list()
ext_modules.append(parser.ffi.verifier.get_extension())

setup(
    name='pyrox',
    version=read('VERSION')[0],
    description='The high-speed HTTP middleware proxy for Python',
    author='John Hopper',
    author_email='john.hopper@jpserver.net',
    url='https://github.com/zinic/pyrox',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Other Environment',
        'Natural Language :: English',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Cython',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Topic :: Internet',
        'Topic :: Utilities'
    ],
    tests_require=read('./tools/test-requires'),
    install_requires=read('./tools/pip-requires'),
    test_suite='nose.collector',
    zip_safe=False,
    include_package_data=True,
    packages=find_packages(exclude=['*.tests']),
    ext_modules=ext_modules)
