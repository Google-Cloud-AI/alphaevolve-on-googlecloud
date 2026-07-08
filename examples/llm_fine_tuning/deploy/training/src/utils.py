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
"""GCS I/O and GPU logging utilities."""

import json
import logging

import torch
from google.cloud import storage

logger = logging.getLogger(__name__)


def log_gpu_info(prefix: str = ""):
    """Log GPU memory usage."""
    if torch.cuda.is_available():
        alloc_gb = torch.cuda.memory_allocated() / 1024**3
        reserved_gb = torch.cuda.memory_reserved() / 1024**3
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        logger.info(
            f"{prefix}GPU memory — "
            f"allocated: {alloc_gb:.1f}GB, "
            f"reserved: {reserved_gb:.1f}GB, "
            f"total: {total_gb:.1f}GB"
        )


def read_input(bucket_name: str, job_id: str) -> dict:
    """Read job input from GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"jobs/{job_id}/input.json")
    data = json.loads(blob.download_as_text())
    logger.info(f"Input read from gs://{bucket_name}/jobs/{job_id}/input.json")
    return data


def write_output(bucket_name: str, job_id: str, data: dict):
    """Write job output to GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"jobs/{job_id}/output.json")
    blob.upload_from_string(
        json.dumps(data), content_type="application/json"
    )
    logger.info(
        f"Output written to gs://{bucket_name}/jobs/{job_id}/output.json"
    )
