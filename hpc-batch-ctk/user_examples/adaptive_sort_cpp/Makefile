CC=g++
CFLAGS=-std=c++11 -O2 -Wall

all: benchmark evaluator.sh

benchmark: src/main.cpp src/benchmark.cpp
	$(CC) $(CFLAGS) src/main.cpp src/benchmark.cpp -o benchmark

clean:
	rm -f benchmark evaluator.sh

evaluator.sh:
	echo "#!/bin/bash" > evaluator.sh
	echo "cd /app/experiment" >> evaluator.sh
	echo "mkdir -p \$$_MOUNT_PATH/\$$_USER_EXPERIMENT_NAME/logs" >> evaluator.sh
	echo 'python3 /app/src/alpha_evolve/cloud_evaluator.py 2>&1 | tee $$_MOUNT_PATH/$$_USER_EXPERIMENT_NAME/logs/evaluator_$$_CANDIDATE_PROGRAM_ID.log' >> evaluator.sh
	chmod +x evaluator.sh

