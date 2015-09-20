import os

import pyrox.filtering as filtering

from pyrox.http import HttpResponse
from pyrox.about import VERSION


_VERSION_STR = 'pyrox/{}'.format(VERSION)

_NOT_FOUND = HttpResponse()
_NOT_FOUND.version = b'1.1'
_NOT_FOUND.status = '404 Not Found'
_NOT_FOUND.header('Server').values.append(_VERSION_STR)


class WebServer(filtering.HttpFilter):

    def __init__(self, root):
        self._root = root

    @filtering.handles_request_head
    def on_request_head(self, req):
        url = str(req.url)
        frag_split = url.split('#', 2)
        query_split = frag_split[0].split('?', 2)

        path = query_split[0]
        if path.startswith('/'):
            path = path[1:]

        frag = frag_split[1] if len(frag_split) > 1 else ''
        query = query_split[1] if len(query_split) > 1 else ''

        target_path = os.path.join(self._root, path)
        if os.path.isdir(target_path):
            target_path = os.path.join(target_path, 'index.html')

        if not os.path.exists(target_path):
            return filtering.reply(_NOT_FOUND)

        resp = HttpResponse()
        resp.version = b'1.1'
        resp.status = '200 OK'
        resp.header('Server').values.append('pyrox/{}'.format(VERSION))

        fin = open(target_path, 'r')
        return filtering.reply(resp, fin)
