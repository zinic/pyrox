#ifndef http_parser_h
#define http_parser_h

#ifdef __cplusplus
extern "C" {
#endif

#include <sys/types.h>
#include <stdint.h>

#define HTTP_EL_VERSION_MAJOR 0
#define HTTP_EL_VERSION_MINOR 1

#define HTTP_MAX_HEADER_SIZE (80 * 1024)


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

enum flags {
    F_CHUNKED               = 1 << 0,
    F_CONNECTION_KEEP_ALIVE = 1 << 1,
    F_CONNECTION_CLOSE      = 1 << 2,
    F_SKIPBODY              = 1 << 3,
    F_TRAILING              = 1 << 4
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

int http_parser_exec(http_parser *parser, const http_parser_settings *settings, const char *data, size_t len);
int http_should_keep_alive(const http_parser *parser);
int http_transfer_encoding_chunked(const http_parser *parser);

#ifdef __cplusplus
}
#endif
#endif
