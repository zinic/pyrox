#include "http_el.h"
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

#ifndef ULLONG_MAX
#   define ULLONG_MAX ((uint64_t) -1)   // 2^64-1
#endif

#ifndef USHORT_MAX
#   define USHORT_MAX ((uint16_t) -1)   // 2^16-1
#endif

#define PROXY_CONNECTION "proxy-connection"
#define CON "con"
#define CONNECTION "connection"
#define CONTENT_LENGTH "content-length"
#define TRANSFER_ENCODING "transfer-encoding"
#define UPGRADE "upgrade"
#define CHUNKED "chunked"
#define KEEP_ALIVE "keep-alive"
#define CLOSE "close"

#define T(v) v



/* Tokens as defined by rfc 2616. Also lowercases them.
 *        token       = 1*<any CHAR except CTLs or separators>
 *     separators     = "(" | ")" | "<" | ">" | "@"
 *                    | "," | ";" | ":" | "\" | <">
 *                    | "/" | "[" | "]" | "?" | "="
 *                    | "{" | "}" | SP | HT
 */
static const char tokens[256] = {
/*   0 nul    1 soh    2 stx    3 etx    4 eot    5 enq    6 ack    7 bel  */
        0,       0,       0,       0,       0,       0,       0,       0,
/*   8 bs     9 ht    10 nl    11 vt    12 np    13 cr    14 so    15 si   */
        0,       0,       0,       0,       0,       0,       0,       0,
/*  16 dle   17 dc1   18 dc2   19 dc3   20 dc4   21 nak   22 syn   23 etb */
        0,       0,       0,       0,       0,       0,       0,       0,
/*  24 can   25 em    26 sub   27 esc   28 fs    29 gs    30 rs    31 us  */
        0,       0,       0,       0,       0,       0,       0,       0,
/*  32 sp    33  !    34  "    35  #    36  $    37  %    38  &    39  '  */
        0,      '!',      0,      '#',     '$',     '%',     '&',    '\'',
/*  40  (    41  )    42  *    43  +    44  ,    45  -    46  .    47  /  */
        0,       0,      '*',     '+',      0,      '-',     '.',      0,
/*  48  0    49  1    50  2    51  3    52  4    53  5    54  6    55  7  */
       '0',     '1',     '2',     '3',     '4',     '5',     '6',     '7',
/*  56  8    57  9    58  :    59  ;    60  <    61  =    62  >    63  ?  */
       '8',     '9',      0,       0,       0,       0,       0,       0,
/*  64  @    65  A    66  B    67  C    68  D    69  E    70  F    71  G  */
        0,      'a',     'b',     'c',     'd',     'e',     'f',     'g',
/*  72  H    73  I    74  J    75  K    76  L    77  M    78  N    79  O  */
       'h',     'i',     'j',     'k',     'l',     'm',     'n',     'o',
/*  80  P    81  Q    82  R    83  S    84  T    85  U    86  V    87  W  */
       'p',     'q',     'r',     's',     't',     'u',     'v',     'w',
/*  88  X    89  Y    90  Z    91  [    92  \    93  ]    94  ^    95  _  */
       'x',     'y',     'z',      0,       0,       0,      '^',     '_',
/*  96  `    97  a    98  b    99  c   100  d   101  e   102  f   103  g  */
       '`',     'a',     'b',     'c',     'd',     'e',     'f',     'g',
/* 104  h   105  i   106  j   107  k   108  l   109  m   110  n   111  o  */
       'h',     'i',     'j',     'k',     'l',     'm',     'n',     'o',
/* 112  p   113  q   114  r   115  s   116  t   117  u   118  v   119  w  */
       'p',     'q',     'r',     's',     't',     'u',     'v',     'w',
/* 120  x   121  y   122  z   123  {   124  |   125  }   126  ~   127 del */
       'x',     'y',     'z',      0,      '|',      0,      '~',       0};


static const int8_t unhex[256] = {
     -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
    ,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
    ,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
    , 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,-1,-1,-1,-1,-1,-1
    ,-1,10,11,12,13,14,15,-1,-1,-1,-1,-1,-1,-1,-1,-1
    ,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
    ,-1,10,11,12,13,14,15,-1,-1,-1,-1,-1,-1,-1,-1,-1
    ,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
};

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
        1    |   2    |   4    |   8    |   16   |   32   |   64   |   0};


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


// States

typedef enum {
    // Request states
    s_req_start,
    s_req_method,
    s_req_path,

    // Common states
    s_http_version_head,
    s_http_version_major,
    s_http_version_minor,

    s_header_field_start,
    s_header_field,
    s_header_value,

    s_body,
    s_chunk_size,
    s_chunk_parameters,
    s_chunk_data,
    s_chunk_complete,
    s_body_complete,
    s_message_end,

    // Reponse states
    s_resp_start,
    s_resp_status,
    s_resp_rphrase
} http_el_state;

typedef enum {
    // Header states
    h_general,
    h_content_length,
    h_connection,
    h_connection_keep_alive,
    h_connection_close,
    h_transfer_encoding,
    h_transfer_encoding_chunked,

    // Matching states
    h_matching_transfer_encoding,
    h_matching_transfer_encoding_chunked,
    h_matching_con,
    h_matching_content_length,
    h_matching_connection,
    h_matching_connection_keep_alive,
    h_matching_connection_close
} header_state;



// Supporting functions

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
    int retval = 0;

    if (dest-> position + 1 < dest->size) {
        dest->bytes[dest->position] = byte;
        dest->position += 1;
    } else {
        retval = ELERR_PBUFFER_OVERFLOW;
    }

    return retval;
}

int copy_into_pbuffer(const char *source, pbuffer *dest, size_t length) {
    int retval = 0;

    if (dest->position + length < dest->size) {
        memcpy(dest->bytes, source, length);
        dest->position += length;
    } else {
        retval = ELERR_PBUFFER_OVERFLOW;
    }

    return retval;
}

void reset_buffer(http_parser *parser) {
    parser->bytes_read = 0;
    parser->index = 0;

    reset_pbuffer(parser->buffer);
}

int store_byte(char byte, http_parser *parser) {
    parser->bytes_read += 1;
    return store_byte_in_pbuffer(byte, parser->buffer);
}

int on_cb(http_parser *parser, http_cb cb) {
    return cb(parser);
}

int on_data_cb(http_parser *parser, http_data_cb cb) {
    return cb(parser, parser->buffer->bytes, parser->buffer->position);
}

#if DEBUG_OUTPUT
char * http_el_state_name(http_el_state state) {
    switch (state) {
        case s_req_start:
            return "request start";
        case s_req_method:
            return "request method";
        case s_req_path:
            return "request path";
        case s_http_version_head:
            return "http version head";
        case s_http_version_major:
            return "http version major";
        case s_http_version_minor:
            return "http version minor";
        case s_header_field_start:
            return "header field start";
        case s_header_field:
            return "header field";
        case s_header_value:
            return "header value";
        case s_body:
            return "request body";
        case s_chunk_size:
            return "chunk size";
        case s_chunk_parameters:
            return "chunk parameters";
        case s_chunk_data:
            return "chunk data";
        case s_body_complete:
            return "body complete";
        case s_chunk_complete:
            return "chunk complete";
        case s_resp_start:
            return "response start";
        case s_resp_status:
            return "response status code";
        case s_resp_rphrase:
            return "response reason phrase";

        default:
            return "ERROR - NOT A STATE";
    }
}

char * http_header_state_name(header_state state) {
    switch (state) {
        case h_general:
            return "general header";
        case h_content_length:
            return "header type content length";
        case h_connection:
            return "header type connection";
        case h_connection_keep_alive:
            return "header type connection keep alive";
        case h_connection_close:
            return "header type connection close";
        case h_transfer_encoding:
            return "header type transfer encoding";
        case h_transfer_encoding_chunked:
            return "header type transfer encoding chunked";
        case h_matching_transfer_encoding:
            return "matching header transfer encoding";
        case h_matching_transfer_encoding_chunked:
            return "matching header transfer encoding chunked";
        case h_matching_con:
            return "matching header con";
        case h_matching_content_length:
            return "matching header content length";
        case h_matching_connection:
            return "matching header connection";
        case h_matching_connection_keep_alive:
            return "matching header connection keep alive";
        case h_matching_connection_close:
            return "matching header connection close";

        default:
            return "ERROR - NOT A STATE";
    }
}
#endif

void set_http_state(http_parser *parser, http_el_state state) {
#if DEBUG_OUTPUT
    printf("%s state changed --> %s\n",
        parser->type == HTTP_REQUEST ? "Request" : "Response",
        http_el_state_name(state));
#endif
    parser->state = state;
}

void set_header_state(http_parser *parser, header_state state) {
#if DEBUG_OUTPUT
    printf("%s header state changed --> %s\n",
        parser->type == HTTP_REQUEST ? "Request" : "Response",
        http_header_state_name(state));
#endif
    parser->header_state = state;
}


void reset_http_parser(http_parser *parser) {
    parser->bytes_read = 0;
    parser->status_code = 0;
    parser->flags = 0;
    parser->content_length = 0;
    parser->http_major = 0;
    parser->http_minor = 0;

    reset_buffer(parser);
    set_header_state(parser, h_general);
    set_http_state(parser,
        parser->type == HTTP_REQUEST ? s_req_start : s_resp_start);
}

int read_body(http_parser *parser, const http_parser_settings *settings, const char *data, size_t offset, size_t length) {
    int retval = 0, real_length = length - offset;
    size_t read = 0;

    if (parser->content_length >= real_length) {
        retval = settings->on_body(parser, data + offset, real_length);
        read = real_length;
    } else {
        retval = settings->on_body(parser, data + offset, parser->content_length);
        read = parser->content_length;
    }

    parser->content_length -= read;
    parser->bytes_read += read;

    if (parser->content_length == 0) {
        switch(parser->state) {
            case s_chunk_data:
                set_http_state(parser, s_chunk_complete);
                break;

            default:
                set_http_state(parser, s_body_complete);
        }
    }

    return retval;
}

int read_chunk_complete(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    switch (next_byte) {
        case CR:
            break;

        case LF:
            set_http_state(parser, s_chunk_size);
            break;

        default:
            retval = ELERR_BAD_DATA_AFTER_CHUNK;
    }

    return retval;
}

int read_chunk_parameters(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    switch (next_byte) {
        case CR:
            break;

        case LF:
            if (parser->content_length == 0) {
                // TODO:Feature - Implement trailing headers
                //parser->flags |= F_TRAILING;
                set_http_state(parser, s_body_complete);
            } else {
                set_http_state(parser, s_chunk_data);
            }
    }

    return retval;
}

int read_chunk_size(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;
    unsigned char unhex_val;
    unsigned long t;

    switch (next_byte) {
        case CR:
            break;

        case LF:
            if (parser->content_length == 0) {
                // TODO:Feature - Implement trailing headers
                //parser->flags |= F_TRAILING;
                set_http_state(parser, s_body_complete);
            } else {
                set_http_state(parser, s_chunk_data);
            }
            break;

        case ';':
        case ' ':
            set_http_state(parser, s_chunk_parameters);
            break;

        default:
            unhex_val = unhex[(unsigned char)next_byte];

            if (unhex_val == -1) {
                retval = ELERR_BAD_CHUNK_SIZE;
            } else {
                t = parser->content_length;
                t *= 16;
                t += unhex_val;

                // Overflow?
                if (t < parser->content_length || t == ULLONG_MAX) {
                    retval = ELERR_BAD_CONTENT_LENGTH;
                } else {
                    parser->content_length = t;
                }
            }
    }

    return retval;
}

int read_chunk_start(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;
    unsigned char unhex_val = unhex[(unsigned char)next_byte];

    if (unhex_val == -1) {
        retval = ELERR_BAD_CHUNK_SIZE;
    } else {
        set_http_state(parser, s_chunk_size);
        retval = read_chunk_size(parser, settings, next_byte);
    }

    return retval;
}

int process_header_by_state(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;
    unsigned long t;
    char lower = LOWER(next_byte);

    switch (parser->header_state) {
        case h_transfer_encoding:
            if (lower == 'c') {
                set_header_state(parser, h_matching_transfer_encoding_chunked);
            } else {
                set_header_state(parser, h_general);
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_connection:
            if (lower == 'k') {
                set_header_state(parser, h_matching_connection_keep_alive);
            } else {
                set_header_state(parser, h_general);
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_matching_transfer_encoding_chunked:
            parser->index += 1;
            if (parser->index > sizeof(CHUNKED) - 1 || lower != CHUNKED[parser->index]) {
                set_header_state(parser, h_general);
            } else if (parser->index == sizeof(CHUNKED) - 2) {
                parser->flags |= F_CHUNKED;
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_matching_connection_keep_alive:
            parser->index += 1;
            if (parser->index > sizeof(KEEP_ALIVE) - 1 || lower != KEEP_ALIVE[parser->index]) {
                set_header_state(parser, h_general);
            } else if (parser->index == sizeof(KEEP_ALIVE) - 2) {
                parser->flags |= F_CONNECTION_KEEP_ALIVE;
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_content_length:
            // TODO(Complexity): refactor into function
            if (!IS_NUM(next_byte)) {
                retval = ELERR_BAD_CONTENT_LENGTH;
            } else {
                t = parser->content_length;
                t *= 10;
                t += next_byte - '0';

                /* Overflow? */
                if (t < parser->content_length || t == ULLONG_MAX) {
                    retval = ELERR_BAD_CONTENT_LENGTH;
                } else {
                    parser->content_length = t;
                    retval = store_byte(next_byte, parser);
                }
            }
            break;

        case h_general:
        default:
            retval = store_byte(next_byte, parser);
    }

    return retval;
}

int read_header_value(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    switch (next_byte) {
        case CR:
            break;

        case LF:
            retval = on_data_cb(parser, settings->on_header_value);
            reset_buffer(parser);
            set_http_state(parser, s_header_field_start);
            set_header_state(parser, h_general);
            break;

        case '\t':
        case ' ':
            // Skip leading whitespace
            if (parser->bytes_read == 0) {
                break;
            }

        default:
            retval = process_header_by_state(parser, settings, next_byte);
    }

    return retval;
}

int read_header_field_by_state(http_parser *parser, const http_parser_settings *settings, char next_byte, char lower) {
    int retval = 0;
    char token;

    switch (parser->header_state) {
        case h_matching_transfer_encoding:
            parser->index += 1;
            if (parser->index > sizeof(TRANSFER_ENCODING) - 1 || lower != TRANSFER_ENCODING[parser->index]) {
                set_header_state(parser, h_general);
            } else if (parser->index == sizeof(TRANSFER_ENCODING) - 2) {
                set_header_state(parser, h_transfer_encoding);
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_matching_con:
            parser->index += 1;
            if (parser->index < sizeof(CON) - 1 && lower != CON[parser->index]) {
                set_header_state(parser, h_general);
            } else if (parser->index == sizeof(CON) - 1) {
                switch (lower) {
                    case 't':
                        set_header_state(parser, h_matching_content_length);
                        break;

                    case 'n':
                        set_header_state(parser, h_matching_connection);
                        break;

                    default:
                        set_header_state(parser, h_general);
                }
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_matching_content_length:
            parser->index += 1;
            if (parser->index > sizeof(CONTENT_LENGTH) - 1 || lower != CONTENT_LENGTH[parser->index]) {
                set_header_state(parser, h_general);
            } else if (parser->index == sizeof(CONTENT_LENGTH) - 2) {
                set_header_state(parser, h_content_length);
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_matching_connection:
            parser->index += 1;
            if (parser->index > sizeof(CONNECTION) - 1 || lower != CONNECTION[parser->index]) {
                set_header_state(parser, h_general);
            } else if (parser->index == sizeof(CONNECTION) - 2) {
                set_header_state(parser, h_connection);
            }

            retval = store_byte(next_byte, parser);
            break;

        case h_general:
        default:
            token = TOKEN(next_byte);

            if (!token) {
                retval = ELERR_BAD_HEADER_TOKEN;
            } else {
                retval = store_byte(next_byte, parser);
            }
    }

    return retval;
}

int read_header_field(http_parser *parser, const http_parser_settings *settings, char next_byte, char lower) {
    int retval = 0;

    switch (next_byte) {
        case CR:
            break;

        case LF:
            retval = on_cb(parser, settings->on_headers_complete);

            if (parser->flags & F_CHUNKED) {
                set_http_state(parser, s_chunk_size);
            } else if (parser->content_length > 0) {
                set_http_state(parser, s_body);
            } else {
                set_http_state(parser, s_body_complete);
            }
            break;

        case ':':
            retval = on_data_cb(parser, settings->on_header_field);
            reset_buffer(parser);
            set_http_state(parser, s_header_value);
            break;

        default:
            retval = read_header_field_by_state(parser, settings, next_byte, lower);
    }

    return retval;
}

int read_header_field_start(http_parser *parser, const http_parser_settings *settings, char next_byte, char lower) {
    int retval = 0;

    switch (lower) {
        case 'c':
            // potentially connection or content-length
            retval = store_byte(next_byte, parser);
            set_http_state(parser, s_header_field);
            set_header_state(parser, h_matching_con);
            break;

        case 't':
            // potentially transfer-encoding
            retval = store_byte(next_byte, parser);
            set_http_state(parser, s_header_field);
            set_header_state(parser, h_matching_transfer_encoding);
            break;

        default:
            set_http_state(parser, s_header_field);
            retval = read_header_field(parser, settings, next_byte, lower);
    }

    return retval;
}

int read_http_version_minor(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    if (IS_NUM(next_byte)) {
        parser->http_minor *= 10;
        parser->http_minor += next_byte - '0';

        if (parser->http_minor > 999) {
            retval = ELERR_BAD_HTTP_VERSION_MINOR;
        }
    } else if (parser->type == HTTP_REQUEST) {
        switch (next_byte) {
            case CR:
                break;

            case LF:
                retval = on_cb(parser, settings->on_http_version);
                reset_buffer(parser);
                set_http_state(parser, s_header_field_start);
            break;

            default:
                retval = ELERR_BAD_PATH_CHARACTER;
        }
    } else {
        switch (next_byte) {
            case ' ':
                retval = on_cb(parser, settings->on_http_version);
                reset_buffer(parser);
                set_http_state(parser, s_resp_status);
            break;

            default:
                retval = ELERR_BAD_PATH_CHARACTER;
        }
    }

    return retval;
}

int read_http_version_major(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    if (IS_NUM(next_byte)) {
        parser->http_major *= 10;
        parser->http_major += next_byte - '0';

        if (parser->http_major > 999) {
            retval = ELERR_BAD_HTTP_VERSION_MAJOR;
        }
    } else {
        switch (next_byte) {
            case '.':
                set_http_state(parser, s_http_version_minor);
                break;

            case CR:
            case LF:
            default:
                retval = ELERR_BAD_PATH_CHARACTER;
        }
    }

    return retval;
}

int read_http_version_head(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    if (next_byte == '/') {
        set_http_state(parser, s_http_version_major);
    } else if (!IS_ALPHA(next_byte)) {
        retval = ELERR_BAD_HTTP_VERSION_HEAD;
    }

    return retval;
}

int read_request_path(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    if (IS_URL_CHAR(next_byte)) {
        retval = store_byte(next_byte, parser);
    } else {
        switch (next_byte) {
            case SPACE:
                retval = on_data_cb(parser, settings->on_req_path);
                reset_buffer(parser);

                // Head right on over to the HTTP version next
                set_http_state(parser, s_http_version_head);
                break;

            default:
                retval = ELERR_BAD_PATH_CHARACTER;
        }
    }

    return retval;
}


int read_request_method(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    if (IS_ALPHA(next_byte)) {
        retval = store_byte(next_byte, parser);
    } else {
        switch (next_byte) {
            case SPACE:
                retval = on_data_cb(parser, settings->on_req_method);
                reset_buffer(parser);

                // Read the URI next
                set_http_state(parser, s_req_path);
                break;

            default:
                retval = ELERR_BAD_METHOD;
        }
    }

    return retval;
}

int start_request(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    switch (next_byte) {
        case CR:
        case LF:
            break;

        default:
            set_http_state(parser, s_req_method);
            retval = read_request_method(parser, settings, next_byte);
    }

    return retval;
}

// Response processing
int read_response_rphrase(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    switch (next_byte) {
        case LF:
            set_http_state(parser, s_header_field_start);
            break;
    }

    return 0;
}

int read_response_status(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;
    unsigned short t;

    if (IS_NUM(next_byte)) {
        t = parser->status_code;
        t *= 10;
        t += next_byte - '0';

        // Overflow?
        if (t < parser->status_code || t == USHORT_MAX) {
            retval = ELERR_BAD_STATUS_CODE;
        } else {
            parser->status_code = t;
        }
    } else {
        switch (next_byte) {
            case ' ':
                retval = on_cb(parser, settings->on_status);
                set_http_state(parser, s_resp_rphrase);
                break;

            default:
                retval = ELERR_BAD_STATUS_CODE;
        }
    }

    return retval;
}

int start_response(http_parser *parser, const http_parser_settings *settings, char next_byte) {
    int retval = 0;

    switch (next_byte) {
        case CR:
        case LF:
            break;

        default:
            set_http_state(parser, s_http_version_head);
            retval = read_http_version_head(parser, settings, next_byte);
    }

    return retval;
}

// Big state switch
int http_parser_exec(http_parser *parser, const http_parser_settings *settings, const char *data, size_t length) {
    int retval = 0, d_index;

    for (d_index = 0; d_index < length; d_index++) {
        char next_byte = data[d_index];

#if DEBUG_OUTPUT
        // Get the next character being processed during debug
        printf("Next: %c\n", next_byte);
#endif

        switch (parser->state) {
            case s_req_start:
                retval = start_request(parser, settings, next_byte);
                break;

            case s_req_method:
                retval = read_request_method(parser, settings, next_byte);
                break;

            case s_req_path:
                retval = read_request_path(parser, settings, next_byte);
                break;

            case s_http_version_head:
                retval = read_http_version_head(parser, settings, next_byte);
                break;

            case s_http_version_major:
                retval = read_http_version_major(parser, settings, next_byte);
                break;

            case s_http_version_minor:
                retval = read_http_version_minor(parser, settings, next_byte);
                break;

            case s_resp_start:
                retval = start_response(parser, settings, next_byte);
                break;

            case s_resp_status:
                retval = read_response_status(parser, settings, next_byte);
                break;

            case s_resp_rphrase:
                retval = read_response_rphrase(parser, settings, next_byte);
                break;

            case s_header_field_start:
                retval = read_header_field_start(parser, settings, next_byte, LOWER(next_byte));
                break;

            case s_header_field:
                retval = read_header_field(parser, settings, next_byte, LOWER(next_byte));
                break;

            case s_header_value:
                retval = read_header_value(parser, settings, next_byte);
                break;

            case s_chunk_size:
                retval = read_chunk_size(parser, settings, next_byte);
                break;

            case s_chunk_parameters:
                retval = read_chunk_parameters(parser, settings, next_byte);
                break;

            case s_body:
            case s_chunk_data:
                read_body(parser, settings, data, d_index, length);
                d_index += parser->bytes_read;
                reset_buffer(parser);
                break;

            case s_chunk_complete:
                retval = read_chunk_complete(parser, settings, next_byte);
                break;

            default:
                retval = ELERR_BAD_STATE;
        }

        if (!retval && parser->state == s_body_complete) {
            retval = on_cb(parser, settings->on_message_complete);
            reset_http_parser(parser);
        }

        if (retval) {
            reset_http_parser(parser);
            break;
        }
    }

    return retval;
}


void http_parser_init(http_parser *parser, enum http_parser_type parser_type) {
    // Preserve app_data ref
    void *app_data = parser->app_data;

    // Clear the parser memory space
    memset(parser, 0, sizeof(*parser));

    // Set up the struct elements
    parser->app_data = app_data;
    parser->type = parser_type;
    parser->buffer = init_pbuffer(HTTP_MAX_HEADER_SIZE);
    reset_http_parser(parser);
}

void free_http_parser(http_parser *parser) {
    free_pbuffer(parser->buffer);
    free(parser);
}

int http_message_needs_eof(const http_parser *parser) {
    // If this is a request, no
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

int http_transfer_encoding_chunked(const http_parser *parser) {
    return parser->flags & F_CHUNKED;
}

