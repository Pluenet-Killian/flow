#ifndef COMMAND_H
#define COMMAND_H

// Execute a shell command
int execute_command(const char* cmd);

// Execute command with arguments
int execute_with_args(const char* cmd, const char* args);

// Run a script file
int run_script(const char* script_path);

// Admin command executor
int admin_execute(const char* user_input);

// Debug console
void debug_exec(const char* debug_cmd);

#endif // COMMAND_H
