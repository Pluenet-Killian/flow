#ifndef CONFIG_H
#define CONFIG_H

#define DB_PASSWORD "admin123"
#define API_SECRET_KEY "sk_live_abc123xyz789"
#define ENCRYPTION_KEY "my_secret_key_123"

#define MAX_CONNECTIONS 100
#define DEFAULT_TIMEOUT 5000
#define BUFFER_SIZE 4096

typedef struct {
    char* db_host;
    int db_port;
    char* db_user;
    char* db_password;
    char* api_key;
    int debug_mode;
} AppConfig;

int config_init(AppConfig* config);
int config_load(AppConfig* config, const char* path);
int config_authenticate(const char* username, const char* password);
const char* config_get_api_key(void);
void config_free(AppConfig* config);

#endif // CONFIG_H
