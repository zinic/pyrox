import os
import sys
import argparse

from pyrox.env import get_logger
import pyrox.server as server

from pyrox.http.filtering import HttpFilterChain
#from pyrox.stock_filters.simple import SimpleFilter


_LOG = get_logger(__name__)

_FTEST_CONFIG_KEY = 'keystone_meniscus_ftest'

args_parser = argparse.ArgumentParser(
    prog='proxy',
    description='Pyrox, the fast Python HTTP middleware server.')
args_parser.add_argument(
    '-d',
    nargs='?',
    dest='downstream_host',
    default='127.0.0.1:80',
    help='Sets the downstream host to proxy to.')
args_parser.add_argument(
    '-b',
    nargs='?',
    dest='bind_host',
    default='127.0.0.1:8080',
    help='Sets the host to bind to and listen on.')
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


def new_filter_chain():
    chain = HttpFilterChain()
    #chain.add_filter(SimpleFilter())
    #chain.add_filter(MeniscusKeystoneFilter())
    if len(chain.chain):
        _LOG.info('Loading the following filters: {}'.format(
            str(chain.chain).strip('[]')))
    return chain


def parse_args():
    return args_parser.parse_args()


def parse_host_arg(host):
    if ':' in host:
        split_host = host.split(':')
        return (split_host[0], int(split_host[1]))
    else:
        return (host, 80)


def start(args):
    downstream_addr = parse_host_arg(args.downstream_host)
    bind_addr = parse_host_arg(args.bind_host)

    _LOG.info('Pyrox listening on: http://{0}:{1}'.format(
        bind_addr[0], bind_addr[1]))
    _LOG.info('Pyrox downstream host: http://{0}:{1}'.format(
        downstream_addr[0], downstream_addr[1]))

    server.start(
        bind_address=bind_addr,
        downstream_host=downstream_addr,
        fc_factory=new_filter_chain,)


if len(sys.argv) > 1:
    args = parse_args()
    if args.start:
        start(args)
else:
    args_parser.print_help()
