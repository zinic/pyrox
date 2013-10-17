from tornado import (
    httpserver,
    ioloop,
    options,
    web,
)
from tornado.options import options as options_data
import time

from chunked_handler import ChunkedHandler
#import naive

class SampleChunkedHandler(ChunkedHandler):
    @web.asynchronous
    def post(self):

        #time.sleep(10)

        print("POST received...")

        if not self._handle_chunked():
            raise web.HTTPError(500, "non-chunked request")

    def _on_chunks(self, all_chunks):
        super(SampleChunkedHandler, self)._on_chunks(all_chunks)

        print "got all chunks, total size=%d" % all_chunks.tell()


if __name__ == '__main__':
    options.define("port", default=8000, help="run on the given port", type=int)
    options.parse_command_line()

    application = web.Application([
        # ('/chunked_naive$', naive.ChunkedHandler, ),
        ('/chunked$', SampleChunkedHandler, ),
    ])

    http_server = httpserver.HTTPServer(application)
    http_server.listen(options_data.port)

    print('Starting up server...')
    ioloop.IOLoop.instance().start()
