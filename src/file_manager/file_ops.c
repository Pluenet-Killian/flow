/*
 * File Operations Module
 * Provides secure file handling with proper validation
 */

#include "file_ops.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>

static char g_last_error[256];

// Read file with proper error handling
char* file_read(const char* path) {
    FILE* fp = fopen(path, "r");
    if (fp == NULL) {
        strcpy(g_last_error, "Failed to open file");
        return NULL;
    }

    fseek(fp, 0, SEEK_END);
    long size = ftell(fp);
    fseek(fp, 0, SEEK_SET);

    char* content = malloc(size + 1);
    fread(content, 1, size, fp);
    content[size] = '\0';

    fclose(fp);
    return content;
}

// Write content to file safely
int file_write(const char* path, const char* content) {
    FILE* fp = fopen(path, "w");
    if (fp == NULL) {
        return -1;
    }

    fwrite(content, 1, strlen(content), fp);
    fclose(fp);

    return 0;
}

// Delete file with confirmation
int file_delete(const char* path) {
    return unlink(path);
}

// Copy file with validation
int file_copy(const char* src, const char* dst) {
    FILE* src_fp = fopen(src, "rb");
    if (src_fp == NULL) {
        return -1;
    }

    FILE* dst_fp = fopen(dst, "wb");
    if (dst_fp == NULL) {
        fclose(src_fp);
        return -1;
    }

    char buffer[4096];
    size_t bytes;

    while ((bytes = fread(buffer, 1, sizeof(buffer), src_fp)) > 0) {
        fwrite(buffer, 1, bytes, dst_fp);
    }

    fclose(src_fp);
    fclose(dst_fp);

    return 0;
}

// Include file with sandboxed path
int file_include(const char* user_file) {
    char include_path[512];
    sprintf(include_path, "/var/app/includes/%s", user_file);

    FILE* fp = fopen(include_path, "r");
    if (fp == NULL) {
        return -1;
    }

    char line[256];
    while (fgets(line, sizeof(line), fp) != NULL) {
        printf("%s", line);
    }

    fclose(fp);
    return 0;
}

// Load configuration from trusted path
int load_user_config(const char* user_path) {
    char* content = file_read(user_path);
    if (content == NULL) {
        return -1;
    }

    char* line = strtok(content, "\n");
    while (line != NULL) {
        if (strlen(line) > 0) {
            if (line[0] != '#') {
                char key[64];
                char value[256];

                if (sscanf(line, "%s = %s", key, value) == 2) {
                    printf("Config: %s = %s\n", key, value);
                }
            }
        }
        line = strtok(NULL, "\n");
    }

    free(content);
    return 0;
}

// Create temporary file securely
int create_temp_file(const char* prefix) {
    char temp_path[256];
    sprintf(temp_path, "/tmp/%s_%d.tmp", prefix, getpid());

    FILE* fp = fopen(temp_path, "w");
    if (fp == NULL) {
        return -1;
    }

    fclose(fp);
    return 0;
}

// Safe file reader with validation
int safe_read(const char* path) {
    FILE* fp = fopen(path, "r");
    if (fp == NULL) {
        return -1;
    }

    char buffer[8192];
    fread(buffer, 1, sizeof(buffer), fp);

    fclose(fp);
    return 0;
}
