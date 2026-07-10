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

"""Unit tests for cloud_evaluator.py."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

import alpha_evolve.cloud_evaluator as cloud_evaluator


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setattr(cloud_evaluator, "PROJECT_ID", "test-project")
    monkeypatch.setattr(cloud_evaluator, "JOB_ID", "job-123")
    monkeypatch.setattr(cloud_evaluator, "CANDIDATE_PROGRAM_ID", "prog-456")
    monkeypatch.setattr(cloud_evaluator, "PROGRAMS_DIR", "evals")
    monkeypatch.setattr(cloud_evaluator, "MOUNT_PATH", "/mnt/disks/share")
    monkeypatch.setattr(cloud_evaluator, "USER_EXPERIMENT_NAME", "test-exp")


def test_run_worker_missing_project(monkeypatch):
    monkeypatch.setattr(cloud_evaluator, "PROJECT_ID", "")
    # Should exit early without doing anything
    cloud_evaluator.run_worker(lambda: {})


def test_run_worker_dummy_project(monkeypatch):
    monkeypatch.setattr(cloud_evaluator, "PROJECT_ID", "your-gcp-project-id")
    # Should exit early
    cloud_evaluator.run_worker(lambda: {})


def test_run_worker_success(mock_env, tmp_path, monkeypatch):
    # Override MOUNT_PATH to use tmp_path
    monkeypatch.setattr(cloud_evaluator, "MOUNT_PATH", str(tmp_path))
    
    # Create the expected directory structure
    prog_dir = tmp_path / "test-exp" / "evals" / "job-123"
    prog_dir.mkdir(parents=True, exist_ok=True)
    
    candidate_file = prog_dir / "program_candidate_data.json"
    candidate_file.write_text(json.dumps({"name": "prog/1", "lockToken": "abc"}))

    dummy_eval = lambda: {"scores": {"scores": [{"metric": "score", "score": 0.99}]}}

    cloud_evaluator.run_worker(dummy_eval)

    result_file = prog_dir / "program_candidate_result.json"
    assert result_file.exists()
    res_data = json.loads(result_file.read_text())
    assert res_data["name"] == "prog/1"
    assert res_data["lockToken"] == "abc"
    assert "scores" in res_data["evaluation"]


def test_run_worker_evaluator_exception(mock_env, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_evaluator, "MOUNT_PATH", str(tmp_path))
    prog_dir = tmp_path / "test-exp" / "evals" / "job-123"
    prog_dir.mkdir(parents=True, exist_ok=True)
    candidate_file = prog_dir / "program_candidate_data.json"
    candidate_file.write_text(json.dumps({"name": "prog/1", "lockToken": "abc"}))

    def bad_eval():
        raise ValueError("Crash")

    cloud_evaluator.run_worker(bad_eval)

    result_file = prog_dir / "program_candidate_result.json"
    assert not result_file.exists()


def test_run_worker_missing_candidate_file(mock_env, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_evaluator, "MOUNT_PATH", str(tmp_path))
    # Do not create candidate file
    cloud_evaluator.run_worker(lambda: {})
