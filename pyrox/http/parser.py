import os
from cffi import FFI

_REQUEST_PARSER = 0
_RESPONSE_PARSER = 1

ffi = FFI()
ffi.cdef("""
// Type defs
typedef struct pbuffer pbuffer;
typedef struct http_parser http_parser;
typedef struct http_parser_settings http_parser_settings;

typedef int (*http_data_cb) (http_parser*, const char *at, size_t length);
typedef int (*http_cb) (http_parser*);


// Enumerations
enum http_parser_type {
    HTTP_REQUEST,
    HTTP_RESPONSE
};

enum HTTP_EL_ERROR {
    ELERR_UNCAUGHT = 1,
    ELERR_BAD_PARSER_TYPE = 2,
    ELERR_BAD_STATE = 3,
    ELERR_BAD_PATH_CHARACTER = 4,
    ELERR_BAD_HTTP_VERSION_HEAD = 5,
    ELERR_BAD_HTTP_VERSION_MAJOR = 6,
    ELERR_BAD_HTTP_VERSION_MINOR = 7,
    ELERR_BAD_HEADER_TOKEN = 8,
    ELERR_BAD_CONTENT_LENGTH = 9,
    ELERR_BAD_CHUNK_SIZE = 10,
    ELERR_BAD_DATA_AFTER_CHUNK = 11,
    ELERR_BAD_STATUS_CODE = 12,

    ELERR_BAD_METHOD = 100,

    ELERR_PBUFFER_OVERFLOW = 1000
};


// Structs
struct pbuffer {
    char *bytes;
    size_t position;
    size_t size;
};

struct http_parser_settings {
    http_cb           on_message_begin;
    http_data_cb      on_req_method;
    http_data_cb      on_req_path;
    http_cb           on_http_version;
    http_cb           on_status;
    http_data_cb      on_header_field;
    http_data_cb      on_header_value;
    http_cb           on_headers_complete;
    http_data_cb      on_body;
    http_cb           on_message_complete;
};

struct http_parser {
    // Parser fields
    unsigned char flags : 5;
    unsigned char state;
    unsigned char header_state;
    unsigned char type;
    unsigned char index;

    // Reserved fields
    unsigned long content_length;
    size_t bytes_read;

    // HTTP version info
    unsigned short http_major;
    unsigned short http_minor;

    // Request specific
    // Reponse specific
    unsigned short status_code;

    // Buffer
    pbuffer *buffer;

    // Optionally settable application data pointer
    void *app_data;
};


// Functions
void http_parser_init(http_parser *parser, enum http_parser_type parser_type);
void free_http_parser(http_parser *parser);

int http_parser_exec(http_parser *parser,
    const http_parser_settings *settings, const char *data, size_t len);
int http_should_keep_alive(const http_parser *parser);
int http_transfer_encoding_chunked(const http_parser *parser);
""")

lib = ffi.verify(
    """
    #include "http_el.h"
    #include "http_el.c"
    """,
    include_dirs=['./include'])


def RequestParser(parser_delegate):
    return HttpEventParser(parser_delegate, _REQUEST_PARSER)


def ResponseParser(parser_delegate):
    return HttpEventParser(parser_delegate, _RESPONSE_PARSER)


@ffi.callback("int (http_parser *parser, const char *at, size_t len)")
def on_req_method(parser, at, length):
    app_data = ffi.from_handle(parser.app_data)
    method_str = ffi.string(at, length)
    app_data.delegate.on_req_method(method_str)
    return 0


@ffi.callback("int (http_parser *parser, const char *at, size_t len)")
def on_req_path(parser, at, length):
    app_data = ffi.from_handle(parser.app_data)
    req_path_str = ffi.string(at, length)
    app_data.delegate.on_req_path(req_path_str)
    return 0


@ffi.callback("int (http_parser *parser)")
def on_status(parser):
    app_data = ffi.from_handle(parser.app_data)
    app_data.delegate.on_status(parser.status_code)
    return 0


@ffi.callback("int (http_parser *parser)", error=-1)
def on_http_version(parser):
    app_data = ffi.from_handle(parser.app_data)
    app_data.delegate.on_http_version(parser.http_major, parser.http_minor)
    return 0


@ffi.callback("int (http_parser *parser, const char *at, size_t len)")
def on_header_field(parser, at, length):
    app_data = ffi.from_handle(parser.app_data)
    header_field = ffi.string(at, length)
    app_data.delegate.on_header_field(header_field)
    return 0


@ffi.callback("int (http_parser *parser, const char *at, size_t len)")
def on_header_value(parser, at, length):
    app_data = ffi.from_handle(parser.app_data)
    header_value = ffi.string(at, length)
    app_data.delegate.on_header_value(header_value)
    return 0


@ffi.callback("int (http_parser *parser)")
def on_headers_complete(parser):
    app_data = ffi.from_handle(parser.app_data)
    app_data.delegate.on_headers_complete()
    return 0


@ffi.callback("int (http_parser *parser, const char *at, size_t len)")
def on_body(parser, at, length):
    app_data = ffi.from_handle(parser.app_data)
    body_value = ffi.string(at, length)
    app_data.delegate.on_body(
        body_value,
        length,
        lib.http_transfer_encoding_chunked(parser))
    return 0


@ffi.callback("int (http_parser *parser)")
def on_message_complete(parser):
    app_data = ffi.from_handle(parser.app_data)
    app_data.delegate.on_message_complete(
        lib.http_transfer_encoding_chunked(parser),
        lib.http_should_keep_alive(parser))
    return 0


class ParserDelegate(object):

    def on_status(self, status_code):
        pass

    def on_req_method(self, method):
        pass

    def on_http_version(self, major, minor):
        pass

    def on_req_path(self, url):
        pass

    def on_header_field(self, field):
        pass

    def on_header_value(self, value):
        pass

    def on_headers_complete(self):
        pass

    def on_body(self, bytes, length, is_chunked):
        pass

    def on_message_complete(self, is_chunked, should_keep_alive):
        pass


class ParserData(object):

    def __init__(self, delegate):
        self.delegate = delegate


class HttpEventParser(object):

    def __init__(self, delegate, kind=-1):
        # set parser type
        if kind == _REQUEST_PARSER:
            parser_type = lib.HTTP_REQUEST
        elif kind == _RESPONSE_PARSER:
            parser_type = lib.HTTP_RESPONSE
        else:
            raise Exception('Kind must be 0 for requests or 1 for responses')

        # initialize parser
        self._parser = ffi.new('http_parser *')
        lib.http_parser_init(self._parser, parser_type)

        self.app_data = ParserData(delegate)
        self._parser.app_data = ffi.new_handle(self.app_data)

        # set callbacks
        self._settings = ffi.new('http_parser_settings *')
        self._settings.on_req_method = on_req_method
        self._settings.on_req_path = on_req_path
        self._settings.on_http_version = on_http_version
        self._settings.on_status = on_status
        self._settings.on_header_field = on_header_field
        self._settings.on_header_value = on_header_value
        self._settings.on_headers_complete = on_headers_complete
        self._settings.on_body = on_body
        self._settings.on_message_complete = on_message_complete

    def destroy(self):
        if self._parser is None:
            lib.free_http_parser(self._parser)
            self._parser = None

    def execute(self, data):
        try:
            if self._parser is None:
                raise Exception('Parser destroyed or not initialized!')
            retval = lib.http_parser_exec(
                self._parser, self._settings, data, len(data))
            if retval:
                raise Exception('Failed with errno: {}'.format(retval))
        except Exception as ex:
            raise
