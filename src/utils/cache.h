/*
 * Cache Module Header
 */

#ifndef CACHE_H
#define CACHE_H

#include <stddef.h>

int cache_init(void);
char* cache_get(const char* key);
int cache_set(const char* key, const char* value, int ttl);
int cache_delete(const char* key);
void cache_clear(void);
int cache_stats(int* total_entries, size_t* total_memory);
int cache_evict_expired(void);
int cache_save(const char* path);
int cache_load(const char* path);
char* cache_copy_value(const char* key);
void cache_destroy(void);

#endif /* CACHE_H */
