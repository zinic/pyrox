from libc.stdlib cimport malloc, free

from cpython cimport bool, PyBytes_FromStringAndSize, PyBytes_FromString

cdef int on_req_method(http_parser *parser, char *data, size_t length):
    cdef object app_data = <object> parser.app_data
    cdef object method_str = PyBytes_FromStringAndSize(data, length)
    try:
        app_data.delegate.on_req_method(method_str)
    except Exception as ex:
        pass
    return 0

cdef int on_req_path(http_parser *parser, char *data, size_t length):
    cdef object app_data = <object> parser.app_data
    cdef object req_path_str = PyBytes_FromStringAndSize(data, length)
    try:
        app_data.delegate.on_req_path(req_path_str)
    except Exception as ex:
        pass
    return 0

cdef int on_req_http_version(http_parser *parser):
    cdef object app_data = <object> parser.app_data
    try:
        app_data.delegate.on_req_http_version(parser.http_major, parser.http_minor)
    except Exception as ex:
        pass
    return 0

cdef int on_header_field(http_parser *parser, char *data, size_t length):
    cdef object app_data = <object> parser.app_data
    cdef object header_field = PyBytes_FromStringAndSize(data, length)
    try:
        app_data.delegate.on_header_field(header_field)
    except Exception as ex:
        pass
    return 0

cdef int on_header_value(http_parser *parser, char *data, size_t length):
    cdef object app_data = <object> parser.app_data
    cdef object header_value = PyBytes_FromStringAndSize(data, length)
    try:
        app_data.delegate.on_header_value(header_value)
    except Exception as ex:
        pass
    return 0

cdef int on_headers_complete(http_parser *parser):
    cdef object app_data = <object> parser.app_data
    try:
        app_data.delegate.on_headers_complete()
    except Exception as ex:
        pass
    return 0

cdef int on_body(http_parser *parser, char *data, size_t length):
    cdef object app_data = <object> parser.app_data
    cdef object body_value = PyBytes_FromStringAndSize(data, length)
    try:
        app_data.delegate.on_body(body_value)
    except Exception as ex:
        pass
    return 0

cdef int on_message_complete(http_parser *parser):
    cdef object app_data = <object> parser.app_data
    try:
        app_data.delegate.on_message_complete()
    except Exception as ex:
        pass
    return 0


class ParserDelegate(object):

    def on_status(self, status_code):
        pass

    def on_req_method(self, method):
        pass

    def on_req_http_version(self, major, minor):
        pass

    def on_req_path(self, url):
        pass

    def on_header_field(self, field):
        pass

    def on_header_value(self, value):
        pass

    def on_headers_complete(self):
        pass

    def on_body(self, bytes):
        pass

    def on_message_complete(self):
        pass


cdef class ParserData(object):

    cdef public object delegate

    def __init__(self, delegate):
        self.delegate = delegate


cdef class HttpEventParser(object):

    cdef http_parser *_parser
    cdef http_parser_settings _settings
    cdef object app_data

    def __cinit__(self):
        self._parser = <http_parser *> malloc(sizeof(http_parser))

    def __init__(self, object delegate, kind=0):
        self.app_data = ParserData(delegate)

        # set parser type
        if kind == 0:
            parser_type = HTTP_REQUEST
        elif kind == 1:
            parser_type = HTTP_RESPONSE
        else:
            raise Exception('Kind must be 0 for requests or 1 for responses')

        # initialize parser
        self._parser.app_data = <void *>self.app_data
        http_parser_init(self._parser, parser_type)

        # set callbacks
        self._settings.on_message_begin = <http_cb>on_message_begin
        self._settings.on_req_method = <http_data_cb>on_req_method
        self._settings.on_req_path = <http_data_cb>on_req_path
        self._settings.on_req_http_version = <http_cb>on_req_http_version
        self._settings.on_body = <http_data_cb>on_body
        self._settings.on_header_field = <http_data_cb>on_header_field
        self._settings.on_header_value = <http_data_cb>on_header_value
        self._settings.on_headers_complete = <http_cb>on_headers_complete
        self._settings.on_message_complete = <http_cb>on_message_complete

    def __dealloc__(self):
        free_http_parser(self._parser)

    def execute(self, char *data, size_t length):
        cdef int retval = http_parser_exec(self._parser, &self._settings, data, length)
        if retval:
            raise Exception('Failed with errno: {}'.format(retval))
