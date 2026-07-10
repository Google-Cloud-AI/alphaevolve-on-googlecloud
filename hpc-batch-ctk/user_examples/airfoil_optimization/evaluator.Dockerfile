# Custom Evaluator Dockerfile using OpenFOAM 2406 as the base image
# This ensures the Cloud Batch worker VMs have OpenFOAM pre-installed and fully functional.

ARG BASE_IMAGE=opencfd/openfoam-run:2406
FROM ${BASE_IMAGE}

# Switch to root to install system dependencies and Python libraries
USER root

# Set environment variables to avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Python, Pip, Make, and Git
RUN apt-get update && apt-get install -y \
    python3-pip \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

# We use the system-provided setuptools and wheel directly to avoid Debian uninstall issues.

ARG CLOUD_BUCKET_NAME
ARG PROJECT_ID
ARG MOUNT_PATH="/mnt/disks/share"

# Environment variables required by the AlphaEvolve Batch Harness
ENV _CLOUD_BUCKET_NAME=${CLOUD_BUCKET_NAME}
ENV _PROJECT_ID=${PROJECT_ID}
ENV _JOB_ID=""
ENV _CANDIDATE_PROGRAM_ID=""
ENV _MOUNT_PATH=${MOUNT_PATH}
ENV _PROGRAMS_DIR=""
ENV _CLIENT_EVALUATOR_SCRIPT=""
ENV _CLIENT_EVALUATOR_METHOD=""
ENV _CANDIDATE_DIR=""

# Set the working directory
WORKDIR /app

# Copy the core AlphaEvolve requirements file from the build context
COPY infrastructure/requirements.txt .

# Install AlphaEvolve core dependencies with security hashes enabled
RUN python3 -m pip install --no-cache-dir --require-hashes -r requirements.txt --break-system-packages

# Copy the shared core source code of AlphaEvolve
COPY google_framework/alpha_evolve /app/src/alpha_evolve

COPY user_examples/airfoil_optimization/ /app/experiment/

WORKDIR /app/src/alpha_evolve

# Set the entrypoint to handle task setup, candidate copying, and execution
ENTRYPOINT ["/bin/bash", "-c", "\
    echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
    mkdir -p $_MOUNT_PATH/logs && \
    if [ -f \"/app/experiment/Makefile\" ]; then \
      echo \"[BATCH DEBUG] Found Makefile under directory: /app/experiment\"; \
      echo \"[BATCH DEBUG] Copying generated code from $_CANDIDATE_DIR to /app/experiment...\" && \
      cp -r $_CANDIDATE_DIR/* /app/experiment/ 2>/dev/null || true && \
      echo \"[BATCH DEBUG] Generating evaluator.sh via Makefile...\" && \
      make -C /app/experiment all || exit 1; \
      echo \"[BATCH DEBUG] Build finished.\"; \
    else \
      echo \"[BATCH DEBUG] ERROR: No Makefile found, exiting.\"; \
      exit 1; \
    fi && \
    echo \"[BATCH DEBUG] Running evaluator...\" && \
    bash /app/experiment/evaluator.sh \
"]
