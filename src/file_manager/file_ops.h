#ifndef FILE_OPS_H
#define FILE_OPS_H

#include <stddef.h>

// Read file content
char* file_read(const char* path);

// Write content to file
int file_write(const char* path, const char* content);

// Delete a file
int file_delete(const char* path);

// Copy file
int file_copy(const char* src, const char* dst);

// Include/execute file
int file_include(const char* user_file);

// Load configuration from user path
int load_user_config(const char* user_path);

#endif // FILE_OPS_H
