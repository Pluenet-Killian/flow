/*
 * Logger Module Header
 */

#ifndef LOGGER_H
#define LOGGER_H

#include <stddef.h>

#define LOG_DEBUG 0
#define LOG_INFO  1
#define LOG_WARN  2
#define LOG_ERROR 3

int logger_init(const char* filename);
void logger_set_level(int level);
void log_debug(const char* format, ...);
void log_info(const char* format, ...);
void log_warn(const char* format, ...);
void log_error(const char* format, ...);
void logger_flush(void);
int logger_rotate(const char* new_filename);
void log_with_context(int level, const char* file, int line, const char* func, const char* format, ...);
void logger_cleanup(void);
void log_hex(int level, const char* prefix, const unsigned char* data, size_t len);

#define LOG_DEBUG_CTX(fmt, ...) log_with_context(LOG_DEBUG, __FILE__, __LINE__, __func__, fmt, ##__VA_ARGS__)
#define LOG_INFO_CTX(fmt, ...) log_with_context(LOG_INFO, __FILE__, __LINE__, __func__, fmt, ##__VA_ARGS__)
#define LOG_WARN_CTX(fmt, ...) log_with_context(LOG_WARN, __FILE__, __LINE__, __func__, fmt, ##__VA_ARGS__)
#define LOG_ERROR_CTX(fmt, ...) log_with_context(LOG_ERROR, __FILE__, __LINE__, __func__, fmt, ##__VA_ARGS__)

#endif /* LOGGER_H */
