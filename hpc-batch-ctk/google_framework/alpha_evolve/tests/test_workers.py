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

"""Unit tests for SamplingWorker, EvaluationWorker, and ResultsListener."""

import asyncio
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from alpha_evolve.workers import SamplingWorker, ResultsListener
from alpha_evolve.experiment import AlphaEvolveExperiment


@pytest.fixture
def mock_experiment():
    exp = MagicMock()
    exp.experiment_name = "exp/123"
    exp.client = MagicMock()
    exp.stats = {"num_programs_generated": 0, "num_programs_evaluated": 0}
    exp.metrics_list = ["score"]
    return exp


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.dispatch = MagicMock(return_value=asyncio.Future())
    engine.dispatch.return_value.set_result(None)
    return engine


@pytest.mark.asyncio
async def test_sampling_worker_run(mock_experiment, mock_engine):
    mock_experiment.acquire_programs.side_effect = [
        {"programs": [{"name": "prog/1", "lockToken": "abc"}]},
        None,
    ]

    worker = SamplingWorker(mock_experiment, mock_engine, poll_interval=0.01)

    # Run worker in a task and cancel it after a short delay
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert mock_experiment.stats["num_programs_generated"] == 1
    mock_engine.dispatch.assert_called_once()


@patch("alpha_evolve.workers.read_file_from_gcs")
@patch("alpha_evolve.workers.archive_full_program_dir_gcs")
def test_results_listener_succeeded(mock_archive, mock_read, mock_experiment):
    mock_sub = MagicMock()
    mock_batch = MagicMock()
    listener = ResultsListener(mock_experiment, mock_sub, "sub/path", "bucket", "evals", mock_batch, "test-exp")

    # Mock Pub/Sub message
    mock_msg = MagicMock()
    mock_msg.attributes = {"NewJobState": "SUCCEEDED", "JobName": "jobs/job-123"}

    # Mock GCS result reading
    mock_read.return_value = {
        "name": "exp/123/prog/1",
        "lockToken": "abc",
        "evaluation": {"scores": {"scores": [{"metric": "score", "score": 0.95}]}},
        "eval_time": 2.5,
    }

    listener.callback(mock_msg)

    mock_msg.ack.assert_called_once()
    mock_experiment.submit_program_evaluations.assert_called_once()
    mock_archive.assert_called_once()


@patch("alpha_evolve.workers.read_file_from_gcs")
@patch("alpha_evolve.workers.archive_full_program_dir_gcs")
def test_results_listener_failed_job(mock_archive, mock_read, mock_experiment):
    mock_sub = MagicMock()
    mock_batch = MagicMock()
    listener = ResultsListener(mock_experiment, mock_sub, "sub/path", "bucket", "evals", mock_batch, "test-exp")

    mock_msg = MagicMock()
    mock_msg.attributes = {"NewJobState": "FAILED", "JobName": "jobs/job-123"}

    # Mock GCS program candidate reading (for fallback failure reporting)
    mock_read.return_value = {
        "name": "exp/123/prog/1",
        "lockToken": "abc",
    }

    listener.callback(mock_msg)

    mock_msg.ack.assert_called_once()
    mock_experiment.submit_program_evaluations.assert_called_once()
    # Should submit a failure score (compile_success=0.0)
    call_args = mock_experiment.submit_program_evaluations.call_args[0][0][0]
    assert call_args["evaluation"]["insights"]["insights"][0]["label"] == "CRITICAL_ERROR"


@patch("alpha_evolve.workers.check_duplicate_evaluation", return_value=True)
def test_results_listener_duplicate_ignored(mock_check, mock_experiment):
    mock_sub = MagicMock()
    mock_batch = MagicMock()
    listener = ResultsListener(mock_experiment, mock_sub, "sub/path", "bucket", "evals", mock_batch, "test-exp")

    mock_msg = MagicMock()
    mock_msg.attributes = {"NewJobState": "SUCCEEDED", "JobName": "jobs/job-123"}

    listener.callback(mock_msg)

    mock_msg.ack.assert_called_once()
    mock_experiment.submit_program_evaluations.assert_not_called()
    mock_check.assert_called_once_with("bucket", "test-exp", "123")


@pytest.mark.asyncio
async def test_sampling_worker_failed_experiment(mock_experiment, mock_engine):
    # Configure acquire_programs to raise ValueError on failed state
    mock_experiment.acquire_programs.side_effect = ValueError(
        "Experiment is FAILED. No further action can be taken."
    )

    worker = SamplingWorker(mock_experiment, mock_engine, poll_interval=0.01)

    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    # Worker catches the exception and sleeps, so client stats shouldn't be incremented
    assert mock_experiment.stats["num_programs_generated"] == 0
    mock_engine.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_sampling_worker_permission_error(mock_experiment, mock_engine):
    mock_experiment.acquire_programs.side_effect = Exception("API Error: 403 Forbidden")
    worker = SamplingWorker(mock_experiment, mock_engine, poll_interval=0.01)

    with pytest.raises(Exception, match="403 Forbidden"):
        await worker.run()

