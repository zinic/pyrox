import pyrox.filtering as filtering

from pyrox.http import HttpResponse
from pyrox.about import VERSION


class WebServer(filtering.HttpFilter):

    @filtering.handles_request_head
    def on_request_head(self, req):
        resp = HttpResponse()
        resp.version = b'1.1'
        resp.status = '200 OK'
        resp.header('Server').values.append('pyrox/{}'.format(VERSION))
        resp.header('Content-Length').values.append('0')

        for name, header in req.headers.items():
            print('Got header {}:{}'.format(name, header.values))

        return filtering.reply(resp,
"""
<html>
    <head>
    </head>
    
    <body>
        <h1>Hello World</h1>
    </body>
</html>
""")
