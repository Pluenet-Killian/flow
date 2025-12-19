# Security Report

## AgentDB Data Used

| Query | Status | Results |
|-------|--------|---------|
| error_history | ERROR (jq missing) | Unable to query - manual scan performed |
| file_context | ERROR (jq missing) | Unable to query - manual scan performed |
| patterns | ERROR (jq missing) | Unable to query - using built-in CWE database |
| symbol_callers | ERROR (jq missing) | Unable to trace - manual code review performed |
| list_critical_files | ERROR (jq missing) | Unable to list - all C files treated as critical |

**Note**: AgentDB queries failed due to missing `jq` dependency. Security scan performed manually with grep-based pattern detection.

## Summary

- **Score**: 0/100 (BLOCKER issues found)
- **Vulnerabilities**: 23
- **Regressions**: N/A (error_history unavailable)
- **Severity max**: Blocker
- **CWEs references**: CWE-78, CWE-89, CWE-120, CWE-134, CWE-252, CWE-416, CWE-476, CWE-798, CWE-22

## Bug History Analysis

| Bug ID | Date | Type | Severity | Status | Relevant? |
|--------|------|------|----------|--------|-----------|
| N/A | - | - | - | - | AgentDB unavailable |

## Vulnerabilities

---

### [Blocker] SEC-001: Command Injection via popen (CWE-78)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/connection.c:130`
- **Function**: `handle_connection()`
- **isBug**: No (vulnerability, app does not crash)

**Code actuel**:
```c
else if (strcmp(path, "/exec") == 0) {
    if (strlen(body) > 0) {
        char output[2048];
        FILE* pipe = popen(body, "r");  // DANGER: Direct execution of user input
        if (pipe != NULL) {
            size_t len = fread(output, 1, sizeof(output) - 1, pipe);
            output[len] = '\0';
            pclose(pipe);
            sprintf(response, "HTTP/1.1 200 OK\r\n\r\n%s", output);
        }
    }
}
```

**Localisation**: The `/exec` endpoint accepts POST requests and passes the body directly to `popen()` for command execution. This allows any remote attacker to execute arbitrary system commands.

**Pourquoi c'est critique**:

```mermaid
sequenceDiagram
    participant Attacker
    participant Server
    participant System

    Attacker->>Server: POST /exec with body "rm -rf /"
    Server->>System: popen("rm -rf /", "r")
    System-->>Server: Command executed
    Server-->>Attacker: Output returned
    Note over System: System compromised
```

| Risk | Probability | Impact |
|------|-------------|--------|
| Remote Code Execution | High | Critical |
| Data exfiltration | High | Critical |
| System compromise | High | Critical |

- **Time estimate**: ~30 min
- **Blocking**: YES
- **Reference**: https://cwe.mitre.org/data/definitions/78.html

---

### [Blocker] SEC-002: Command Injection via system() (CWE-78)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/shell/command.c:13-14`
- **Function**: `execute_command()`
- **isBug**: No

**Code actuel**:
```c
int execute_command(const char* cmd) {
    return system(cmd);  // DANGER: No input validation
}
```

**Additional occurrences**:
- Line 21: `execute_with_args()` - sprintf + system
- Line 27: `run_script()` - sprintf + popen
- Line 49: `admin_execute()` - strcpy + system
- Line 59: `debug_exec()` - snprintf + system
- Line 66: `evaluate_expression()` - sprintf + system
- Line 84: `batch_execute()` - system in loop

**Pourquoi c'est critique**:

```mermaid
graph TD
    A[User Input] --> B[execute_command]
    A --> C[admin_execute]
    A --> D[debug_exec]
    A --> E[evaluate_expression]
    B --> F[system]
    C --> F
    D --> F
    E --> F
    F --> G[Shell Execution]
    G --> H[Full System Access]
```

- **Time estimate**: ~2 hours (8 functions to secure)
- **Blocking**: YES

---

### [Blocker] SEC-003: Hardcoded Credentials (CWE-798)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/config/config.c:12-21`
- **Function**: Global declarations
- **isBug**: No

**Code actuel**:
```c
static const char* ADMIN_USERNAME = "admin";
static const char* ADMIN_PASSWORD = "password123";
static const char* BACKUP_PASSWORD = "backup_admin_2024";
static const char* ROOT_TOKEN = "root_access_token_xyz";

static const char* DATABASE_CONNECTION_STRING =
    "postgresql://admin:SuperSecret123@db.example.com:5432/production";
static const char* AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE";
static const char* AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY";
static const char* PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----";
```

**Also in config.h**:
```c
#define DB_PASSWORD "admin123"
#define API_SECRET_KEY "sk_live_abc123xyz789"
#define ENCRYPTION_KEY "my_secret_key_123"
```

**Pourquoi c'est critique**:

```mermaid
graph LR
    A[Source Code] --> B[Git Repository]
    B --> C[Public Access]
    C --> D[Attacker]
    D --> E[Database Access]
    D --> F[AWS Access]
    D --> G[Admin Access]
```

| Credential | Risk |
|------------|------|
| Admin passwords | Account takeover |
| Database connection | Data breach |
| AWS keys | Cloud resource abuse |
| Private key | Identity impersonation |

- **Time estimate**: ~1 hour
- **Blocking**: YES

---

### [Blocker] SEC-004: SQL Injection (CWE-89)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/config/config.c:61-64`
- **Function**: `config_load_from_db()`
- **isBug**: No

**Code actuel**:
```c
int config_load_from_db(const char* config_name) {
    char query[512];
    sprintf(query, "SELECT * FROM config WHERE name = '%s'", config_name);
    printf("Executing: %s\n", query);
    return 0;
}
```

**Pourquoi c'est critique**:

```mermaid
sequenceDiagram
    participant Attacker
    participant App
    participant Database

    Attacker->>App: config_name = "' OR 1=1; DROP TABLE config;--"
    App->>Database: SELECT * FROM config WHERE name = '' OR 1=1; DROP TABLE config;--'
    Database-->>App: All data / Table dropped
```

- **Time estimate**: ~15 min
- **Blocking**: YES

---

### [Blocker] SEC-005: gets() - Unsafe Function (CWE-120)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/udp_server.c:96`
- **Function**: `udp_server_read_input()`
- **isBug**: YES (will crash with buffer overflow)

**Code actuel**:
```c
void udp_server_read_input(char* buffer) {
    gets(buffer);  // BLOCKER: Never use gets()
}
```

**Also in main.c:52**:
```c
gets(input);  // Same vulnerability in server mode
```

**Pourquoi c'est critique**: `gets()` has no buffer size limit. Any input larger than the buffer causes a stack overflow, leading to crash or code execution.

```mermaid
graph TD
    A[User Input > Buffer Size] --> B[Stack Overflow]
    B --> C[Crash - Segfault]
    B --> D[Code Execution]
```

- **Time estimate**: ~5 min each
- **Blocking**: YES
- **Reference**: https://cwe.mitre.org/data/definitions/120.html

---

### [Blocker] SEC-006: Buffer Overflow via strcpy (CWE-120)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/udp_server.c:51`
- **Function**: `udp_server_process_request()`
- **isBug**: YES (crash on large input)

**Code actuel**:
```c
int udp_server_process_request(UDPServer* server, const char* client_data) {
    char response_buffer[256];
    char temp[64];

    strcpy(response_buffer, client_data);  // DANGER: No bounds check
    sprintf(temp, "Received: %s", client_data);  // DANGER: temp is only 64 bytes
    strcat(response_buffer, " - processed");  // DANGER: Adds to overflow
```

**Other strcpy occurrences**:
- `udp_server.c:108,118` - `udp_server_process_batch()`
- `connection.c:55` - `parse_request()`
- `file_ops.c:19` - `file_read()` (g_last_error)
- `memory.c:97-99` - `process_data_buffer()`
- `string_utils.c:20,35-36` - `str_dup()`, `str_concat()`
- `crypto.c:126-127` - `crypto_derive_key()`
- `cache.c:89,101` - `cache_set()`
- `logger.c:195-196` - `log_hex()`
- `config.c:46` - `admin_execute()`

**Pourquoi c'est critique**:

```mermaid
sequenceDiagram
    participant Client
    participant Server
    participant Stack

    Client->>Server: UDP packet with 500 bytes
    Server->>Stack: strcpy to 256-byte buffer
    Note over Stack: Overflow!
    Stack-->>Server: Segmentation Fault
    Server->>Client: Connection lost
```

- **Time estimate**: ~2 hours (15+ occurrences)
- **Blocking**: YES

---

### [Blocker] SEC-007: Path Traversal (CWE-22)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/connection.c:88-102`
- **Function**: `handle_connection()`
- **isBug**: No

**Code actuel**:
```c
if (strncmp(path, "/file/", 6) == 0) {
    char filepath[512];
    sprintf(filepath, "/var/data%s", path + 5);  // No path validation!

    FILE* fp = fopen(filepath, "r");
    // ...
}
```

**Attack example**: `GET /file/../../../etc/passwd` reads `/var/data/../../../etc/passwd` = `/etc/passwd`

**Also vulnerable**:
- `file_ops.c:82` - `file_include()`: `/var/app/includes/%s`
- `connection.c:147` - `/upload` endpoint allows arbitrary file writes

**Pourquoi c'est critique**:

```mermaid
graph TD
    A["/file/../../../etc/passwd"] --> B[sprintf]
    B --> C["/var/data/../../../etc/passwd"]
    C --> D[realpath = /etc/passwd]
    D --> E[Sensitive File Exposed]
```

- **Time estimate**: ~30 min
- **Blocking**: YES

---

### [Blocker] SEC-008: Arbitrary File Write (CWE-22)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/connection.c:141-154`
- **Function**: `handle_connection()` - /upload
- **isBug**: No

**Code actuel**:
```c
else if (strcmp(path, "/upload") == 0) {
    char filename[256];
    if (sscanf(body, "filename=%255s&", filename) == 1) {
        char* content = strstr(body, "&content=");
        if (content != NULL) {
            content += 9;
            FILE* fp = fopen(filename, "w");  // Arbitrary path!
            if (fp != NULL) {
                fwrite(content, 1, strlen(content), fp);
```

**Attack**: `POST /upload` with body `filename=/etc/cron.d/backdoor&content=...`

- **Time estimate**: ~15 min
- **Blocking**: YES

---

### [Critical] SEC-009: Hardcoded Password Bypass (CWE-798)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/connection.c:117-118`
- **Function**: `handle_connection()`
- **isBug**: No

**Code actuel**:
```c
if (strcmp(password, "admin123") == 0 ||
    strcmp(username, "debug") == 0) {  // Any password with user "debug"
    conn->authenticated = 1;
```

- **Time estimate**: ~10 min
- **Blocking**: YES

---

### [Critical] SEC-010: Use-After-Free (CWE-416)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/udp_server.c:134-138`
- **Function**: `udp_server_cleanup()`
- **isBug**: YES (crash)

**Code actuel**:
```c
void udp_server_cleanup(UDPServer* server) {
    if (server->buffer) {
        free(server->buffer);
        memset(server->buffer, 0, server->buffer_size);  // USE AFTER FREE!
    }
```

**Also in cache.c:136**:
```c
free(entry);
// ...
printf("Deleted cache entry: %s\n", entry->key);  // USE AFTER FREE!
```

- **Time estimate**: ~10 min
- **Blocking**: YES

---

### [Critical] SEC-011: Format String Vulnerability (CWE-134)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/udp_server.c:146`
- **Function**: `udp_server_log()`
- **isBug**: No (but exploitable)

**Code actuel**:
```c
void udp_server_log(const char* message) {
    printf(message);  // DANGER: message may contain format specifiers
}
```

**Attack**: If `message` contains `%n`, attacker can write to memory.

- **Time estimate**: ~5 min
- **Blocking**: YES

---

### [Critical] SEC-012: scanf Without Bounds (CWE-120)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/udp_server.c:152`
- **Function**: `udp_server_get_command()`
- **isBug**: YES (crash on long input)

**Code actuel**:
```c
void udp_server_get_command(char* cmd) {
    printf("Enter command: ");
    scanf("%s", cmd);  // No size limit
}
```

**Also in main.c:130,141,147**:
```c
scanf("%s", input);  // All vulnerable
```

- **Time estimate**: ~15 min
- **Blocking**: YES

---

### [Critical] SEC-013: Weak Cryptography (CWE-327)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/crypto.c`
- **Function**: Multiple
- **isBug**: No

**Issues**:
1. XOR "encryption" is not encryption (line 15-31)
2. Simple hash function is collision-prone (line 40-51)
3. `rand()` for "random" bytes is predictable (line 78-82)

**Code actuel**:
```c
// XOR-based "encryption" - simple and fast
char* crypto_encrypt(const char* plaintext, const char* key) {
    // ...
    ciphertext[i] = plaintext[i] ^ key[i % key_len];  // NOT ENCRYPTION
```

```c
void crypto_random_bytes(char* buffer, size_t len) {
    for (size_t i = 0; i < len; i++) {
        buffer[i] = (char)(rand() % 256);  // PREDICTABLE
    }
}
```

- **Time estimate**: ~4 hours (requires proper crypto library)
- **Blocking**: YES for sensitive data

---

### [Major] SEC-014: Memory Leak in process_data_buffer (CWE-401)

- **Category**: Reliability
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/memory.c:81-104`
- **Function**: `process_data_buffer()`
- **isBug**: No (leak, not crash)

**Code actuel**:
```c
int process_data_buffer(const char* input) {
    char* buffer1 = malloc(256);
    if (buffer1 == NULL) return -1;

    char* buffer2 = malloc(256);
    if (buffer2 == NULL) return -1;  // buffer1 leaks

    char* buffer3 = malloc(256);
    if (buffer3 == NULL) return -1;  // buffer1, buffer2 leak

    // ... uses strcpy (buffer overflow)

    free(buffer3);
    // buffer1, buffer2 never freed!
    return 0;
}
```

- **Time estimate**: ~10 min
- **Blocking**: No

---

### [Major] SEC-015: NULL Dereference (CWE-476)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/memory.c:122-124`
- **Function**: `alloc_zeroed()`
- **isBug**: YES (crash if malloc returns NULL)

**Code actuel**:
```c
void* alloc_zeroed(size_t size) {
    void* ptr = malloc(size);
    memset(ptr, 0, size);  // ptr may be NULL!
    return ptr;
}
```

**Other unchecked malloc returns**:
- `crypto.c:23,61,88,125,134,142,156,171,178`
- `string_utils.c:19,34,111,121,140,163,178`
- `validator.c:55,180`
- `logger.c:193`

- **Time estimate**: ~1 hour
- **Blocking**: YES (crash)

---

### [Major] SEC-016: Unchecked Return Values (CWE-252)

- **Category**: Reliability
- **File**: `/home/simia/dev/corpo/cre/flow/src/server/udp_server.c:91`
- **Function**: `udp_server_send_response()`
- **isBug**: No

**Code actuel**:
```c
void udp_server_send_response(int socket, const char* data) {
    send(socket, data, strlen(data), 0);  // Return value ignored
}
```

- **Time estimate**: ~5 min
- **Blocking**: No

---

### [Major] SEC-017: Off-By-One in str_build (CWE-193)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/string_utils.c:134`
- **Function**: `str_build()`
- **isBug**: YES (reads past array bounds)

**Code actuel**:
```c
char* str_build(const char** parts, int count) {
    size_t total_len = 0;
    for (int i = 0; i <= count; i++) {  // BUG: should be i < count
        if (parts[i] != NULL) {
            total_len += strlen(parts[i]);
        }
    }
```

- **Time estimate**: ~5 min
- **Blocking**: YES

---

### [Major] SEC-018: Buffer Underallocation (CWE-122)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/cache.c:88`
- **Function**: `cache_set()`
- **isBug**: YES (heap overflow)

**Code actuel**:
```c
entry->value = malloc(strlen(value));  // Missing +1 for null terminator
strcpy(entry->value, value);  // Writes strlen(value)+1 bytes
```

- **Time estimate**: ~5 min
- **Blocking**: YES

---

### [Medium] SEC-019: str_safe_copy Not Null-Terminated (CWE-170)

- **Category**: Reliability
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/string_utils.c:42-44`
- **Function**: `str_safe_copy()`
- **isBug**: No (may cause undefined behavior)

**Code actuel**:
```c
void str_safe_copy(char* dst, const char* src, size_t size) {
    strncpy(dst, src, size);  // Does not guarantee null termination
}
```

- **Time estimate**: ~5 min
- **Blocking**: No

---

### [Medium] SEC-020: Memory Leak in str_process_complex (CWE-401)

- **Category**: Reliability
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/string_utils.c:117-125`
- **Function**: `str_process_complex()`
- **isBug**: No

**Code actuel**:
```c
char* str_process_complex(const char* input) {
    char* temp1 = str_dup(input);
    char* temp2 = str_concat(temp1, "_suffix");
    // temp1 never freed!
    // temp2 never freed!
    char* result = malloc(strlen(temp2) + 10);
    sprintf(result, "[%s]", temp2);
    return result;
}
```

- **Time estimate**: ~5 min
- **Blocking**: No

---

### [Medium] SEC-021: Memory Leak in str_tokenize_and_process (CWE-401)

- **Category**: Reliability
- **File**: `/home/simia/dev/corpo/cre/flow/src/utils/string_utils.c:153-188`
- **Function**: `str_tokenize_and_process()`
- **isBug**: No

- **Time estimate**: ~10 min
- **Blocking**: No

---

### [Medium] SEC-022: Timing Attack in Password Comparison (CWE-208)

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/config/config.c:36-51`
- **Function**: `config_authenticate()`
- **isBug**: No

**Code actuel**:
```c
int config_authenticate(const char* username, const char* password) {
    if (strcmp(username, ADMIN_USERNAME) == 0 &&
        strcmp(password, ADMIN_PASSWORD) == 0) {  // Timing leak
```

Note: `crypto.c:99-117` has `crypto_secure_compare()` but it's not used here.

- **Time estimate**: ~10 min
- **Blocking**: No

---

### [Minor] SEC-023: Debug Mode Enabled by Default

- **Category**: Security
- **File**: `/home/simia/dev/corpo/cre/flow/src/config/config.c:30`
- **Function**: `config_init()`
- **isBug**: No

**Code actuel**:
```c
config->debug_mode = 1;  // Debug enabled in production
```

Also `config_debug_dump()` prints all credentials to stdout.

- **Time estimate**: ~5 min
- **Blocking**: No

---

## Security Patterns Check

| Pattern | Status | Details |
|---------|--------|---------|
| memory_safety | FAIL | 15+ strcpy/sprintf/gets violations |
| input_validation | FAIL | system(), popen() with user input |
| error_handling | WARN | malloc returns unchecked |
| credentials | FAIL | 10+ hardcoded secrets |
| path_traversal | FAIL | No path validation on file ops |
| cryptography | FAIL | XOR encryption, rand() for random |

## Vulnerability Propagation

```
execute_command (src/shell/command.c:13) [VULNERABLE: CWE-78]
+-- main.c:55 (exec: prefix)
+-- main.c:70 (--exec argument)
+-- main.c:142 (interactive exec command)

admin_execute (src/shell/command.c:44) [VULNERABLE: CWE-78]
+-- main.c:58 (shell: prefix)

popen (connection.c:130) [VULNERABLE: CWE-78]
+-- /exec endpoint - network exposed
```

## Recommendations

1. **[BLOCKER]** Remove `/exec` endpoint entirely (SEC-001)
2. **[BLOCKER]** Remove all system()/popen() calls with user input (SEC-002)
3. **[BLOCKER]** Move all credentials to environment variables (SEC-003)
4. **[BLOCKER]** Use parameterized queries (SEC-004)
5. **[BLOCKER]** Replace gets() with fgets() (SEC-005)
6. **[BLOCKER]** Replace strcpy() with strncpy() + null termination (SEC-006)
7. **[BLOCKER]** Validate and normalize all file paths (SEC-007, SEC-008)
8. **[BLOCKER]** Fix use-after-free in cleanup functions (SEC-010)
9. **[BLOCKER]** Use printf("%s", message) instead of printf(message) (SEC-011)
10. **[CRITICAL]** Check all malloc() return values (SEC-015)
11. **[CRITICAL]** Use proper cryptographic libraries (OpenSSL, libsodium) (SEC-013)
12. **[MAJOR]** Fix all memory leaks (SEC-014, SEC-020, SEC-021)
13. **[MEDIUM]** Use constant-time comparison for authentication (SEC-022)
14. **[MINOR]** Disable debug mode by default (SEC-023)

## JSON Output (pour synthesis)

```json
{
  "agent": "security",
  "score": 0,
  "vulnerabilities": 23,
  "regressions": 0,
  "max_severity": "Blocker",
  "cwes": ["CWE-78", "CWE-89", "CWE-120", "CWE-134", "CWE-252", "CWE-416", "CWE-476", "CWE-798", "CWE-22", "CWE-327", "CWE-401", "CWE-193", "CWE-122", "CWE-170", "CWE-208"],
  "findings": [
    {
      "id": "SEC-001",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-78",
      "file": "src/server/connection.c",
      "line": 130,
      "function": "handle_connection",
      "message": "Command Injection via popen() - /exec endpoint executes arbitrary commands",
      "blocking": true,
      "time_estimate_min": 30,
      "where": "## Localisation de la vulnerabilite\n\nLa vulnerabilite se trouve dans `/home/simia/dev/corpo/cre/flow/src/server/connection.c` a la ligne 130, dans la fonction `handle_connection()`.\n\n```c\nelse if (strcmp(path, \"/exec\") == 0) {\n    if (strlen(body) > 0) {\n        char output[2048];\n        FILE* pipe = popen(body, \"r\");  // DANGER: User input directly executed\n        if (pipe != NULL) {\n            size_t len = fread(output, 1, sizeof(output) - 1, pipe);\n            output[len] = '\\0';\n            pclose(pipe);\n            sprintf(response, \"HTTP/1.1 200 OK\\r\\n\\r\\n%s\", output);\n        }\n    }\n}\n```\n\nCette fonction recoit des requetes HTTP POST sur l'endpoint `/exec` et passe le body directement a `popen()` pour execution. Aucune validation n'est effectuee sur le contenu du body avant execution.",
      "why": "## Pourquoi c'est un probleme\n\nCette vulnerabilite est **critique** car elle permet l'execution de code arbitraire a distance (RCE - Remote Code Execution).\n\n### Scenario d'attaque\n\n```mermaid\nsequenceDiagram\n    participant Attacker\n    participant Server\n    participant System\n\n    Attacker->>Server: POST /exec\\nbody: rm -rf /\n    Server->>System: popen(\"rm -rf /\", \"r\")\n    System-->>Server: Commande executee\n    Server-->>Attacker: Output retourne\n    Note over System: Systeme compromis\n```\n\n### Impact\n\n| Risque | Probabilite | Impact |\n|--------|-------------|--------|\n| Execution de code arbitraire | Haute | Critique |\n| Exfiltration de donnees | Haute | Critique |\n| Compromission complete du systeme | Haute | Critique |\n| Installation de backdoor | Haute | Critique |\n\n### Reference\n\n- **CWE-78** : Improper Neutralization of Special Elements used in an OS Command",
      "how": "## Comment corriger\n\n### Solution recommandee\n\nSupprimer completement l'endpoint `/exec` ou implementer une whitelist stricte de commandes autorisees.\n\n```c\n// Option 1: Supprimer l'endpoint (RECOMMANDE)\n// Retirer tout le bloc else if (strcmp(path, \"/exec\") == 0)\n\n// Option 2: Whitelist stricte (si absolument necessaire)\nelse if (strcmp(path, \"/exec\") == 0) {\n    // Liste des commandes autorisees\n    static const char* allowed_commands[] = {\"date\", \"uptime\", \"hostname\", NULL};\n    \n    int allowed = 0;\n    for (int i = 0; allowed_commands[i] != NULL; i++) {\n        if (strcmp(body, allowed_commands[i]) == 0) {\n            allowed = 1;\n            break;\n        }\n    }\n    \n    if (!allowed) {\n        sprintf(response, \"HTTP/1.1 403 Forbidden\\r\\n\\r\\nCommand not allowed\");\n    } else {\n        // Execute only whitelisted command\n        FILE* pipe = popen(body, \"r\");\n        // ...\n    }\n}\n```\n\n### Processus de correction\n\n```mermaid\ngraph LR\n    A[Identifier endpoint] --> B[Evaluer necessite]\n    B --> C{Necessaire?}\n    C -->|Non| D[Supprimer]\n    C -->|Oui| E[Whitelist stricte]\n    E --> F[Tests de securite]\n    D --> F\n    F --> G[Code review]\n```\n\n### Validation\n\n1. Tester que l'endpoint est supprime ou retourne 403 pour commandes non autorisees\n2. Effectuer un test de penetration sur l'endpoint\n3. Verifier avec un scanner de vulnerabilites (OWASP ZAP, Burp Suite)\n\n### References\n\n- [CWE-78](https://cwe.mitre.org/data/definitions/78.html)\n- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)"
    },
    {
      "id": "SEC-002",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-78",
      "file": "src/shell/command.c",
      "line": 13,
      "function": "execute_command",
      "message": "Command Injection via system() - 8 functions pass user input to shell",
      "blocking": true,
      "time_estimate_min": 120,
      "propagation": 8
    },
    {
      "id": "SEC-003",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-798",
      "file": "src/config/config.c",
      "line": 12,
      "function": "global",
      "message": "10+ hardcoded credentials including passwords, API keys, and AWS secrets",
      "blocking": true,
      "time_estimate_min": 60
    },
    {
      "id": "SEC-004",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-89",
      "file": "src/config/config.c",
      "line": 62,
      "function": "config_load_from_db",
      "message": "SQL Injection via string concatenation in query",
      "blocking": true,
      "time_estimate_min": 15
    },
    {
      "id": "SEC-005",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-120",
      "file": "src/server/udp_server.c",
      "line": 96,
      "function": "udp_server_read_input",
      "message": "gets() usage causes buffer overflow crash",
      "blocking": true,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-006",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-120",
      "file": "src/server/udp_server.c",
      "line": 51,
      "function": "udp_server_process_request",
      "message": "15+ strcpy/sprintf without bounds checking cause buffer overflow",
      "blocking": true,
      "time_estimate_min": 120
    },
    {
      "id": "SEC-007",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-22",
      "file": "src/server/connection.c",
      "line": 90,
      "function": "handle_connection",
      "message": "Path traversal allows reading arbitrary files via /file/ endpoint",
      "blocking": true,
      "time_estimate_min": 30
    },
    {
      "id": "SEC-008",
      "source": ["security"],
      "severity": "Blocker",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-22",
      "file": "src/server/connection.c",
      "line": 147,
      "function": "handle_connection",
      "message": "Arbitrary file write via /upload endpoint",
      "blocking": true,
      "time_estimate_min": 15
    },
    {
      "id": "SEC-009",
      "source": ["security"],
      "severity": "Critical",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-798",
      "file": "src/server/connection.c",
      "line": 117,
      "function": "handle_connection",
      "message": "Hardcoded password bypass: user 'debug' with any password grants access",
      "blocking": true,
      "time_estimate_min": 10
    },
    {
      "id": "SEC-010",
      "source": ["security"],
      "severity": "Critical",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-416",
      "file": "src/server/udp_server.c",
      "line": 137,
      "function": "udp_server_cleanup",
      "message": "Use-after-free: memset on freed buffer causes crash",
      "blocking": true,
      "time_estimate_min": 10
    },
    {
      "id": "SEC-011",
      "source": ["security"],
      "severity": "Critical",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-134",
      "file": "src/server/udp_server.c",
      "line": 146,
      "function": "udp_server_log",
      "message": "Format string vulnerability: printf(message) allows memory writes",
      "blocking": true,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-012",
      "source": ["security"],
      "severity": "Critical",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-120",
      "file": "src/server/udp_server.c",
      "line": 152,
      "function": "udp_server_get_command",
      "message": "scanf without bounds check causes buffer overflow",
      "blocking": true,
      "time_estimate_min": 15
    },
    {
      "id": "SEC-013",
      "source": ["security"],
      "severity": "Critical",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-327",
      "file": "src/utils/crypto.c",
      "line": 15,
      "function": "crypto_encrypt",
      "message": "Weak cryptography: XOR encryption and rand() for randomness",
      "blocking": true,
      "time_estimate_min": 240
    },
    {
      "id": "SEC-014",
      "source": ["security"],
      "severity": "Major",
      "category": "Reliability",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-401",
      "file": "src/utils/memory.c",
      "line": 81,
      "function": "process_data_buffer",
      "message": "Memory leak: buffer1 and buffer2 never freed",
      "blocking": false,
      "time_estimate_min": 10
    },
    {
      "id": "SEC-015",
      "source": ["security"],
      "severity": "Major",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-476",
      "file": "src/utils/memory.c",
      "line": 122,
      "function": "alloc_zeroed",
      "message": "NULL pointer dereference: memset on potentially NULL ptr",
      "blocking": true,
      "time_estimate_min": 60
    },
    {
      "id": "SEC-016",
      "source": ["security"],
      "severity": "Major",
      "category": "Reliability",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-252",
      "file": "src/server/udp_server.c",
      "line": 91,
      "function": "udp_server_send_response",
      "message": "Return value of send() not checked",
      "blocking": false,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-017",
      "source": ["security"],
      "severity": "Major",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-193",
      "file": "src/utils/string_utils.c",
      "line": 134,
      "function": "str_build",
      "message": "Off-by-one error reads past array bounds",
      "blocking": true,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-018",
      "source": ["security"],
      "severity": "Major",
      "category": "Security",
      "isBug": true,
      "type": "vulnerability",
      "cwe": "CWE-122",
      "file": "src/utils/cache.c",
      "line": 88,
      "function": "cache_set",
      "message": "Heap buffer overflow: malloc(strlen) missing +1 for null terminator",
      "blocking": true,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-019",
      "source": ["security"],
      "severity": "Medium",
      "category": "Reliability",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-170",
      "file": "src/utils/string_utils.c",
      "line": 42,
      "function": "str_safe_copy",
      "message": "strncpy does not guarantee null termination",
      "blocking": false,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-020",
      "source": ["security"],
      "severity": "Medium",
      "category": "Reliability",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-401",
      "file": "src/utils/string_utils.c",
      "line": 117,
      "function": "str_process_complex",
      "message": "Memory leak: temp1 and temp2 never freed",
      "blocking": false,
      "time_estimate_min": 5
    },
    {
      "id": "SEC-021",
      "source": ["security"],
      "severity": "Medium",
      "category": "Reliability",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-401",
      "file": "src/utils/string_utils.c",
      "line": 153,
      "function": "str_tokenize_and_process",
      "message": "Memory leak: copy and tokens array never freed",
      "blocking": false,
      "time_estimate_min": 10
    },
    {
      "id": "SEC-022",
      "source": ["security"],
      "severity": "Medium",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-208",
      "file": "src/config/config.c",
      "line": 36,
      "function": "config_authenticate",
      "message": "Timing attack: strcmp allows password length guessing",
      "blocking": false,
      "time_estimate_min": 10
    },
    {
      "id": "SEC-023",
      "source": ["security"],
      "severity": "Minor",
      "category": "Security",
      "isBug": false,
      "type": "vulnerability",
      "cwe": "CWE-489",
      "file": "src/config/config.c",
      "line": 30,
      "function": "config_init",
      "message": "Debug mode enabled by default in production",
      "blocking": false,
      "time_estimate_min": 5
    }
  ],
  "bug_history_analyzed": 0,
  "patterns_checked": 6,
  "agentdb_queries": {
    "error_history": {"status": "error", "reason": "jq command not found"},
    "file_context": {"status": "error", "reason": "jq command not found"},
    "patterns": {"status": "error", "reason": "jq command not found"},
    "symbol_callers": {"status": "error", "reason": "jq command not found"},
    "list_critical_files": {"status": "error", "reason": "jq command not found"}
  }
}
```
