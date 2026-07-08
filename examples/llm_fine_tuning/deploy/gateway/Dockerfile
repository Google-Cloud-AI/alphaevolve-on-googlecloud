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

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8080

# Use gunicorn for concurrent request handling. Each training evaluation
# blocks for 5-10 minutes, so we need multiple workers/threads to handle
# parallel requests from AlphaEvolve.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--threads", "8", "--timeout", "1200", "main:app"]
