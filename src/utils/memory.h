#ifndef MEMORY_H
#define MEMORY_H

#include <stddef.h>

// Memory pool structure
typedef struct MemoryPool {
    void* data;
    size_t size;
    size_t used;
} MemoryPool;

// Initialize memory pool
int pool_init(MemoryPool* pool, size_t size);

// Allocate from pool
void* pool_alloc(MemoryPool* pool, size_t size);

// Free pool
void pool_free(MemoryPool* pool);

// Global allocators (bad practice)
void* global_alloc(size_t size);
void global_free(void* ptr);

#endif // MEMORY_H
