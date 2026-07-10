# Makefile for building the packing shared library

# Compiler
CXX = g++

# Compiler flags
CXXFLAGS = -std=c++11 -fPIC -O2 -Wall

# Linker flags
LDFLAGS = -shared

# Source file
SRCS = libpacking.cpp

# Object file
OBJS = $(SRCS:.cpp=.o)

# Target shared library
TARGET = libpacking.so

# Default target
all: $(TARGET) evaluator.sh

# Rule to build the shared library
$(TARGET): $(OBJS)
	$(CXX) $(LDFLAGS) -o $@ $^

# Rule to compile C++ source files into object files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean target to remove generated files
clean:
	rm -f $(OBJS) $(TARGET)

# Phony targets
.PHONY: all clean

# Evaluator shell
# User specific evaluator script
# Create_evaluator.sh that runs the evaluator
evaluator.sh:
	echo "#!/bin/bash" > evaluator.sh
	echo "cd /app/experiment" >> evaluator.sh
	echo "mkdir -p \$$_MOUNT_PATH/\$$_USER_EXPERIMENT_NAME/logs" >> evaluator.sh
	echo 'python3 /app/src/alpha_evolve/cloud_evaluator.py 2>&1 | tee $$_MOUNT_PATH/$$_USER_EXPERIMENT_NAME/logs/evaluator_$$_CANDIDATE_PROGRAM_ID.log' >> evaluator.sh
	chmod +x evaluator.sh

