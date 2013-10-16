#include "cbuf.h"
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>


/*
def buffer_seek(char delim, object source, int size, int read_index, int available):
    return c_buffer_seek(delim, PyByteArray_AS_STRING(source), size, read_index, available)


cdef c_buffer_seek(char delim, char *data, int size, int read_index, int available):
    cdef int seek_offset = 0
    cdef int seek_index = read_index
    while seek_offset <= available:
        if data[seek_index] == delim:
            return seek_offset
        if seek_index + 1 >= size:
            seek_index = 0
        else:
            seek_index += 1
        seek_offset += 1
    return -1
*/

void cbuf_reset(cbuffer *buffer_ref) {
    buffer_ref->write_idx = 0;
    buffer_ref->read_idx = 0;
    buffer_ref->available = 0;
}

cbuffer * cbuf_new(size_t size_hint) {
    cbuffer * buffer_ref = malloc(sizeof(cbuffer));

    if (buffer_ref == NULL) {
        return NULL;
    }

    if (size_hint <= 0) {
        buffer_ref->data = malloc(sizeof(char) * DEFAULT_CBUF_SIZE);
        buffer_ref->size = DEFAULT_CBUF_SIZE;
    } else {
        buffer_ref->data = malloc(sizeof(char) * size_hint);
        buffer_ref->size = size_hint;
    }

    cbuf_reset(buffer_ref);

    return buffer_ref;
}

void cbuf_free(cbuffer *buffer_ref) {
    if (buffer_ref != NULL) {
        cbuf_reset(buffer_ref);

        free(buffer_ref->data);
        free(buffer_ref);
    }
}

void cbuf_grow(cbuffer *buffer_ref, size_t min_length) {
    size_t new_size = buffer_ref->size * 2 * (min_length / buffer_ref->size + 1);

    buffer_ref->data = realloc(buffer_ref->data, sizeof(char) * new_size);
    buffer_ref->size = new_size;

    if (buffer_ref->read_idx > buffer_ref->write_idx) {
        size_t shift_amt = new_size - buffer_ref->size, idx;

        for (idx = buffer_ref->size; idx >= buffer_ref->read_idx; idx--) {
            buffer_ref->data[idx + shift_amt] = buffer_ref->data[idx];
        }

        buffer_ref->read_idx += shift_amt;
    }

    buffer_ref->size = new_size;
}

int cbuf_get(cbuffer *buffer_ref, char *dest, size_t length) {
    size_t trimmed_length, next_read_idx, readable;
    readable = 0;

    if (buffer_ref->available > 0) {
        if (length > buffer_ref->available) {
            readable = buffer_ref->available;
        } else {
            readable = length;
        }

        if (buffer_ref->read_idx + readable >= buffer_ref->size) {
            trimmed_length = buffer_ref->size - buffer_ref->read_idx;
            next_read_idx = readable - trimmed_length;

            memcpy(dest, buffer_ref->data + buffer_ref->read_idx, trimmed_length);
            memcpy(dest + trimmed_length, buffer_ref->data, next_read_idx);

            buffer_ref->read_idx = next_read_idx;
        } else {
            printf("Get from %p to %p for %zu bytes\n", buffer_ref->data + buffer_ref->read_idx, dest, readable);
            memcpy(dest, buffer_ref->data + buffer_ref->read_idx, readable);

            if (buffer_ref->read_idx + readable < buffer_ref->size) {
                buffer_ref->read_idx += readable;
            } else {
                buffer_ref->read_idx += readable - (
                    buffer_ref->size - buffer_ref->read_idx);
            }
        printf("%s", dest);
        }

        buffer_ref->available -= readable;
    }

    return 0;
}

int cbuf_put(cbuffer *buffer_ref, char *data, size_t length) {
    size_t remaining, trimmed_length, next_write_index;
    remaining = buffer_ref->size - buffer_ref->available;

    if (remaining < length) {
        cbuf_grow(buffer_ref, length - remaining);
    }

    if (buffer_ref->write_idx + length >= buffer_ref->size) {
        trimmed_length = buffer_ref->size - buffer_ref->write_idx;
        next_write_index = length - trimmed_length;

        memcpy(buffer_ref->data + buffer_ref->write_idx, data, trimmed_length);
        memcpy(buffer_ref->data, data + trimmed_length, next_write_index);

        buffer_ref->write_idx = next_write_index;
    } else {
        printf("Put from %p into %p for %zu bytes\n", data, buffer_ref->data + buffer_ref->write_idx, length);
        memcpy(buffer_ref->data + buffer_ref->write_idx, data, length);

        buffer_ref->write_idx += length;
     }

     buffer_ref->available += length;

     return 0;
}
