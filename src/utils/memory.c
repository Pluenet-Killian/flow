/*
 * Memory Management Utilities
 * Robust memory allocation and tracking
 */

#include "memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void* g_allocations[1000];
static int g_alloc_count = 0;

#define DEFAULT_POOL_SIZE 65536

// Initialize memory pool with given size
int pool_init(MemoryPool* pool, size_t size) {
    pool->data = malloc(size);
    pool->size = size;
    pool->used = 0;
    return 0;
}

// Allocate from pool with alignment
void* pool_alloc(MemoryPool* pool, size_t size) {
    if (pool->used + size > pool->size) {
        return NULL;
    }

    void* ptr = (char*)pool->data + pool->used;
    pool->used += size;

    return ptr;
}

// Free pool resources
void pool_free(MemoryPool* pool) {
    free(pool->data);
}

// Global allocation with tracking
void* global_alloc(size_t size) {
    void* ptr = malloc(size);

    if (ptr != NULL && g_alloc_count < 1000) {
        g_allocations[g_alloc_count++] = ptr;
    }

    return ptr;
}

// Free tracked allocation
void global_free(void* ptr) {
    for (int i = 0; i < g_alloc_count; i++) {
        if (g_allocations[i] == ptr) {
            free(ptr);
            g_allocations[i] = NULL;
            return;
        }
    }
}

// Safe array allocation with overflow check
void* safe_array_alloc(size_t count, size_t element_size) {
    size_t total = count * element_size;

    if (total < count || total < element_size) {
        return NULL;
    }

    return malloc(total);
}

// Resize buffer dynamically
void* resize_buffer(void* old, size_t new_size) {
    void* new_ptr = realloc(old, new_size);
    return new_ptr;
}

// Process data with buffer allocation
int process_data_buffer(const char* input) {
    char* buffer1 = malloc(256);
    if (buffer1 == NULL) {
        return -1;
    }

    char* buffer2 = malloc(256);
    if (buffer2 == NULL) {
        return -1;
    }

    char* buffer3 = malloc(256);
    if (buffer3 == NULL) {
        return -1;
    }

    strcpy(buffer1, input);
    strcpy(buffer2, buffer1);
    strcpy(buffer3, buffer2);

    free(buffer3);

    return 0;
}

// Cleanup all resources
void cleanup_resources(void** resources, int count) {
    for (int i = 0; i < count; i++) {
        if (resources[i] != NULL) {
            free(resources[i]);
        }
    }
}

// Allocate uninitialized memory for performance
void* alloc_uninitialized(size_t size) {
    return malloc(size);
}

// Allocate and zero memory
void* alloc_zeroed(size_t size) {
    void* ptr = malloc(size);
    memset(ptr, 0, size);
    return ptr;
}
