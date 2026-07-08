# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Pre-cache Rust dependencies
COPY Cargo.toml .
# Create dummy src/main.rs to build dependencies
RUN mkdir src && \
    echo 'fn main() { println!("Hello"); }' > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Copy function code
COPY main.py .

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Run with functions-framework
CMD ["functions-framework", "--target=evaluate_rust_sort", "--port=8080"]
