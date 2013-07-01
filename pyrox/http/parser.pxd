cdef extern from "http_parser.h":

    cdef enum http_method:
        HTTP_DELETE, HTTP_GET, HTTP_HEAD, HTTP_POST, HTTP_PUT,
        HTTP_CONNECT, HTTP_OPTIONS, HTTP_TRACE, HTTP_COPY, HTTP_LOCK,
        HTTP_MKCOL, HTTP_MOVE, HTTP_PROPFIND, HTTP_PROPPATCH, HTTP_UNLOCK,
        HTTP_REPORT, HTTP_MKACTIVITY, HTTP_CHECKOUT, HTTP_MERGE,
        HTTP_MSEARCH, HTTP_NOTIFY, HTTP_SUBSCRIBE, HTTP_UNSUBSCRIBE,
        HTTP_PATCH, HTTP_PURGE

    cdef enum http_parser_type:
        HTTP_REQUEST, HTTP_RESPONSE, HTTP_BOTH

    cdef struct http_parser:
        int content_length
        unsigned short http_major
        unsigned short http_minor
        unsigned short status_code
        unsigned char method
        char upgrade
        void *data

    ctypedef int (*http_data_cb) (http_parser*, char *at, size_t length)
    ctypedef int (*http_cb) (http_parser*)

    struct http_parser_settings:
        http_cb on_message_begin
        http_data_cb on_url
        http_data_cb on_header_field
        http_data_cb on_header_value
        http_cb on_headers_complete
        http_data_cb on_body
        http_cb on_message_complete

    void http_parser_init(http_parser *parser, http_parser_type ptype)

    size_t http_parser_execute(http_parser *parser,
            http_parser_settings *settings, char *data,
            size_t len)

    int http_should_keep_alive(http_parser *parser)

    char *http_method_str(http_method)
