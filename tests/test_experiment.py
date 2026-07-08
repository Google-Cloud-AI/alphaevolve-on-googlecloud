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

from unittest.mock import MagicMock

import pytest

from alpha_evolve.experiment import AlphaEvolveExperiment


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_evaluator():
    return MagicMock()


@pytest.fixture
def experiment(mock_client, mock_evaluator):
    return AlphaEvolveExperiment(
        mock_client,
        mock_evaluator,
        max_programs_evaluated=10,
        parallel_evaluation=True,
    )


def test_init_params(experiment):
    assert experiment.parallel_evaluation is True


def test_create_experiment(experiment, mock_client):
    mock_client.create_session.return_value = "session1"
    mock_client.create_experiment.return_value = {"name": "exp1"}

    config = {
        "title": "Test Exp",
        "generation_settings": {"models": [{"name": "gemini-2.5-flash"}]}
    }
    experiment.create_experiment(config)

    assert experiment.session_name == "session1"
    assert experiment.experiment_name == "exp1"
    mock_client.create_session.assert_called_once()
    mock_client.create_experiment.assert_called_with(config, "session1")


def test_create_initial_program(experiment, mock_client):
    mock_client.create_initial_program.return_value = {"name": "prog1"}

    experiment.experiment_name = "test-exp"
    experiment.create_initial_program({"content": "foo"})

    assert experiment.initial_program_name == "prog1"
    mock_client.create_initial_program.assert_called_with(
        "test-exp", {"content": "foo"}
    )


def test_start_experiment(experiment, mock_client):
    experiment.experiment_name = "test-exp"
    experiment.start_experiment()
    mock_client.start_experiment.assert_called_with("test-exp")


def test_resume_experiment(experiment, mock_client):
    experiment.experiment_name = "test-exp"
    experiment.resume_experiment()
    mock_client.resume_experiment.assert_called_with("test-exp")


def test_evaluator_wrapper(experiment, mock_evaluator):
    mock_evaluator.return_value = {"metric1": 0.5}

    result = experiment.evaluator({"name": "prog1"})

    expected = {"scores": {"scores": [{"metric": "metric1", "score": 0.5}]}}
    assert result == expected


@pytest.mark.asyncio
async def test_async_evaluator_wrapper(mock_client):
    async def async_evaluator(program):
        return {"metric1": 0.6}

    experiment = AlphaEvolveExperiment(
        mock_client,
        async_evaluator,
        max_programs_evaluated=10,
    )

    import inspect
    assert inspect.iscoroutinefunction(experiment.evaluator)

    result = await experiment.evaluator({"name": "prog1"})

    expected = {"scores": {"scores": [{"metric": "metric1", "score": 0.6}]}}
    assert result == expected

