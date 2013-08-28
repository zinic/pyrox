import unittest
import time

from pyrox.http import RequestParser, ParserDelegate


NORMAL_REQUEST = """GET /test/12345?field=f1&field2=f2#fragment HTTP/1.1\r
Connection: keep-alive\r
Content-Length: 12\r\n
\r
This is test"""


def performance(duration=10, print_output=True):
    parser = RequestParser(ParserDelegate())

    runs = 0
    then = time.time()
    while time.time() - then < duration:
        parser.execute(NORMAL_REQUEST)
        runs += 1
    if print_output:
        print('Ran {} times in {} seconds for {} runs per second.'.format(
            runs,
            duration,
            runs / float(duration)))

if __name__ == '__main__':
    print('Executing warmup')
    performance(5, False)

    print('Executing performance test')
    performance(5)

    print('Profiling...')
    import cProfile
    cProfile.run('performance(5)')
