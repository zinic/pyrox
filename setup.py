# -*- coding: utf-8 -*-
import os
import sys
import pyrox.about

from setuptools import setup, find_packages
from distutils.extension import Extension

try:
    from Cython.Build import cythonize
    has_cython = True
except ImportError:
    has_cython = False


def read(relative):
    contents = open(relative, 'r').read()
    return [l for l in contents.split('\n') if l != '']


def compile_pyx():
    ext_modules = list()

    cparser = cythonize('pyrox/http/parser.pyx')[0]
    cparser.sources.insert(0, 'include/http_el.c')
    ext_modules.append(cparser)

    ext_modules.extend(cythonize('pyrox/http/model_util.pyx'))

    return ext_modules


# compiler flags
CFLAGS = ['-I', './include']
DEBUG = os.getenv('DEBUG')

if DEBUG and DEBUG.lower() == 'true':
    CFLAGS.extend(['-D', 'DEBUG_OUTPUT'])

os.environ['CFLAGS'] = ' '.join(CFLAGS)


setup(
    name='pyrox',
    version=pyrox.about.VERSION,
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
    scripts=['scripts/pyrox'],
    tests_require=read('tools/tests_require.txt'),
    install_requires=read('tools/install_requires.txt'),
    test_suite='nose.collector',
    zip_safe=False,
    package_data={
        '': ['*.pyx']
    },
    include_package_data=True,
    packages=find_packages(exclude=['*.tests']),
    ext_modules=compile_pyx())
