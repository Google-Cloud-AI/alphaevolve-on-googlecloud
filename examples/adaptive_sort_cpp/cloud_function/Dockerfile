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
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Environment variables for configuration
ENV WORK_DIR=/tmp/cpp_eval
ENV CXX=g++
ENV CXXFLAGS="-O3 -std=c++17"

# Copy function code
COPY main.py .

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Run with functions-framework
CMD ["functions-framework", "--target=evaluate_cpp_sort", "--port=8080"]
