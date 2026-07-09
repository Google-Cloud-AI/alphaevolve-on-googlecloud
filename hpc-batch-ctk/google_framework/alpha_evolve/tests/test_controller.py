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

"""Unit tests for AlphaEvolveController."""

import asyncio
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from alpha_evolve.controller import AlphaEvolveController
from alpha_evolve.execution import DistributedEngine
from alpha_evolve.experiment import AlphaEvolveExperiment


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("_PROJECT_ID", "test-project")
    monkeypatch.setenv("_CLOUD_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("_USER_EXPERIMENT_NAME", "test-exp")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "STANDARD")


def test_controller_init_missing_project(monkeypatch):
    monkeypatch.setenv("_PROJECT_ID", "")
    with pytest.raises(ValueError, match="Project ID not found in environment"):
        AlphaEvolveController()


def test_controller_init_missing_bucket(monkeypatch):
    monkeypatch.setenv("_PROJECT_ID", "test-project")
    monkeypatch.setenv("_CLOUD_BUCKET_NAME", "")
    with pytest.raises(ValueError, match="Bucket name not found in environment"):
        AlphaEvolveController()


def test_controller_init_dev_mode_rejected(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "dev")
    with pytest.raises(ValueError, match="Invalid evaluation mode: dev"):
        AlphaEvolveController()


def test_controller_init_batch_mode(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    c = AlphaEvolveController()
    assert isinstance(c.engine, DistributedEngine)


def test_controller_init_invalid_provisioning(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "INVALID")
    with pytest.raises(ValueError, match="Invalid _EVALUATION_PROVISIONING_MODEL"):
        AlphaEvolveController()


def test_controller_init_invalid_mode(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "unknown")
    with pytest.raises(ValueError, match="Invalid evaluation mode: unknown"):
        AlphaEvolveController()


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.write_file_to_gcs")
async def test_run_loop_validation_errors(mock_write, mock_read, mock_env):
    mock_read.return_value = None
    c = AlphaEvolveController()

    dummy_eval = lambda: {"scores": {}}
    
    # Invalid max_programs
    with pytest.raises(ValueError, match="run_settings.max_programs must be an integer"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_programs": 0}}, {"name": "init"})

    with pytest.raises(ValueError, match="run_settings.max_programs must be an integer"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_programs": "abc"}}, {"name": "init"})

    # Invalid concurrency
    with pytest.raises(ValueError, match="run_settings.concurrency must be an integer"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_programs": 10, "concurrency": -5}}, {"name": "init"})

    # Invalid max_duration type
    with pytest.raises(ValueError, match="run_settings.max_duration must be an integer hour"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_duration": "abc"}}, {"name": "init"})

    # Out of bounds max_duration
    with pytest.raises(ValueError, match="run_settings.max_duration must be between 1 and 24 hours inclusive"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_duration": 0}}, {"name": "init"})
    with pytest.raises(ValueError, match="run_settings.max_duration must be between 1 and 24 hours inclusive"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_duration": 25}}, {"name": "init"})

    # Invalid idle_timeout type
    with pytest.raises(ValueError, match="run_settings.idle_timeout must be an integer hour"):
        await c.run_loop(dummy_eval, {"run_settings": {"idle_timeout": "abc"}}, {"name": "init"})

    # Out of bounds idle_timeout
    with pytest.raises(ValueError, match="run_settings.idle_timeout must be at least 1 hour"):
        await c.run_loop(dummy_eval, {"run_settings": {"idle_timeout": 0}}, {"name": "init"})

    # idle_timeout >= max_duration
    with pytest.raises(ValueError, match="run_settings.idle_timeout .* must be strictly less than run_settings.max_duration"):
        await c.run_loop(dummy_eval, {"run_settings": {"max_duration": 6, "idle_timeout": 6}}, {"name": "init"})

    # idle_timeout >= default max_duration (6)
    with pytest.raises(ValueError, match="run_settings.idle_timeout .* must be strictly less than run_settings.max_duration"):
        await c.run_loop(dummy_eval, {"run_settings": {"idle_timeout": 6}}, {"name": "init"})


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.delete_file_from_gcs")
async def test_run_loop_resume_completed(mock_delete, mock_read, mock_env):
    # Test when resuming a completed experiment
    mock_read.return_value = {
        "session_name": "sessions/1",
        "experiment_name": "exp/1",
        "initial_program": {"name": "prog/1"},
    }
    c = AlphaEvolveController()
    
    mock_exp = MagicMock()
    mock_exp.get_experiment.return_value = {"state": "COMPLETED"}
    
    with patch("alpha_evolve.controller.AlphaEvolveExperiment", return_value=mock_exp):
        await c.run_loop(lambda: {}, {"title": "test"}, {"name": "init"})
        mock_delete.assert_called_once()


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.write_file_to_gcs")
async def test_run_loop_new_execution(mock_write, mock_read, mock_env):
    mock_read.return_value = None
    c = AlphaEvolveController()

    mock_exp = MagicMock()
    mock_exp.session_name = "sessions/1"
    mock_exp.experiment_name = "exp/1"
    mock_exp.evaluator_client.__name__ = "dummy_eval"
    mock_exp.stopping_criteria_met.side_effect = [False, True] # Stop on second iteration
    mock_exp.get_experiment.return_value = {"state": "RUNNING"}

    c.engine = MagicMock()
    c.engine.start = MagicMock(return_value=asyncio.Future())
    c.engine.start.return_value.set_result(None)
    c.engine.stop = MagicMock(return_value=asyncio.Future())
    c.engine.stop.return_value.set_result(None)

    with patch("alpha_evolve.controller.AlphaEvolveExperiment", return_value=mock_exp):
        with patch("alpha_evolve.controller.SamplingWorker") as mock_worker:
            from unittest.mock import AsyncMock
            mock_worker_instance = MagicMock()
            mock_worker_instance.run = AsyncMock()
            mock_worker.return_value = mock_worker_instance
            
            await c.run_loop(lambda: {}, {"title": "test"}, {"name": "init"}, num_samplers=2)
            
            mock_exp.create_experiment.assert_called_once()
            mock_exp.create_initial_program.assert_called_once()
            mock_exp.start_experiment.assert_called_once()
            c.engine.start.assert_called_once()
            c.engine.stop.assert_called_once()


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.write_file_to_gcs")
async def test_run_loop_retains_batch_params(mock_write, mock_read, mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_MACHINE_TYPE", "n1-standard-4")
    monkeypatch.setenv("_ACCELERATOR_COUNT", "3")
    monkeypatch.setenv("_ACCELERATOR_TYPE", "nvidia-tesla-t4")
    
    mock_read.return_value = None
    c = AlphaEvolveController()
    
    assert c.engine.batch_params["accelerator_count"] == 3
    assert c.engine.batch_params["accelerator_type"] == "nvidia-tesla-t4"

    mock_exp = MagicMock()
    mock_exp.session_name = "sessions/1"
    mock_exp.experiment_name = "exp/1"
    mock_exp.evaluator_client.__name__ = "dummy_eval"
    mock_exp.stopping_criteria_met.side_effect = [True] 
    mock_exp.get_experiment.return_value = {"state": "RUNNING"}

    c.engine = MagicMock()
    c.engine.batch_params = {
        "accelerator_count": 3,
        "accelerator_type": "nvidia-tesla-t4"
    }
    c.engine.start = MagicMock(return_value=asyncio.Future())
    c.engine.start.return_value.set_result(None)
    c.engine.stop = MagicMock(return_value=asyncio.Future())
    c.engine.stop.return_value.set_result(None)

    with patch("alpha_evolve.controller.AlphaEvolveExperiment", return_value=mock_exp):
        with patch("alpha_evolve.controller.SamplingWorker") as mock_worker:
            from unittest.mock import AsyncMock
            mock_worker_instance = MagicMock()
            mock_worker_instance.run = AsyncMock()
            mock_worker.return_value = mock_worker_instance
            
            await c.run_loop(lambda: {}, {"title": "test"}, {"name": "init"}, num_samplers=1)
            
            assert c.engine.batch_params["accelerator_count"] == 3
            assert c.engine.batch_params["accelerator_type"] == "nvidia-tesla-t4"
            assert c.engine.batch_params["client_evaluator_method"] == "dummy_eval"


def test_list_programs(mock_env):
    c = AlphaEvolveController()
    with pytest.raises(ValueError, match="Experiment has not been initialized."):
        c.list_programs({})

    c.experiment = MagicMock()
    c.experiment.list_programs.return_value = {"programs": []}
    res = c.list_programs({"pageSize": 10})
    assert res == {"programs": []}
    c.experiment.list_programs.assert_called_with(params={"pageSize": 10})


def test_controller_init_flex_start_valid_machine(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "FLEX_START")
    monkeypatch.setenv("_EVALUATION_MACHINE_TYPE", "n1-standard-4")
    monkeypatch.setenv("_ACCELERATOR_COUNT", "1")
    monkeypatch.setenv("_ACCELERATOR_TYPE", "nvidia-tesla-t4")
    c = AlphaEvolveController()
    assert isinstance(c.engine, DistributedEngine)
    assert c.engine.batch_params["accelerator_count"] == 1
    assert c.engine.batch_params["accelerator_type"] == "nvidia-tesla-t4"


def test_controller_init_flex_start_valid_h4d_machine(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "FLEX_START")
    monkeypatch.setenv("_EVALUATION_MACHINE_TYPE", "h4d-standard-192")
    c = AlphaEvolveController()
    assert isinstance(c.engine, DistributedEngine)
    assert "accelerator_count" not in c.engine.batch_params
    assert "accelerator_type" not in c.engine.batch_params



def test_controller_init_flex_start_invalid_machine(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "FLEX_START")
    monkeypatch.setenv("_EVALUATION_MACHINE_TYPE", "n2-standard-4")
    with pytest.raises(ValueError, match="Invalid _EVALUATION_MACHINE_TYPE"):
        AlphaEvolveController()


def test_controller_init_n1_missing_accelerator_vars(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "STANDARD")
    monkeypatch.setenv("_EVALUATION_MACHINE_TYPE", "n1-standard-4")
    monkeypatch.delenv("_ACCELERATOR_COUNT", raising=False)
    monkeypatch.delenv("_ACCELERATOR_TYPE", raising=False)
    c = AlphaEvolveController()
    assert isinstance(c.engine, DistributedEngine)
    assert c.engine.batch_params["accelerator_count"] == 1
    assert c.engine.batch_params["accelerator_type"] == "nvidia-tesla-t4"


def test_controller_init_n1_invalid_accelerator_type(mock_env, monkeypatch):
    monkeypatch.setenv("_EVALUATION_MODE", "batch")
    monkeypatch.setenv("_EVALUATION_PROVISIONING_MODEL", "STANDARD")
    monkeypatch.setenv("_EVALUATION_MACHINE_TYPE", "n1-standard-4")
    monkeypatch.setenv("_ACCELERATOR_COUNT", "1")
    monkeypatch.setenv("_ACCELERATOR_TYPE", "nvidia-tesla-k80")
    with pytest.raises(ValueError, match="Invalid _ACCELERATOR_TYPE"):
        AlphaEvolveController()


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.delete_file_from_gcs")
async def test_run_loop_experiment_fails(mock_delete, mock_read, mock_env):
    mock_read.return_value = None
    c = AlphaEvolveController()

    mock_exp = MagicMock()
    mock_exp.session_name = "sessions/1"
    mock_exp.experiment_name = "exp/1"
    mock_exp.evaluator_client.__name__ = "dummy_eval"
    mock_exp.stopping_criteria_met.side_effect = Exception("Experiment is FAILED")

    c.engine = MagicMock()
    c.engine.start = MagicMock(return_value=asyncio.Future())
    c.engine.start.return_value.set_result(None)
    c.engine.stop = MagicMock(return_value=asyncio.Future())
    c.engine.stop.return_value.set_result(None)

    with patch("alpha_evolve.controller.AlphaEvolveExperiment", return_value=mock_exp):
        with patch("alpha_evolve.controller.SamplingWorker") as mock_worker:
            from unittest.mock import AsyncMock
            mock_worker_instance = MagicMock()
            mock_worker_instance.run = AsyncMock()
            mock_worker.return_value = mock_worker_instance
            
            with pytest.raises(Exception, match="Experiment is FAILED"):
                await c.run_loop(lambda: {}, {"title": "test"}, {"name": "init"}, num_samplers=2)
                
            mock_delete.assert_called_once_with("test-bucket", "test-exp/current_experiment.json")
            c.engine.stop.assert_called_once()


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.delete_file_from_gcs")
async def test_run_loop_resume_experiment_fails(mock_delete, mock_read, mock_env):
    mock_read.return_value = {
        "session_name": "sessions/1",
        "experiment_name": "exp/1",
        "initial_program": {"name": "prog/1"},
    }
    c = AlphaEvolveController()

    mock_exp = MagicMock()
    mock_exp.resume_experiment.side_effect = Exception("Experiment is failed. No further action can be taken.")

    with patch("alpha_evolve.controller.AlphaEvolveExperiment", return_value=mock_exp):
        with pytest.raises(Exception, match="Experiment is failed"):
            await c.run_loop(lambda: {}, {"title": "test"}, {"name": "init"})
            
        mock_delete.assert_called_once_with("test-bucket", "test-exp/current_experiment.json")


@pytest.mark.asyncio
@patch("alpha_evolve.controller.read_file_from_gcs")
@patch("alpha_evolve.controller.write_file_to_gcs")
async def test_run_loop_translates_duration_settings(mock_write, mock_read, mock_env):
    mock_read.return_value = None
    c = AlphaEvolveController()
    
    mock_exp = MagicMock()
    mock_exp.session_name = "sessions/1"
    mock_exp.experiment_name = "exp/1"
    mock_exp.evaluator_client.__name__ = "dummy_eval"
    mock_exp.stopping_criteria_met.return_value = True
    
    c.engine = MagicMock()
    c.engine.start = MagicMock(return_value=asyncio.Future())
    c.engine.start.return_value.set_result(None)
    c.engine.stop = MagicMock(return_value=asyncio.Future())
    c.engine.stop.return_value.set_result(None)
    
    config = {
        "title": "test",
        "run_settings": {
            "max_duration": 24,
            "idle_timeout": 5
        }
    }
    
    with patch("alpha_evolve.controller.AlphaEvolveExperiment", return_value=mock_exp):
        with patch("alpha_evolve.controller.SamplingWorker") as mock_worker:
            from unittest.mock import AsyncMock
            mock_worker_instance = MagicMock()
            mock_worker_instance.run = AsyncMock()
            mock_worker.return_value = mock_worker_instance
            
            await c.run_loop(lambda: {}, config, {"name": "init"}, num_samplers=1)
            
            # Verify translation to seconds strings
            mock_exp.create_experiment.assert_called_once_with({
                "title": "test",
                "run_settings": {
                    "max_duration": "86400s",
                    "idle_timeout": "18000s"
                }
            })

