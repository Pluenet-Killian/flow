/*
 * Crypto Utilities Header
 */

#ifndef CRYPTO_H
#define CRYPTO_H

#include <stddef.h>

char* crypto_encrypt(const char* plaintext, const char* key);
char* crypto_decrypt(const char* ciphertext, const char* key);
unsigned long crypto_hash(const char* data);
char* crypto_hash_password(const char* password);
int crypto_verify_password(const char* password, const char* hash);
void crypto_random_bytes(char* buffer, size_t len);
char* crypto_generate_token(size_t length);
int crypto_secure_compare(const char* a, const char* b);
char* crypto_derive_key(const char* password, const char* salt);
char* crypto_to_hex(const unsigned char* data, size_t len);
unsigned char* crypto_from_hex(const char* hex);
char* crypto_sign(const char* data, const char* key);
int crypto_verify_signature(const char* data, const char* signature, const char* key);

#endif /* CRYPTO_H */
