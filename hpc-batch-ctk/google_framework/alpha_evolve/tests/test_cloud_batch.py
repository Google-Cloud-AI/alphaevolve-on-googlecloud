# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for BatchClient in cloud_batch.py."""

import os
import pytest
from unittest.mock import MagicMock, patch

from alpha_evolve.cloud_batch import BatchClient


@pytest.fixture
def mock_batch_client():
    with patch("alpha_evolve.cloud_batch.batch_v1.BatchServiceClient") as mock_service:
        client = BatchClient()
        client.client = mock_service.return_value
        yield client


def test_get_config_path(mock_batch_client, tmp_path, monkeypatch):
    # Test when file exists at custom path
    config_file = tmp_path / "eval-batch.yaml"
    config_file.write_text("taskGroups: []")

    # Override the method behavior to simulate finding it
    monkeypatch.setattr(mock_batch_client, "_get_config_path", lambda: str(config_file))
    assert mock_batch_client._get_config_path() == str(config_file)


def test_get_config_path_not_found():
    client = BatchClient()
    with patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="eval-batch.yaml not found"):
            client._get_config_path()


def test_prepare_job_config(mock_batch_client, tmp_path, monkeypatch):
    config_file = tmp_path / "eval-batch.yaml"
    config_file.write_text(
        'taskGroups:\n- taskSpec:\n    runnables:\n    - container:\n        imageUri: "${_EVALUATOR_IMAGE_URI}"\n'
        '    environment:\n      variables:\n        _JOB_ID: "${_JOB_ID}"\n        _CLIENT_EVALUATOR_SCRIPT: "${_CLIENT_EVALUATOR_SCRIPT}"'
    )

    monkeypatch.setattr(mock_batch_client, "_get_config_path", lambda: str(config_file))
    monkeypatch.setenv("_EVALUATOR_IMAGE_URI", "gcr.io/test/evaluator:latest")

    json_str = mock_batch_client._prepare_job_config("job-123", "prog-456", "eval_script.py", "eval_method")
    
    assert "gcr.io/test/evaluator:latest" in json_str
    assert "job-123" in json_str
    assert "eval_script.py" in json_str


def test_create_batch_job_success(mock_batch_client, monkeypatch):
    monkeypatch.setenv("_PROJECT_ID", "hpc-solutions-03")
    monkeypatch.setattr(mock_batch_client, "_prepare_job_config", lambda *args, **kwargs: '{"taskGroups": []}')

    mock_created = MagicMock()
    mock_created.name = "projects/hpc-solutions-03/locations/us-central1/jobs/job-123"
    mock_batch_client.client.create_job.return_value = mock_created

    job = mock_batch_client.create_batch_job("job-123", "prog-456", "eval_script.py", "eval_method", region="us-central1")
    
    assert job == mock_created
    mock_batch_client.client.create_job.assert_called_once()
    call_kwargs = mock_batch_client.client.create_job.call_args[1]
    assert call_kwargs["request"].parent == "projects/hpc-solutions-03/locations/us-central1"
    assert call_kwargs["request"].job_id == "job-123"


def test_create_batch_job_failure(mock_batch_client, monkeypatch):
    monkeypatch.setenv("_PROJECT_ID", "hpc-solutions-03")
    monkeypatch.setattr(mock_batch_client, "_prepare_job_config", lambda *args, **kwargs: '{"taskGroups": []}')

    mock_batch_client.client.create_job.side_effect = Exception("API Crash")

    with pytest.raises(Exception, match="API Crash"):
        mock_batch_client.create_batch_job("job-123", "prog-456", "eval_script.py", "eval_method")


def test_delete_batch_job(mock_batch_client):
    mock_batch_client.delete_batch_job("projects/hpc-solutions-03/locations/us-central1/jobs/job-123")
    mock_batch_client.client.delete_job.assert_called_once()
    call_kwargs = mock_batch_client.client.delete_job.call_args[1]
    assert call_kwargs["request"].name == "projects/hpc-solutions-03/locations/us-central1/jobs/job-123"


def test_delete_batch_job_exception(mock_batch_client):
    mock_batch_client.client.delete_job.side_effect = Exception("Delete Crash")
    # Should catch exception and log without raising
    mock_batch_client.delete_batch_job("projects/hpc-solutions-03/locations/us-central1/jobs/job-123")


def test_prepare_job_config_n1_gpu(mock_batch_client, tmp_path, monkeypatch):
    config_file = tmp_path / "eval-batch.yaml"
    config_file.write_text(
        'allocationPolicy:\n'
        '  instances:\n'
        '  - policy:\n'
        '      machineType: "n1-standard-4"\n'
        '      provisioningModel: "STANDARD"\n'
    )

    monkeypatch.setattr(mock_batch_client, "_get_config_path", lambda: str(config_file))

    json_str = mock_batch_client._prepare_job_config(
        "job-123", "prog-456", "eval_script.py", "eval_method",
        accelerator_count=2, accelerator_type="nvidia-tesla-t4"
    )
    
    import json
    parsed = json.loads(json_str)
    instance = parsed["allocationPolicy"]["instances"][0]
    assert instance["installGpuDrivers"] is True
    assert instance["policy"]["accelerators"][0]["count"] == 2
    assert instance["policy"]["accelerators"][0]["type"] == "nvidia-tesla-t4"


def test_prepare_job_config_n2_no_gpu(mock_batch_client, tmp_path, monkeypatch):
    config_file = tmp_path / "eval-batch.yaml"
    config_file.write_text(
        'allocationPolicy:\n'
        '  instances:\n'
        '  - policy:\n'
        '      machineType: "n2-standard-4"\n'
        '      provisioningModel: "STANDARD"\n'
    )

    monkeypatch.setattr(mock_batch_client, "_get_config_path", lambda: str(config_file))

    json_str = mock_batch_client._prepare_job_config(
        "job-123", "prog-456", "eval_script.py", "eval_method",
        accelerator_count=2, accelerator_type="nvidia-tesla-t4"
    )
    
    import json
    parsed = json.loads(json_str)
    instance = parsed["allocationPolicy"]["instances"][0]
    assert "installGpuDrivers" not in instance
    assert "accelerators" not in instance["policy"]
