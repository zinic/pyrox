cdef extern from "http_el.h":

    cdef enum http_parser_type:
        HTTP_REQUEST, HTTP_RESPONSE

    cdef struct http_parser:
        unsigned long content_length
        void *app_data
        short http_major
        short http_minor
        short status_code

    ctypedef int (*http_data_cb) (http_parser*, char *at, size_t length) except -1
    ctypedef int (*http_cb) (http_parser*) except -1

    struct http_parser_settings:
        http_data_cb      on_req_method
        http_data_cb      on_req_path
        http_cb           on_http_version
        http_cb           on_status
        http_data_cb      on_header_field
        http_data_cb      on_header_value
        http_cb           on_headers_complete
        http_data_cb      on_body
        http_cb           on_message_complete

    void http_parser_init(http_parser *parser, http_parser_type ptype)
    void free_http_parser(http_parser *parser)

    int http_parser_exec(http_parser *parser, http_parser_settings *settings, char *data, size_t len) except -1
    int http_should_keep_alive(http_parser *parser)
    int http_transfer_encoding_chunked(http_parser *parser)
