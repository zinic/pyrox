from libc.stdlib cimport *
from cpython cimport PyBytes_FromStringAndSize, PyBytes_FromString


cdef int on_url_cb(http_parser *parser, char *at, size_t length)  except -1:
    cdef object pystr = PyBytes_FromString(http_method_str(<http_method>parser.method))
    cdef object data = <object>parser.data
    try:
        data.delegate.on_req_method(pystr)
    except Exception:
        data.delegate.on_url(PyBytes_FromStringAndSize(at, length))
    return 0

cdef int on_header_field_cb(http_parser *parser, char *at, size_t length):
    cdef object header_name = PyBytes_FromStringAndSize(at, length)
    cdef object data = <object>parser.data
    data.header_name = header_name
    return 0

cdef int on_header_value_cb(http_parser *parser, char *at, size_t length) except -1:
    cdef object value = PyBytes_FromStringAndSize(at, length)
    cdef object data = <object>parser.data
    try:
        data.delegate.on_header(data.header_name, value)
    except Exception:
        return -1
    return 0

cdef int on_headers_complete_cb(http_parser *parser):
    return 0

cdef int on_message_begin_cb(http_parser *parser):
    return 0

cdef int on_body_cb(http_parser *parser, char *at, size_t length):
    return 0

cdef int on_message_complete_cb(http_parser *parser):
    return 0


class ParserData(object):

    def __init__(self, delegate):
        self.header_name = ''
        self.delegate =  delegate


cdef class HttpParser(object):
    """ Callback oriented low-level HTTP parser. """

    cdef http_parser _parser
    cdef http_parser_settings _settings

    cdef object parser_data

    def __init__(self, object filter_delegate, kind=2, decompress=False):
        """ constructor of HttpParser object.
        :
        attr kind: Int, could be 0 to parse only requests, 1 to parse only
        responses or 2 if we want to let the parser detect the type.
        """

        # set parser type
        if kind == 2:
            parser_type = HTTP_BOTH
        elif kind == 1:
            parser_type = HTTP_RESPONSE
        elif kind == 0:
            parser_type = HTTP_REQUEST

        # initialize parser
        http_parser_init(&self._parser, parser_type)
        self.parser_data = ParserData(filter_delegate)
        self._parser.data = <void *>self.parser_data

        # set callback
        self._settings.on_url = <http_data_cb>on_url_cb
        self._settings.on_body = <http_data_cb>on_body_cb
        self._settings.on_header_field = <http_data_cb>on_header_field_cb
        self._settings.on_header_value = <http_data_cb>on_header_value_cb
        self._settings.on_headers_complete = <http_cb>on_headers_complete_cb
        self._settings.on_message_begin = <http_cb>on_message_begin_cb
        self._settings.on_message_complete = <http_cb>on_message_complete_cb

    def execute(self, char *data, size_t length):
        """ Execute the parser with the last chunk. We pass the length
        to let the parser know when EOF has been received. In this case
        length == 0.

        :return recved: Int, received length of the data parsed. if
        recvd != length you should return an error.
        """
        return http_parser_execute(&self._parser, &self._settings,
                data, length)

