# -*- coding: utf-8 -*-
import os
import sys
import pyrox.about

from setuptools import setup, find_packages, Extension


# force setuptools not to convert .pyx to .c in the Extension
import setuptools.extension
assert callable(setuptools.extension.have_pyrex), "Requires setuptools 0.6.26 or later"
setuptools.extension.have_pyrex = lambda: True

# https://bitbucket.org/pypa/setuptools/issues/288/cannot-specify-cython-under-setup_requires
class LateResolvedCommandLookup(dict):
    """
    A dictionary of distutils commands with overrides to be resolved late.
    Late-resolved commands should be implemented as callable methods on
    the class.

    This class allows 'build_ext' to be resolve after setup_requires resolves
    dependencies such as Cython.
    """
    def __getitem__(self, name):
        if getattr(self, name, None):
            return getattr(self, name)()
        return super(LateResolvedCommandLookup, self).__getitem__(name)

    def __contains__(self, name):
        return hasattr(self, name) or (
            super(LateResolvedCommandLookup, self).__contains__(name))

    def build_ext(self):
        Cython = __import__('Cython.Distutils.build_ext')
        return Cython.Distutils.build_ext


def read(relative):
    contents = open(relative, 'r').read()
    return [l for l in contents.split('\n') if l != '']


def compile_pyx():
    ext_modules = list()

    e = Extension('pyrox.http.parser',
            sources=['pyrox/http/parser.pyx'],
            include_dirs = ['include/'])
    ext_modules.append(e)

    e = Extension('pyrox.http.model_util',
            sources=['pyrox/http/model_util.pyx'],
            include_dirs = ['include/'])
    ext_modules.append(e)

    return ext_modules


# compiler flags
CFLAGS = []
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
    setup_requires=read('tools/setup_requires.txt'),
    tests_require=read('tools/tests_require.txt'),
    install_requires=read('tools/install_requires.txt'),
    test_suite='nose.collector',
    zip_safe=False,
    package_data={
        '': ['*.pyx']
    },
    include_package_data=True,
    packages=find_packages(exclude=['*.tests']),
    ext_modules=compile_pyx(),
    cmdclass=LateResolvedCommandLookup(),
)
