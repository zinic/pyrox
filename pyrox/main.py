import os
import sys
import argparse

from pyrox.log import get_logger
import pyrox.server as server

from pyrox.http.filtering import HttpFilterPipeline
#from pyrox.stock_filters.simple import SimpleFilter


_LOG = get_logger(__name__)

_FTEST_CONFIG_KEY = 'keystone_meniscus_ftest'

args_parser = argparse.ArgumentParser(
    prog='proxy',
    description='Pyrox, the fast Python HTTP middleware server.')
args_parser.add_argument(
    '-c',
    nargs='?',
    dest='other_cfg',
    default=None,
    help="""
        Sets the configuration file to load on startup. If unset this
        option defaults to /etc/pyrox/pyrox.conf""")
args_parser.add_argument(
    '-p',
    nargs='?',
    dest='plugin_paths',
    default=None,
    help=('"{}" character separated string of paths to '
          'import from when loading plugins.'.format(os.sep)))
args_parser.add_argument(
    'start',
    default=False,
    help='Starts the daemon.')


def start(args):
    server.start_pyrox(other_cfg=args.other_cfg)


if len(sys.argv) > 1:
    args = args_parser.parse_args()
    if args.start:
        start(args)
else:
    args_parser.print_help()
