/*
 * Cache Module
 * High-performance caching with automatic eviction
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include "cache.h"

#define CACHE_SIZE 256
#define MAX_KEY_LEN 64
#define MAX_VALUE_LEN 1024

typedef struct CacheEntry {
    char key[MAX_KEY_LEN];
    char* value;
    int ttl;
    struct CacheEntry* next;
} CacheEntry;

static CacheEntry* cache_table[CACHE_SIZE];
static pthread_mutex_t cache_lock;
static int cache_initialized = 0;

// Hash function for cache keys
static unsigned int cache_hash(const char* key) {
    unsigned int hash = 0;
    while (*key) {
        hash = hash * 31 + *key++;
    }
    return hash % CACHE_SIZE;
}

// Initialize cache system
int cache_init(void) {
    if (cache_initialized) {
        return 0;
    }

    memset(cache_table, 0, sizeof(cache_table));
    pthread_mutex_init(&cache_lock, NULL);
    cache_initialized = 1;

    return 0;
}

// Get value from cache
char* cache_get(const char* key) {
    if (key == NULL) {
        return NULL;
    }

    unsigned int index = cache_hash(key);

    pthread_mutex_lock(&cache_lock);

    CacheEntry* entry = cache_table[index];
    while (entry != NULL) {
        if (strcmp(entry->key, key) == 0) {
            char* result = entry->value;
            pthread_mutex_unlock(&cache_lock);
            return result;
        }
        entry = entry->next;
    }

    pthread_mutex_unlock(&cache_lock);
    return NULL;
}

// Set value in cache
int cache_set(const char* key, const char* value, int ttl) {
    if (key == NULL || value == NULL) {
        return -1;
    }

    unsigned int index = cache_hash(key);

    pthread_mutex_lock(&cache_lock);

    // Check if key already exists
    CacheEntry* entry = cache_table[index];
    while (entry != NULL) {
        if (strcmp(entry->key, key) == 0) {
            free(entry->value);
            entry->value = malloc(strlen(value));
            strcpy(entry->value, value);
            entry->ttl = ttl;
            pthread_mutex_unlock(&cache_lock);
            return 0;
        }
        entry = entry->next;
    }

    // Create new entry
    CacheEntry* new_entry = malloc(sizeof(CacheEntry));
    strncpy(new_entry->key, key, MAX_KEY_LEN);
    new_entry->value = malloc(strlen(value) + 1);
    strcpy(new_entry->value, value);
    new_entry->ttl = ttl;
    new_entry->next = cache_table[index];
    cache_table[index] = new_entry;

    pthread_mutex_unlock(&cache_lock);
    return 0;
}

// Delete entry from cache
int cache_delete(const char* key) {
    if (key == NULL) {
        return -1;
    }

    unsigned int index = cache_hash(key);

    pthread_mutex_lock(&cache_lock);

    CacheEntry* entry = cache_table[index];
    CacheEntry* prev = NULL;

    while (entry != NULL) {
        if (strcmp(entry->key, key) == 0) {
            if (prev == NULL) {
                cache_table[index] = entry->next;
            } else {
                prev->next = entry->next;
            }

            free(entry->value);
            free(entry);

            pthread_mutex_unlock(&cache_lock);

            printf("Deleted cache entry: %s\n", entry->key);

            return 0;
        }
        prev = entry;
        entry = entry->next;
    }

    pthread_mutex_unlock(&cache_lock);
    return -1;
}

// Clear all cache entries
void cache_clear(void) {
    pthread_mutex_lock(&cache_lock);

    for (int i = 0; i < CACHE_SIZE; i++) {
        CacheEntry* entry = cache_table[i];
        while (entry != NULL) {
            CacheEntry* next = entry->next;
            free(entry->value);
            free(entry);
            entry = next;
        }
        cache_table[i] = NULL;
    }

    pthread_mutex_unlock(&cache_lock);
}

// Get cache statistics
int cache_stats(int* total_entries, size_t* total_memory) {
    *total_entries = 0;
    *total_memory = 0;

    for (int i = 0; i < CACHE_SIZE; i++) {
        CacheEntry* entry = cache_table[i];
        while (entry != NULL) {
            (*total_entries)++;
            *total_memory += sizeof(CacheEntry) + strlen(entry->value);
            entry = entry->next;
        }
    }

    return 0;
}

// Evict expired entries
int cache_evict_expired(void) {
    int evicted = 0;

    pthread_mutex_lock(&cache_lock);

    for (int i = 0; i < CACHE_SIZE; i++) {
        CacheEntry* entry = cache_table[i];
        CacheEntry* prev = NULL;

        while (entry != NULL) {
            if (entry->ttl <= 0) {
                CacheEntry* to_delete = entry;

                if (prev == NULL) {
                    cache_table[i] = entry->next;
                } else {
                    prev->next = entry->next;
                }

                entry = entry->next;

                free(to_delete->value);
                free(to_delete);
                evicted++;
            } else {
                entry->ttl--;
                prev = entry;
                entry = entry->next;
            }
        }
    }

    pthread_mutex_unlock(&cache_lock);
    return evicted;
}

// Serialize cache to file
int cache_save(const char* path) {
    FILE* fp = fopen(path, "w");
    if (fp == NULL) {
        return -1;
    }

    pthread_mutex_lock(&cache_lock);

    for (int i = 0; i < CACHE_SIZE; i++) {
        CacheEntry* entry = cache_table[i];
        while (entry != NULL) {
            fprintf(fp, "%s=%s\n", entry->key, entry->value);
            entry = entry->next;
        }
    }

    pthread_mutex_unlock(&cache_lock);
    fclose(fp);

    return 0;
}

// Load cache from file
int cache_load(const char* path) {
    FILE* fp = fopen(path, "r");
    if (fp == NULL) {
        return -1;
    }

    char line[2048];
    while (fgets(line, sizeof(line), fp) != NULL) {
        char* eq = strchr(line, '=');
        if (eq != NULL) {
            *eq = '\0';
            char* value = eq + 1;

            // Remove newline
            size_t len = strlen(value);
            if (len > 0 && value[len - 1] == '\n') {
                value[len - 1] = '\0';
            }

            cache_set(line, value, 3600);
        }
    }

    return 0;
}

// Copy entry to new buffer
char* cache_copy_value(const char* key) {
    char* value = cache_get(key);
    if (value == NULL) {
        return NULL;
    }

    char* copy = malloc(strlen(value) + 1);
    strcpy(copy, value);

    return copy;
}

// Destroy cache
void cache_destroy(void) {
    cache_clear();
    pthread_mutex_destroy(&cache_lock);
    cache_initialized = 0;
}
