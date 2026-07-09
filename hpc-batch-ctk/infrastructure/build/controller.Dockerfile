# Use a lightweight base image
ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

# Arguments for the experiment configuration
ARG CLOUD_BUCKET_NAME
ARG PUBSUB_TOPIC
ARG PUBSUB_SUBSCRIPTION
ARG PROJECT_ID
ARG LOCATION=global
ARG COLLECTION=default_collection
ARG ENGINE=alpha-evolve-infra-experiment-engine
ARG ASSISTANT=default_assistant
ARG BASE_URL=discoveryengine.googleapis.com
ARG MODEL=MODEL_UNSPECIFIED
ARG REGION_CODE=global
ARG MAX_PROGRAMS_GENERATED=10
ARG CONCURRENCY=4
ARG MAX_PROGRAMS_EVALUATED=10
ARG EVALUATION_MODE=batch
ARG NUM_SAMPLERS=4
ARG POLL_INTERVAL=4
ARG PROGRAMS_DIR="programs_candidate"
ARG DELETE_SUCCEEDED_JOBS="true"
ARG MAX_DURATION=6
ARG IDLE_TIMEOUT=5
ARG MAX_DURATION_SECONDS=3600
ARG MOUNT_PATH="/mnt/disks/share"
ARG REGION
ARG REPO_NAME
ARG EVALUATION_MACHINE_TYPE
ARG EVALUATION_PROVISIONING_MODEL # STANDARD or SPOT
ARG BOOT_DISK_IMAGE
ARG SERVICE_ACCOUNT_EMAIL
ARG EXAMPLE_DIR
ARG USER_EXPERIMENT_NAME
# Only used for N1 machine types
ARG ACCELERATOR_COUNT
ARG ACCELERATOR_TYPE

# Set the environment variables for GCS Bucket
ENV _CLOUD_BUCKET_NAME=${CLOUD_BUCKET_NAME}
# Set the environment variables for Pub/Sub
ENV _PUBSUB_TOPIC=${PUBSUB_TOPIC}
ENV _PUBSUB_SUBSCRIPTION=${PUBSUB_SUBSCRIPTION}
# Set the environment variables for AlphaEvolve
ENV _PROJECT_ID=${PROJECT_ID}
ENV _LOCATION=${LOCATION}
ENV _COLLECTION=${COLLECTION}
ENV _ENGINE=${ENGINE}
ENV _ASSISTANT=${ASSISTANT}
ENV _BASE_URL=${BASE_URL}
ENV _MODEL=${MODEL}
ENV _REGION_CODE=${REGION_CODE}
ENV _MAX_PROGRAMS_GENERATED=${MAX_PROGRAMS_GENERATED}
ENV _CONCURRENCY=${CONCURRENCY}
ENV _MAX_PROGRAMS_EVALUATED=${MAX_PROGRAMS_EVALUATED}
# Set the experiment configuration
ENV _EVALUATION_MODE=${EVALUATION_MODE}
ENV _NUM_SAMPLERS=${NUM_SAMPLERS}
ENV _POLL_INTERVAL=${POLL_INTERVAL}
# Specify where program files are located on the disk or in the GCS bucket
ENV _PROGRAMS_DIR=${PROGRAMS_DIR}
ENV _DELETE_SUCCEEDED_JOBS=${DELETE_SUCCEEDED_JOBS}
ENV _MAX_DURATION=${MAX_DURATION}
ENV _IDLE_TIMEOUT=${IDLE_TIMEOUT}
# Only needed for batch mode
ENV _MAX_DURATION_SECONDS=${MAX_DURATION_SECONDS}
# Only needed for batch mode
ENV _MOUNT_PATH=${MOUNT_PATH}
# Only needed for batch mode
ENV _REGION=${REGION}
ENV _REPO_NAME=${REPO_NAME}
ENV _EVALUATION_MACHINE_TYPE=${EVALUATION_MACHINE_TYPE}
ENV _EVALUATION_PROVISIONING_MODEL=${EVALUATION_PROVISIONING_MODEL}

ENV _BOOT_DISK_IMAGE=${BOOT_DISK_IMAGE}
ENV _SERVICE_ACCOUNT_EMAIL=${SERVICE_ACCOUNT_EMAIL}
ENV _USER_EXPERIMENT_NAME=${USER_EXPERIMENT_NAME}
ENV _ACCELERATOR_COUNT=${ACCELERATOR_COUNT}
ENV _ACCELERATOR_TYPE=${ACCELERATOR_TYPE}

# Set the working directory
WORKDIR /app

# Install build tools and python3-venv
RUN apt-get update && apt-get install -y make g++ python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

# Create virtual environment and add to PATH
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the shared source code
COPY google_framework/alpha_evolve /app/src/alpha_evolve

# Copy the experiment code
COPY ${EXAMPLE_DIR} /app/experiment/


# Copy the batch-job template orchestrator manifest
COPY infrastructure/batch_configs/eval-batch.yaml /app/eval-batch.yaml

# Copy the requirements file from the build context
COPY infrastructure/requirements.txt .

# Install dependencies
RUN python3 -m pip install --no-cache-dir --require-hashes -r requirements.txt

# Set the working directory
WORKDIR /app/experiment

# Add execution permissions to the entrypoint script
RUN chmod +x /app/experiment/run_experiment.py

# Set the entrypoint
ENTRYPOINT ["python3", "/app/experiment/run_experiment.py"]

