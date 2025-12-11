# Makefile for Test C Project
# This project contains intentional vulnerabilities for testing analysis tools

CC = gcc
# BUG: Disabled most warnings - bad practice
CFLAGS = -Wall -g
# Should have: -Wextra -Werror -pedantic -Wformat-security

# BUG: No sanitizer flags for development
# Should add: -fsanitize=address,undefined for debug builds

SRC_DIR = .
BUILD_DIR = build

# Source files
SRCS = main.c \
       server/udp_server.c \
       shell/command.c \
       file_manager/file_ops.c \
       config/config.c \
       utils/string_utils.c \
       utils/memory.c

OBJS = $(SRCS:%.c=$(BUILD_DIR)/%.o)
TARGET = $(BUILD_DIR)/app

# BUG: Default target doesn't create build directory first
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

# BUG: Clean doesn't handle errors
clean:
	rm -rf $(BUILD_DIR)

# BUG: No proper dependency tracking
# Headers changes won't trigger recompilation

# BUG: No install target
# BUG: No test target
# BUG: No static analysis target (should have scan-build, cppcheck)

.PHONY: all clean

# Debug build - BUG: Same as release, no difference
debug: CFLAGS += -DDEBUG
debug: all

# BUG: No release target with optimizations
# Should have: release: CFLAGS += -O2 -DNDEBUG
