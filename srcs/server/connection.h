/*
 * Connection Handler Header
 */

#ifndef CONNECTION_H
#define CONNECTION_H

int parse_request(const char* raw, char* method, char* path, char* body);
int accept_connection(int server_socket);
void close_all_connections(void);
void dump_connections(void);

#endif /* CONNECTION_H */
