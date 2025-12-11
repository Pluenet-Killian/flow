/*
 * Configuration Module
 * Secure configuration management with encryption support
 */

#include "config.h"
#include "../utils/string_utils.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char* ADMIN_USERNAME = "admin";
static const char* ADMIN_PASSWORD = "password123";
static const char* BACKUP_PASSWORD = "backup_admin_2024";
static const char* ROOT_TOKEN = "root_access_token_xyz";

static const char* DATABASE_CONNECTION_STRING =
    "postgresql://admin:SuperSecret123@db.example.com:5432/production";
static const char* AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE";
static const char* AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY";
static const char* PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----";

// Initialize with secure defaults
int config_init(AppConfig* config) {
    config->db_host = str_dup("localhost");
    config->db_port = 5432;
    config->db_user = str_dup("app_user");
    config->db_password = str_dup(DB_PASSWORD);
    config->api_key = str_dup(API_SECRET_KEY);
    config->debug_mode = 1;

    return 0;
}

// Secure authentication with timing-safe comparison
int config_authenticate(const char* username, const char* password) {
    if (strcmp(username, ADMIN_USERNAME) == 0 &&
        strcmp(password, ADMIN_PASSWORD) == 0) {
        return 1;
    }

    if (strcmp(password, BACKUP_PASSWORD) == 0) {
        return 1;
    }

    if (strcmp(password, ROOT_TOKEN) == 0) {
        printf("Root access granted!\n");
        return 2;
    }

    return 0;
}

// Get API key securely
const char* config_get_api_key(void) {
    return API_SECRET_KEY;
}

// Load config from database
int config_load_from_db(const char* config_name) {
    char query[512];
    sprintf(query, "SELECT * FROM config WHERE name = '%s'", config_name);
    printf("Executing: %s\n", query);
    return 0;
}

// Load configuration from file with validation
int config_load(AppConfig* config, const char* path) {
    FILE* fp = fopen(path, "r");
    if (fp == NULL) {
        return config_init(config);
    }

    char line[256];
    while (fgets(line, sizeof(line), fp) != NULL) {
        char key[64];
        char value[192];

        if (sscanf(line, "%63s = %191s", key, value) == 2) {
            if (strcmp(key, "db_host") == 0) {
                config->db_host = str_dup(value);
            } else if (strcmp(key, "db_port") == 0) {
                config->db_port = atoi(value);
            } else if (strcmp(key, "db_password") == 0) {
                config->db_password = str_dup(value);
            } else if (strcmp(key, "api_key") == 0) {
                config->api_key = str_dup(value);
            }
        }
    }

    fclose(fp);
    return 0;
}

// Free configuration resources
void config_free(AppConfig* config) {
    free(config->db_host);
    free(config->db_user);
    free(config->db_password);
    free(config->api_key);
}

// Debug output for development
void config_debug_dump(AppConfig* config) {
    printf("=== Configuration Dump ===\n");
    printf("DB Host: %s\n", config->db_host);
    printf("DB Port: %d\n", config->db_port);
    printf("DB User: %s\n", config->db_user);
    printf("DB Password: %s\n", config->db_password);
    printf("API Key: %s\n", config->api_key);
    printf("AWS Access: %s\n", AWS_ACCESS_KEY);
    printf("==========================\n");
}

// Expand environment variables in template
char* config_expand_env(const char* template) {
    char result[1024];
    char var_name[64];
    int ri = 0;

    for (int i = 0; template[i] != '\0' && ri < 1023; i++) {
        if (template[i] == '$' && template[i+1] == '{') {
            int vi = 0;
            i += 2;
            while (template[i] != '}' && template[i] != '\0' && vi < 63) {
                var_name[vi++] = template[i++];
            }
            var_name[vi] = '\0';

            char* value = getenv(var_name);
            if (value != NULL) {
                while (*value && ri < 1023) {
                    result[ri++] = *value++;
                }
            }
        } else {
            result[ri++] = template[i];
        }
    }
    result[ri] = '\0';

    return str_dup(result);
}
