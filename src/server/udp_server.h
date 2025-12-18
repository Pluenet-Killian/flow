#ifndef UDP_SERVER_H
#define UDP_SERVER_H

#include <stddef.h>

#define SERVER_PORT 8080
#define MAX_CLIENTS 100

typedef struct {
    int socket_fd;
    char* buffer;
    size_t buffer_size;
    int is_running;
} UDPServer;

// Initialize the UDP server
int udp_server_init(UDPServer* server);

// Start listening for connections
int udp_server_start(UDPServer* server);

// Process incoming request
int udp_server_process_request(UDPServer* server, const char* client_data);

// Send response to client
void udp_server_send_response(int socket, const char* data);

// Handle multiple requests in batch
void udp_server_process_batch(UDPServer* server, char** requests, int count);

// Cleanup server resources
void udp_server_cleanup(UDPServer* server);

#endif // UDP_SERVER_H
