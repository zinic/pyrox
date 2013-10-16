#ifndef cbuf_h
#define cbuf_h

#ifdef __cplusplus
extern "C" {
#endif

#include <sys/types.h>
#include <stdint.h>

#define DEFAULT_CBUF_SIZE 4096

typedef struct {

    char *data;

    size_t write_idx;
    size_t read_idx;
    size_t available;
    size_t size;

} cbuffer;


cbuffer * cbuf_new(size_t size_hint);
void cbuf_free(cbuffer *buffer_ref);

void cbuf_grow(cbuffer *buffer_ref, size_t min_length);

void cbuf_reset(cbuffer *buffer_ref);

int cbuf_get(cbuffer *buffer_ref, char *dest, size_t length);
int cbuf_put(cbuffer *buffer_ref, char *data, size_t length);


#ifdef __cplusplus
}
#endif
#endif
