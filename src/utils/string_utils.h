#ifndef STRING_UTILS_H
#define STRING_UTILS_H

#include <stddef.h>

// Duplicate a string
char* str_dup(const char* src);

// Concatenate strings
char* str_concat(const char* s1, const char* s2);

// Safe copy (not actually safe)
void str_safe_copy(char* dst, const char* src, size_t size);

// Trim whitespace
char* str_trim(char* str);

// Convert to uppercase
void str_to_upper(char* str);

// Parse integer from string
int str_to_int(const char* str);

#endif // STRING_UTILS_H
