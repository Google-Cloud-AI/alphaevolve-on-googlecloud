ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

# Set environment variables to avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install build tools for compiling dependencies (gcc, g++, make, cmake, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

ARG CLOUD_BUCKET_NAME
ARG PROJECT_ID
ARG MOUNT_PATH="/mnt/disks/share"

# Environment variables
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

# Copy and install base requirements first for caching
COPY infrastructure/requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir --require-hashes -r /app/requirements.txt

# Copy and install experiment-specific requirements
COPY user_examples/signal_processing/requirements.txt /app/experiment/requirements.txt
RUN python3 -m pip install --no-cache-dir --require-hashes -r /app/experiment/requirements.txt

# Copy the shared source code
COPY google_framework/alpha_evolve /app/src/alpha_evolve
# Copy the experiment code
COPY user_examples/signal_processing/ /app/experiment/

WORKDIR /app/src/alpha_evolve

ENTRYPOINT ["/bin/bash", "-c", "\
    echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
    mkdir -p $_MOUNT_PATH/logs && \
    if [ -f \"/app/experiment/Makefile\" ]; then \
      echo \"[BATCH DEBUG] Found Makefile under directory: /app/experiment\"; \
      echo \"[BATCH DEBUG] Copying generated code from $_CANDIDATE_DIR to /app/experiment...\" && \
      cp -r $_CANDIDATE_DIR/* /app/experiment/ 2>/dev/null || true && \
      echo \"[BATCH DEBUG] Building Make library from /app/experiment...\" && \
      make -C /app/experiment all || exit 1; \
      echo \"[BATCH DEBUG] Build finished.\"; \
    else \
      echo \"[BATCH DEBUG] INFO: No Makefile found, skipping build.\"; \
      exit 0; \
    fi && \
    echo \"[BATCH DEBUG] Running evaluator...\" && \
    bash /app/experiment/evaluator.sh \
"]

