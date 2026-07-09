# Makefile for the airfoil_optimization experiment.
# Since we do not compile C++ code, this Makefile only generates the evaluator.sh wrapper
# required by the AlphaEvolve Cloud Batch execution harness.

# Default target
all: evaluator.sh

# Evaluator shell script generation
evaluator.sh:
	echo "#!/bin/bash" > evaluator.sh
	echo "export FOAM_RUN_AS_ROOT=1" >> evaluator.sh
	echo "source /usr/lib/openfoam/openfoam2406/etc/bashrc" >> evaluator.sh
	echo "cd /app/experiment" >> evaluator.sh
	# Execute the AlphaEvolve cloud evaluator python runtime and pipe logs to GCS mount path
	echo "mkdir -p \$$_MOUNT_PATH/\$$_USER_EXPERIMENT_NAME/logs" >> evaluator.sh
	echo 'python3 /app/src/alpha_evolve/cloud_evaluator.py 2>&1 | tee $$_MOUNT_PATH/$$_USER_EXPERIMENT_NAME/logs/evaluator_$$_CANDIDATE_PROGRAM_ID.log' >> evaluator.sh
	chmod +x evaluator.sh

clean:
	rm -f evaluator.sh

.PHONY: all clean
