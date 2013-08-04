import sys
import argparse

import pyrox.server as server

from pyrox.http.filtering import HttpFilterChain
from pyrox.stock_filters.simple import SimpleFilter
from pyrox.stock_filters.keystone_meniscus import MeniscusKeystoneFilter

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
    'start',
    default=False,
    help='Starts the daemon.')


def new_filter_chain():
    chain = HttpFilterChain()
    chain.add_filter(SimpleFilter())
    return chain


def parse_host_arg(host):
    if ':' in host:
        split_host = host.split(':')
        return (split_host[0], int(split_host[1]))
    else:
        return (host, 80)


def start(args):
    downstream_addr = parse_host_arg(args.downstream_host)
    bind_addr = parse_host_arg(args.bind_host)

    server.start(
        bind_address=bind_addr,
        downstream_host=downstream_addr,
        fc_factory=new_filter_chain,)


if len(sys.argv) > 1:
    args = args_parser.parse_args()
    if args.start:
        start(args)
else:
    args_parser.print_help()

