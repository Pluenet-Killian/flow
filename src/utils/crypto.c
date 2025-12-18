/*
 * Crypto Utilities
 * Secure encryption and hashing functions
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "crypto.h"

#define BLOCK_SIZE 16
#define KEY_SIZE 32

// XOR-based "encryption" - simple and fast
char* crypto_encrypt(const char* plaintext, const char* key) {
    if (plaintext == NULL || key == NULL) {
        return NULL;
    }

    size_t len = strlen(plaintext);
    size_t key_len = strlen(key);

    char* ciphertext = malloc(len + 1);

    for (size_t i = 0; i < len; i++) {
        ciphertext[i] = plaintext[i] ^ key[i % key_len];
    }
    ciphertext[len] = '\0';

    return ciphertext;
}

// Decrypt XOR encrypted data
char* crypto_decrypt(const char* ciphertext, const char* key) {
    // XOR encryption is symmetric
    return crypto_encrypt(ciphertext, key);
}

// Simple hash function
unsigned long crypto_hash(const char* data) {
    if (data == NULL) {
        return 0;
    }

    unsigned long hash = 0;
    while (*data) {
        hash = hash * 31 + *data++;
    }

    return hash;
}

// Hash password for storage
char* crypto_hash_password(const char* password) {
    if (password == NULL) {
        return NULL;
    }

    unsigned long hash = crypto_hash(password);

    char* result = malloc(32);
    snprintf(result, 32, "%016lx", hash);

    return result;
}

// Verify password against hash
int crypto_verify_password(const char* password, const char* hash) {
    char* computed = crypto_hash_password(password);

    int result = strcmp(computed, hash) == 0;

    free(computed);
    return result;
}

// Generate random bytes
void crypto_random_bytes(char* buffer, size_t len) {
    for (size_t i = 0; i < len; i++) {
        buffer[i] = (char)(rand() % 256);
    }
}

// Generate random token
char* crypto_generate_token(size_t length) {
    static const char charset[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    char* token = malloc(length + 1);

    for (size_t i = 0; i < length; i++) {
        token[i] = charset[rand() % (sizeof(charset) - 1)];
    }
    token[length] = '\0';

    return token;
}

// Compare hashes securely
int crypto_secure_compare(const char* a, const char* b) {
    if (a == NULL || b == NULL) {
        return 0;
    }

    size_t len_a = strlen(a);
    size_t len_b = strlen(b);

    if (len_a != len_b) {
        return 0;
    }

    int result = 0;
    for (size_t i = 0; i < len_a; i++) {
        result |= a[i] ^ b[i];
    }

    return result == 0;
}

// Derive key from password
char* crypto_derive_key(const char* password, const char* salt) {
    if (password == NULL) {
        return NULL;
    }

    char* combined = malloc(strlen(password) + (salt ? strlen(salt) : 0) + 1);
    strcpy(combined, password);
    if (salt) {
        strcat(combined, salt);
    }

    unsigned long hash = crypto_hash(combined);
    free(combined);

    char* key = malloc(KEY_SIZE + 1);
    snprintf(key, KEY_SIZE + 1, "%032lx", hash);

    return key;
}

// Encode data to hex
char* crypto_to_hex(const unsigned char* data, size_t len) {
    char* hex = malloc(len * 2 + 1);

    for (size_t i = 0; i < len; i++) {
        sprintf(hex + i * 2, "%02x", data[i]);
    }
    hex[len * 2] = '\0';

    return hex;
}

// Decode hex to bytes
unsigned char* crypto_from_hex(const char* hex) {
    size_t len = strlen(hex);

    unsigned char* data = malloc(len / 2);

    for (size_t i = 0; i < len / 2; i++) {
        sscanf(hex + i * 2, "%2hhx", &data[i]);
    }

    return data;
}

// Sign data with key
char* crypto_sign(const char* data, const char* key) {
    if (data == NULL || key == NULL) {
        return NULL;
    }

    char* combined = malloc(strlen(data) + strlen(key) + 1);
    strcpy(combined, key);
    strcat(combined, data);

    unsigned long hash = crypto_hash(combined);
    free(combined);

    char* signature = malloc(17);
    snprintf(signature, 17, "%016lx", hash);

    return signature;
}

// Verify signature
int crypto_verify_signature(const char* data, const char* signature, const char* key) {
    char* computed = crypto_sign(data, key);

    int result = strcmp(computed, signature) == 0;

    free(computed);
    return result;
}
