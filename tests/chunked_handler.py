
from tornado import web, httpclient, httputil

from iostream_callback import (
    Callback,
    Data,
    DONE,
)
import time

from cStringIO import StringIO

WAIT_LENGTH = (1, )
WAIT_CHUNK = (2, )


class ChunkedData(Data):

    def __init__(self):
        self.chunk = StringIO()
        self.chunk_length = 0

        super(ChunkedData, self).__init__()


# class ProxyChunkedData(Data):
#
# def __init__(self):
# h = httputil.HTTPHeaders({"Transfer-Encoding": "chunked"})
# h.add("Expect", "100-continue")
# req = httpclient.HTTPRequest(
# url='http://localhost:8080/chunked',
# method="POST",
# headers=h,
# streaming_callback=self.streaming_callback)
# http_client = httpclient.AsyncHTTPClient()
# http_client.fetch(req, self.async_callback)
#
# self.chunk_length = 0
#
# super(ProxyChunkedData, self).__init__()
#
# def handle_response(response):
# if response.error and not isinstance(response.error,
# tornado.httpclient.HTTPError):
# self.set_status(500)
# self.write('Internal server error:\n' + str(response.error))
# self.finish()
# else:
# self.set_status(response.code)
# for header in ('Date', 'Cache-Control', 'Server',
# 'Content-Type', 'Location'):
# v = response.headers.get(header)
# if v:
# self.set_header(header, v)
# if response.body:
# self.write(response.body)
# self.finish()


class LengthCallback(Callback):
    start_state = WAIT_LENGTH

    def _handle(self, data):
        print('length::_handle()...length-data="{0}"'.format(data))

        assert data[-2:] == '\r\n', "chunk size ends with CRLF"
        self.data.chunk_length = int(data[:-2], 16)
        print('...length={0}'.format(self.data.chunk_length))

        if self.data.chunk_length:
            self.data.state = WAIT_CHUNK
        else:
            self.data.state = DONE


class DataCallback(Callback):
    start_state = WAIT_CHUNK

    def _handle(self, data):
        print('ddddddddddddddata::_handle()...data')

        # time.sleep(10)

        assert data[-2:] == '\r\n', "chunk data ends with CRLF"
        self.data.chunk.write(data[:-2])

        # time_curr = time.time()
        # while True:
        # delta = time.time() - time_curr
        # if delta > 10:
        # break
        # print('...wwwwwriting:{0}'.format(data[:-2]))

        self.data.state = WAIT_LENGTH


class ChunkReader(object):
    def __init__(self, handler):
        self.handler = handler

        stream = handler.request.connection.stream

        data = ChunkedData()
        print('Chunk reader - init: data')
        func = Callback.make_entry_callback(data, (
                LengthCallback(data,
                    lambda self: stream.read_until('\r\n', self)),
                DataCallback(data,
                    lambda self: stream.read_bytes(data.chunk_length + 2, self)),
            ), self._done_callback)

        data.state = WAIT_LENGTH
        func()

    def _done_callback(self, data):
        self.handler._on_chunks(data.chunk)


class ChunkedHandler(web.RequestHandler):
    def _handle_chunked(self, *args, **kwargs):
        # we assume that the wrapping server has not sent/flushed the
        # 100 (Continue) response
        print('_handle_chunked()...{0}'.format(self.request.headers))
        if self.request.headers.get('Transfer-Encoding', None) == 'chunked':
        #if self.request.headers.get('Expect', None) == '100-continue' and \
        # self.request.headers.get('Transfer-Encoding', None) == 'chunked':

        #TODO(jwood) Why is Content-Length coming over from Tornado, even though chunked xfer???
        # if self.request.headers.get('Expect', None) == '100-continue' and \
        # not 'Content-Length' in self.request.headers and \
        # self.request.headers.get('Transfer-Encoding', None) == 'chunked':

            print('...got chunked...')

            self._auto_finish = False
            ChunkReader(self)

            self.request.write("HTTP/1.1 100 (Continue)\r\n\r\n")

            return True
        return False

    def _on_chunks(self, all_chunks):
        print('finish()')

        #TODO(jwood) Dump to file...yeah, this isn't production stuff here.
        f = open('final_output.dat', 'wb')
        f.write(all_chunks.getvalue())

        self.finish()
