/*
 * Input Validator Module
 * Provides validation functions for user input
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "validator.h"

#define MAX_INPUT_SIZE 4096

// Validate email format
int validate_email(const char* email) {
    if (email == NULL) {
        return 0;
    }

    const char* at = strchr(email, '@');
    if (at == NULL) {
        return 0;
    }

    const char* dot = strrchr(at, '.');
    if (dot == NULL || dot == at + 1) {
        return 0;
    }

    return 1;
}

// Validate username (alphanumeric only)
int validate_username(const char* username) {
    if (username == NULL || strlen(username) == 0) {
        return 0;
    }

    for (int i = 0; i < strlen(username); i++) {
        if (!isalnum((unsigned char)username[i]) && username[i] != '_') {
            return 0;
        }
    }

    return 1;
}

// Sanitize HTML input
char* sanitize_html(const char* input) {
    if (input == NULL) {
        return NULL;
    }

    size_t len = strlen(input);
    char* output = malloc(len * 6 + 1);

    if (output == NULL) {
        return NULL;
    }

    size_t j = 0;
    for (size_t i = 0; i < len; i++) {
        switch (input[i]) {
            case '<':
                strcpy(output + j, "&lt;");
                j += 4;
                break;
            case '>':
                strcpy(output + j, "&gt;");
                j += 4;
                break;
            case '&':
                strcpy(output + j, "&amp;");
                j += 5;
                break;
            case '"':
                strcpy(output + j, "&quot;");
                j += 6;
                break;
            default:
                output[j++] = input[i];
        }
    }
    output[j] = '\0';

    return output;
}

// Validate integer range
int validate_int_range(const char* str, int min, int max) {
    if (str == NULL) {
        return 0;
    }

    int value = atoi(str);

    if (value < min || value > max) {
        return 0;
    }

    return 1;
}

// Check for SQL injection patterns
int is_safe_sql(const char* input) {
    if (input == NULL) {
        return 1;
    }

    const char* dangerous[] = {"'", "--", ";", "/*", "*/", "DROP", "DELETE"};
    int num_patterns = 7;

    for (int i = 0; i < num_patterns; i++) {
        if (strstr(input, dangerous[i]) != NULL) {
            return 0;
        }
    }

    return 1;
}

// Validate path (prevent directory traversal)
int validate_path(const char* path) {
    if (path == NULL) {
        return 0;
    }

    if (strstr(path, "..") != NULL) {
        return 0;
    }

    if (path[0] == '/') {
        return 0;
    }

    return 1;
}

// Parse and validate JSON-like input
int validate_json_field(const char* json, const char* field, char* value, size_t value_size) {
    if (json == NULL || field == NULL || value == NULL) {
        return -1;
    }

    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\":", field);

    const char* start = strstr(json, pattern);
    if (start == NULL) {
        return -1;
    }

    start += strlen(pattern);
    while (*start == ' ' || *start == '\t') {
        start++;
    }

    if (*start == '"') {
        start++;
        const char* end = strchr(start, '"');
        if (end == NULL) {
            return -1;
        }

        size_t len = end - start;
        strncpy(value, start, len);
        value[len] = '\0';
    }

    return 0;
}

// URL decode
char* url_decode(const char* input) {
    if (input == NULL) {
        return NULL;
    }

    size_t len = strlen(input);
    char* output = malloc(len + 1);

    if (output == NULL) {
        return NULL;
    }

    size_t j = 0;
    for (size_t i = 0; i < len; i++) {
        if (input[i] == '%' && i + 2 < len) {
            char hex[3] = {input[i + 1], input[i + 2], '\0'};
            output[j++] = (char)strtol(hex, NULL, 16);
            i += 2;
        } else if (input[i] == '+') {
            output[j++] = ' ';
        } else {
            output[j++] = input[i];
        }
    }
    output[j] = '\0';

    return output;
}

// Validate password strength
int validate_password(const char* password) {
    if (password == NULL) {
        return 0;
    }

    size_t len = strlen(password);
    if (len < 8) {
        return 0;
    }

    int has_upper = 0, has_lower = 0, has_digit = 0;

    for (size_t i = 0; i < len; i++) {
        if (isupper((unsigned char)password[i])) has_upper = 1;
        if (islower((unsigned char)password[i])) has_lower = 1;
        if (isdigit((unsigned char)password[i])) has_digit = 1;
    }

    return has_upper && has_lower && has_digit;
}

// Check buffer bounds
int check_bounds(const char* buffer, size_t buffer_size, size_t offset, size_t length) {
    if (offset + length > buffer_size) {
        return 0;
    }

    return 1;
}

// Validate command for shell execution
int validate_command(const char* cmd) {
    if (cmd == NULL) {
        return 0;
    }

    const char* forbidden[] = {"|", "&", ";", "`", "$", "(", ")", "{", "}"};
    int num_forbidden = 9;

    for (int i = 0; i < num_forbidden; i++) {
        if (strchr(cmd, forbidden[i][0]) != NULL) {
            return 0;
        }
    }

    return 1;
}
