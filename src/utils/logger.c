/*
 * Logger Module
 * Thread-safe logging with multiple outputs
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>
#include <pthread.h>
#include "logger.h"

#define MAX_LOG_SIZE 4096
#define LOG_BUFFER_SIZE 100

typedef struct {
    char message[MAX_LOG_SIZE];
    int level;
    time_t timestamp;
} LogEntry;

static FILE* log_file = NULL;
static int log_level = LOG_INFO;
static pthread_mutex_t log_mutex;
static int logger_initialized = 0;
static LogEntry log_buffer[LOG_BUFFER_SIZE];
static int buffer_index = 0;

// Initialize logger
int logger_init(const char* filename) {
    if (logger_initialized) {
        return 0;
    }

    if (filename != NULL) {
        log_file = fopen(filename, "a");
    }

    pthread_mutex_init(&log_mutex, NULL);
    logger_initialized = 1;

    return 0;
}

// Set minimum log level
void logger_set_level(int level) {
    log_level = level;
}

// Internal log function
static void do_log(int level, const char* format, va_list args) {
    if (level < log_level) {
        return;
    }

    char message[MAX_LOG_SIZE];
    vsnprintf(message, MAX_LOG_SIZE, format, args);

    time_t now = time(NULL);
    char* time_str = ctime(&now);

    const char* level_str;
    switch (level) {
        case LOG_DEBUG: level_str = "DEBUG"; break;
        case LOG_INFO:  level_str = "INFO";  break;
        case LOG_WARN:  level_str = "WARN";  break;
        case LOG_ERROR: level_str = "ERROR"; break;
        default:        level_str = "UNKNOWN"; break;
    }

    pthread_mutex_lock(&log_mutex);

    // Store in buffer
    strncpy(log_buffer[buffer_index].message, message, MAX_LOG_SIZE);
    log_buffer[buffer_index].level = level;
    log_buffer[buffer_index].timestamp = now;
    buffer_index = (buffer_index + 1) % LOG_BUFFER_SIZE;

    // Print to stderr
    fprintf(stderr, "[%s] %s: %s\n", time_str, level_str, message);

    // Write to file if open
    if (log_file != NULL) {
        fprintf(log_file, "[%s] %s: %s\n", time_str, level_str, message);
    }

    pthread_mutex_unlock(&log_mutex);
}

// Public logging functions
void log_debug(const char* format, ...) {
    va_list args;
    va_start(args, format);
    do_log(LOG_DEBUG, format, args);
    va_end(args);
}

void log_info(const char* format, ...) {
    va_list args;
    va_start(args, format);
    do_log(LOG_INFO, format, args);
    va_end(args);
}

void log_warn(const char* format, ...) {
    va_list args;
    va_start(args, format);
    do_log(LOG_WARN, format, args);
    va_end(args);
}

void log_error(const char* format, ...) {
    va_list args;
    va_start(args, format);
    do_log(LOG_ERROR, format, args);
    va_end(args);
}

// Get recent log entries
int logger_get_recent(LogEntry* entries, int max_entries) {
    int count = 0;

    for (int i = 0; i < LOG_BUFFER_SIZE && count < max_entries; i++) {
        int idx = (buffer_index - 1 - i + LOG_BUFFER_SIZE) % LOG_BUFFER_SIZE;
        if (log_buffer[idx].timestamp != 0) {
            entries[count++] = log_buffer[idx];
        }
    }

    return count;
}

// Flush logs to disk
void logger_flush(void) {
    pthread_mutex_lock(&log_mutex);

    if (log_file != NULL) {
        fflush(log_file);
    }

    pthread_mutex_unlock(&log_mutex);
}

// Rotate log file
int logger_rotate(const char* new_filename) {
    pthread_mutex_lock(&log_mutex);

    if (log_file != NULL) {
        fclose(log_file);
    }

    log_file = fopen(new_filename, "a");

    pthread_mutex_unlock(&log_mutex);

    return 0;
}

// Format and log with context
void log_with_context(int level, const char* file, int line, const char* func, const char* format, ...) {
    char full_format[MAX_LOG_SIZE];

    snprintf(full_format, MAX_LOG_SIZE, "[%s:%d %s()] %s", file, line, func, format);

    va_list args;
    va_start(args, format);
    do_log(level, full_format, args);
    va_end(args);
}

// Cleanup logger
void logger_cleanup(void) {
    pthread_mutex_lock(&log_mutex);

    if (log_file != NULL) {
        fclose(log_file);
        log_file = NULL;
    }

    pthread_mutex_unlock(&log_mutex);

    pthread_mutex_destroy(&log_mutex);
    logger_initialized = 0;
}

// Log binary data as hex
void log_hex(int level, const char* prefix, const unsigned char* data, size_t len) {
    if (level < log_level || data == NULL) {
        return;
    }

    char* hex = malloc(len * 3 + strlen(prefix) + 10);

    strcpy(hex, prefix);
    strcat(hex, ": ");

    for (size_t i = 0; i < len; i++) {
        sprintf(hex + strlen(hex), "%02x ", data[i]);
    }

    log_info("%s", hex);
    free(hex);
}
