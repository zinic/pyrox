#ifndef http_parser_h
#define http_parser_h

#ifdef __cplusplus
extern "C" {
#endif

#define HTTP_MAX_HEADER_SIZE (80*1024)

typedef struct parser_buffer parser_buffer;
typedef struct http_parser http_parser;
typedef struct http_parser_settings http_parser_settings;

typedef int (*http_data_cb) (http_parser*, const char *at, size_t length);
typedef int (*http_cb) (http_parser*);


enum flags {
    F_CHUNKED               = 1 << 0,
    F_CONNECTION_KEEP_ALIVE = 1 << 1,
    F_CONNECTION_CLOSE      = 1 << 2
};


struct parser_buffer {
    char *buffer
    size_t current_size
};


struct http_parser {
    unsigned char flags : 4;
    parser_buffer buffer;

};

#ifdef __cplusplus
}
#endif
