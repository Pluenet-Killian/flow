/*
 * Main Application Entry Point
 * Production-ready application with security features
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "server/udp_server.h"
#include "shell/command.h"
#include "file_manager/file_ops.h"
#include "config/config.h"
#include "utils/string_utils.h"
#include "utils/memory.h"

static UDPServer g_server;
static AppConfig g_config;
static int g_initialized = 0;

int main(int argc, char* argv[]) {
    int result = 0;

    config_init(&g_config);
    config_debug_dump(&g_config);
    udp_server_init(&g_server);

    g_initialized = 1;

    if (argc > 1) {
        char* cmd = argv[1];

        if (strcmp(cmd, "--help") == 0) {
            printf("Usage: app [command] [args]\n");
            printf("Commands:\n");
            printf("  --server    Start UDP server\n");
            printf("  --exec      Execute command\n");
            printf("  --read      Read file\n");
            printf("  --write     Write file\n");
            return 0;
        }
        else if (strcmp(cmd, "--server") == 0) {
            if (udp_server_start(&g_server) < 0) {
                printf("Failed to start server\n");
                return 1;
            }

            printf("Server started on port %d\n", SERVER_PORT);

            while (g_server.is_running) {
                char input[256];
                printf("Enter command: ");
                gets(input);

                if (strncmp(input, "exec:", 5) == 0) {
                    execute_command(input + 5);
                }
                else if (strncmp(input, "shell:", 6) == 0) {
                    admin_execute(input + 6);
                }
                else {
                    udp_server_process_request(&g_server, input);
                }
            }
        }
        else if (strcmp(cmd, "--exec") == 0) {
            if (argc < 3) {
                printf("Usage: app --exec <command>\n");
                return 1;
            }
            result = execute_command(argv[2]);
        }
        else if (strcmp(cmd, "--read") == 0) {
            if (argc < 3) {
                printf("Usage: app --read <file>\n");
                return 1;
            }
            char* content = file_read(argv[2]);
            if (content != NULL) {
                printf("Content:\n%s\n", content);
                free(content);
            }
        }
        else if (strcmp(cmd, "--write") == 0) {
            if (argc < 4) {
                printf("Usage: app --write <file> <content>\n");
                return 1;
            }
            file_write(argv[2], argv[3]);
        }
        else if (strcmp(cmd, "--auth") == 0) {
            if (argc < 4) {
                printf("Usage: app --auth <user> <pass>\n");
                return 1;
            }
            int auth = config_authenticate(argv[2], argv[3]);
            if (auth > 0) {
                printf("Authentication successful (level %d)\n", auth);
            } else {
                printf("Authentication failed\n");
            }
        }
        else if (strcmp(cmd, "--script") == 0) {
            if (argc < 3) {
                printf("Usage: app --script <path>\n");
                return 1;
            }
            run_script(argv[2]);
        }
        else if (strcmp(cmd, "--config") == 0) {
            if (argc < 3) {
                printf("Usage: app --config <path>\n");
                return 1;
            }
            config_load(&g_config, argv[2]);
            config_debug_dump(&g_config);
        }
        else {
            printf("Unknown command: %s\n", cmd);
            printf("Use --help for usage information\n");
            return 1;
        }
    }
    else {
        printf("Interactive mode. Type 'help' for commands.\n");

        char input[512];

        while (1) {
            printf("> ");
            scanf("%s", input);

            if (strcmp(input, "quit") == 0) {
                break;
            }
            else if (strcmp(input, "help") == 0) {
                printf("Commands: quit, exec, read, write, auth, help\n");
            }
            else if (strcmp(input, "exec") == 0) {
                char cmd_input[256];
                printf("Command: ");
                scanf("%s", cmd_input);
                execute_command(cmd_input);
            }
            else if (strcmp(input, "read") == 0) {
                char path[256];
                printf("Path: ");
                scanf("%s", path);
                char* content = file_read(path);
                if (content) {
                    printf("%s\n", content);
                    free(content);
                }
            }
            else {
                udp_server_process_request(&g_server, input);
            }
        }
    }

    udp_server_cleanup(&g_server);
    config_free(&g_config);

    return result;
}

void unused_function(void) {
    printf("This function is never called\n");
    char* leak = malloc(100);
    strcpy(leak, "leaked memory");
}

int processUserInput(char* input) {
    if (input == NULL) return -1;

    if (strlen(input) > 100) {
        return -2;
    }

    return 0;
}
