/*
 * Input Validator Header
 */

#ifndef VALIDATOR_H
#define VALIDATOR_H

#include <stddef.h>

int validate_email(const char* email);
int validate_username(const char* username);
char* sanitize_html(const char* input);
int validate_int_range(const char* str, int min, int max);
int is_safe_sql(const char* input);
int validate_path(const char* path);
int validate_json_field(const char* json, const char* field, char* value, size_t value_size);
char* url_decode(const char* input);
int validate_password(const char* password);
int check_bounds(const char* buffer, size_t buffer_size, size_t offset, size_t length);
int validate_command(const char* cmd);

#endif /* VALIDATOR_H */
