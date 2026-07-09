# Configurable base image passed from Cloud Build (default: ubuntu:24.04)
ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install dependencies: build-essential, OpenMPI, OpenSSH services, Python
RUN apt-get update && apt-get install -y \
    build-essential \
    openmpi-bin \
    libopenmpi-dev \
    openssh-server \
    openssh-client \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Configure passwordless SSH daemon (required for permissiveSsh: true)
RUN mkdir /var/run/sshd \
    && mkdir -p /root/.ssh \
    && ssh-keygen -t rsa -f /root/.ssh/id_rsa -N "" \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys \
    && echo "Host *\n\tStrictHostKeyChecking no\n\tUserKnownHostsFile /dev/null" > /root/.ssh/config

# Copy and install core platform requirements with secure hash verification
COPY infrastructure/requirements.txt /app/requirements.txt
RUN python3 -m pip install --break-system-packages --ignore-installed --no-cache-dir --require-hashes -r /app/requirements.txt

# Set workdir and copy AlphaEvolve base packages
WORKDIR /app/src/alpha_evolve
COPY google_framework/alpha_evolve /app/src/alpha_evolve

# Copy the experiment code
COPY user_examples/nbody_molecular_dynamics/ /app/experiment/
RUN chmod +x /app/experiment/run-ssh.sh

# Set the entrypoint using bash
ENTRYPOINT ["/bin/bash", "-c", "\
    echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
    mkdir -p $_MOUNT_PATH/logs && \
    if [ -f \"/app/experiment/Makefile\" ]; then \
      echo \"[BATCH DEBUG] Found Makefile under directory: /app/experiment\"; \
      echo \"[BATCH DEBUG] Copying generated C++ code from $_CANDIDATE_DIR to /app/experiment...\"; \
      cp -r $_CANDIDATE_DIR/* /app/experiment/ 2>/dev/null || true; \
      echo \"[BATCH DEBUG] Generating evaluation script...\" && \
      make -C /app/experiment evaluator.sh || exit 1; \
      echo \"[BATCH DEBUG] Build finished.\"; \
    else \
      echo \"[BATCH DEBUG] INFO: No Makefile found, skipping build.\"; \
      exit 0; \
    fi && \
    echo \"[BATCH DEBUG] Running evaluator...\" && \
    bash /app/experiment/evaluator.sh \
"]
