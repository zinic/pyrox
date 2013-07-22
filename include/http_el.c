#include "http_el.h"
#include <assert.h>
#include <stddef.h>
#include <ctype.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

#ifndef ULLONG_MAX
#   define ULLONG_MAX ((uint64_t) -1) /* 2^64-1 */
#endif

#define PROXY_CONNECTION "proxy-connection"
#define CONNECTION "connection"
#define CONTENT_LENGTH "content-length"
#define TRANSFER_ENCODING "transfer-encoding"
#define UPGRADE "upgrade"
#define CHUNKED "chunked"
#define KEEP_ALIVE "keep-alive"
#define CLOSE "close"

#define T(v) v

// Lookup table for valid URL characters - I fudged this a bit
static const uint8_t normal_url_char[32] = {
/*   0 nul    1 soh    2 stx    3 etx    4 eot    5 enq    6 ack    7 bel  */
        0    |   0    |   0    |   0    |   0    |   0    |   0    |   0,
/*   8 bs     9 ht    10 nl    11 vt    12 np    13 cr    14 so    15 si   */
        0    | T(2)   |   0    |   0    | T(16)  |   0    |   0    |   0,
/*  16 dle   17 dc1   18 dc2   19 dc3   20 dc4   21 nak   22 syn   23 etb */
        0    |   0    |   0    |   0    |   0    |   0    |   0    |   0,
/*  24 can   25 em    26 sub   27 esc   28 fs    29 gs    30 rs    31 us  */
        0    |   0    |   0    |   0    |   0    |   0    |   0    |   0,
/*  32 sp    33  !    34  "    35  #    36  $    37  %    38  &    39  '  */
        0    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  40  (    41  )    42  *    43  +    44  ,    45  -    46  .    47  /  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  48  0    49  1    50  2    51  3    52  4    53  5    54  6    55  7  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  56  8    57  9    58  :    59  ;    60  <    61  =    62  >    63  ?  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  64  @    65  A    66  B    67  C    68  D    69  E    70  F    71  G  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  72  H    73  I    74  J    75  K    76  L    77  M    78  N    79  O  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  80  P    81  Q    82  R    83  S    84  T    85  U    86  V    87  W  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  88  X    89  Y    90  Z    91  [    92  \    93  ]    94  ^    95  _  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/*  96  `    97  a    98  b    99  c   100  d   101  e   102  f   103  g  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/* 104  h   105  i   106  j   107  k   108  l   109  m   110  n   111  o  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/* 112  p   113  q   114  r   115  s   116  t   117  u   118  v   119  w  */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |  128,
/* 120  x   121  y   122  z   123  {   124  |   125  }   126  ~   127 del */
        1    |   2    |   4    |   8    |   16   |   32   |   64   |   0, };


#ifndef BIT_AT
#   define BIT_AT(a, i)(!!((unsigned int) (a)[(unsigned int) (i) >> 3] & (1 << ((unsigned int) (i) & 7))))
#endif

#define CR                  '\r'
#define LF                  '\n'
#define SPACE               ' '

#define LOWER(c)            (unsigned char)(c | 0x20)
#define IS_ALPHA(c)         (LOWER(c) >= 'a' && LOWER(c) <= 'z')
#define IS_NUM(c)           ((c) >= '0' && (c) <= '9')
#define IS_ALPHANUM(c)      (IS_ALPHA(c) || IS_NUM(c))
#define IS_HEX(c)           (IS_NUM(c) || (LOWER(c) >= 'a' && LOWER(c) <= 'f'))

#define IS_MARK(c) ((c) == '-' || (c) == '_' || (c) == '.' || \
  (c) == '!' || (c) == '~' || (c) == '*' || (c) == '\'' || (c) == '(' || \
  (c) == ')')

#define IS_USERINFO_CHAR(c) (IS_ALPHANUM(c) || IS_MARK(c) || (c) == '%' || \
  (c) == ';' || (c) == ':' || (c) == '&' || (c) == '=' || (c) == '+' || \
  (c) == '$' || (c) == ',')

#define TOKEN(c) ((c == ' ') ? ' ' : tokens[(unsigned char)c])
#define IS_URL_CHAR(c) (BIT_AT(normal_url_char, (unsigned char)c) || ((c) & 0x80))
#define IS_HOST_CHAR(c) (IS_ALPHANUM(c) || (c) == '.' || (c) == '-' || (c) == '_')

enum http_el_state {
    // Request states
    s_req_start,
    s_req_method,
    s_req_path,
    s_req_http_version,

    // Reponse states
    s_resp_start
};

pbuffer * init_pbuffer(size_t size) {
    pbuffer *buffer = (pbuffer *) malloc(sizeof(pbuffer));
    buffer->bytes = (char *) malloc(sizeof(char) * size);
    buffer->position = 0;
    buffer->size = size;

    return buffer;
}

void reset_pbuffer(pbuffer *buffer) {
    buffer->position = 0;
}

void free_pbuffer(pbuffer *buffer) {
    if (buffer->bytes != NULL) {
        free(buffer->bytes);
        buffer->bytes = NULL;
    }

    free(buffer);
}

int store_byte_in_pbuffer(char byte, pbuffer *dest) {
    int errno = 0;

    if (dest-> position + 1 < dest->size) {
        dest->bytes[dest->position] = byte;
        dest->position += 1;
    } else {
        errno = ELERR_PBUFFER_OVERFLOW;
    }

    return errno;
}

int copy_into_pbuffer(const char *source, pbuffer *dest, size_t length) {
    int errno = 0;

    if (dest->position + length < dest->size) {
        memcpy(dest->bytes, source, length);
        dest->position += length;
    } else {
        errno = ELERR_PBUFFER_OVERFLOW;
    }

    return errno;
}

void reset_buffer(http_parser *parser) {
    reset_pbuffer(parser->buffer);
}

int store_byte(char byte, http_parser *parser) {
    return store_byte_in_pbuffer(byte, parser->buffer);
}

void on_data_cb(http_parser *parser, http_data_cb cb) {
    cb(parser, parser->buffer->bytes, parser->buffer->position);
}

int start_request(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int errno = 0;

    if (!IS_ALPHA(next_byte)) {
        errno = ELERR_BAD_METHOD;
    } else {
        errno = store_byte(next_byte, parser);

        // Move to the actual function for this
        parser->state = s_req_method;
    }

    return errno;
}

int read_request_method(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int errno = 0;

    if (next_byte == SPACE) {
        on_data_cb(parser, settings->on_req_method);
        reset_buffer(parser);

        // Read the URI next
        parser->state = s_req_path;
    } else if (IS_ALPHA(next_byte)) {
        errno = store_byte(next_byte, parser);
    } else {
        errno = ELERR_BAD_METHOD;
    }

    return errno;
}

int read_request_path(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int errno = 0;

    if (next_byte == SPACE) {
        on_data_cb(parser, settings->on_req_path);
        reset_buffer(parser);

        // Head right on over to the HTTP version next
        parser->state = s_req_http_version;
    } else if (IS_URL_CHAR(next_byte)) {
        errno = store_byte(next_byte, parser);
    } else {
        errno = ELERR_BAD_PATH_CHARACTER;
    }

    return errno;
}

int read_request_http_version(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int errno = 0;
    printf("ass %c\n", next_byte);
    if (next_byte == SPACE) {
        on_data_cb(parser, settings->on_req_path);
        reset_buffer(parser);

        parser->state = s_req_http_version;
    } else if (IS_URL_CHAR(next_byte)) {
        errno = store_byte(next_byte, parser);
    } else {
        errno = ELERR_BAD_PATH_CHARACTER;
    }

    return errno;
}

int request_parser_exec(http_parser *parser, const http_parser_settings *settings, const char *data, size_t len) {
    int errno = 0;
    int d_index;

    for (d_index = 0; d_index < len; d_index++) {
        char next_byte = data[d_index];

        switch (parser->state) {
            case s_req_start:
                errno = start_request(parser, settings, next_byte);
                break;

            case s_req_method:
                errno = read_request_method(parser, settings, next_byte);
                break;

            case s_req_path:
                errno = read_request_path(parser, settings, next_byte);
                break;

            case s_req_http_version:
                errno = read_request_http_version(parser, settings, next_byte);
                break;

            default:
                errno = ELERR_BAD_STATE;
        }

        // If errno evals to true then an error was set
        if (errno) {
            break;
        }
    }

    return errno;
}


int start_response(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    return 0;
}

int response_parser_exec(http_parser *parser, const http_parser_settings *settings, const char *data, size_t len) {
    int errno = 0;
    int d_index;

    for (d_index = 0; d_index < len; d_index++) {
        char next_byte = data[d_index];

        switch (parser->state) {
            case s_resp_start:
                errno = start_response(parser, settings, next_byte);
                break;

            default:
                errno = ELERR_BAD_STATE;
        }

        // If errno evals to true then an error was set
        if (errno) {
            break;
        }
    }

    return errno;
}

int http_parser_exec(http_parser *parser, const http_parser_settings *settings, const char *data, size_t len) {
    int errno = 0;

    switch (parser->type) {
        case HTTP_REQUEST:
            errno = request_parser_exec(parser, settings, data, len);
            break;
        case HTTP_RESPONSE:
            errno = response_parser_exec(parser, settings, data, len);
            break;
        default:
            errno = ELERR_BAD_PARSER_TYPE;
    }

    return errno;
}

void http_parser_init(http_parser *parser, enum http_parser_type parser_type) {
    // Preserve app_data ref
    void *app_data = parser->app_data;

    // Clear the parser memory space
    memset(parser, 0, sizeof(*parser));

    // Set up the struct elements
    parser->app_data = app_data;
    parser->type = parser_type;
    parser->state = parser_type == HTTP_REQUEST ? s_req_start : s_resp_start;
    parser->buffer = init_pbuffer(HTTP_MAX_HEADER_SIZE);
    parser->http_errno = 0;
}

void free_http_parser(http_parser *parser) {
    free_pbuffer(parser->buffer);
    free(parser);
}

int http_message_needs_eof(const http_parser *parser) {
    // If this is a request, then hell yes
    if (parser->type == HTTP_REQUEST) {
        return 0;
    }

    // See RFC 2616 section 4.4
    if (parser->status_code / 100 == 1 ||   // 1xx e.g. Continue
        parser->status_code == 204 ||       // No Content
        parser->status_code == 304 ||       // Not Modified
        parser->flags & F_SKIPBODY) {       // response to a HEAD request
        return 0;
    }

    if ((parser->flags & F_CHUNKED) || parser->content_length != ULLONG_MAX) {
        return 0;
    }

    return 1;
}

int http_should_keep_alive(const http_parser *parser) {
    if (parser->http_major > 0 && parser->http_minor > 0) {
        /* HTTP/1.1 */
        if (parser->flags & F_CONNECTION_CLOSE) {
            return 0;
        }
    } else {
        /* HTTP/1.0 or earlier */
        if (!(parser->flags & F_CONNECTION_KEEP_ALIVE)) {
            return 0;
        }
    }

    return !http_message_needs_eof(parser);
}

