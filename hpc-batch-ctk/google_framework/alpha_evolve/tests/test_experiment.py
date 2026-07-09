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

"""Unit tests for AlphaEvolveExperiment and Pydantic models."""

import pytest
from unittest.mock import MagicMock

from alpha_evolve.experiment import AlphaEvolveExperiment
from alpha_evolve.models import (
    AlphaEvolveExperimentConfig,
    AlphaEvolveModel,
    AlphaEvolveModelConfig,
    AlphaEvolveGenerationSettings,
    AlphaEvolveRunSettings,
    AlphaEvolveEvolutionSettings,
    AlphaEvolveProgramEvaluation,
    AlphaEvolveEvaluationScores,
    AlphaEvolveEvaluationScore,
    AlphaEvolveExperimentState,
    parse_models_from_env,
)


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.create_session.return_value = "sessions/123"
    client.create_experiment.return_value = {"name": "exp/456"}
    client.create_initial_program.return_value = {"name": "prog/789"}
    client.start_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name}
    client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name}
    return client


def test_pydantic_models_valid():
    config = AlphaEvolveExperimentConfig(
        title="Test Title",
        problem_description="Optimize sorting",
        program_language="python",
        run_settings=AlphaEvolveRunSettings(max_programs=100, concurrency=4),
        generation_settings=AlphaEvolveGenerationSettings(models=[AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V2P5_FLASH)]),
        evolution_settings=AlphaEvolveEvolutionSettings(reset_interval=10),
    )
    assert config.title == "Test Title"
    assert config.run_settings.max_programs == 100
    assert config.generation_settings.models[0].name == AlphaEvolveModel.GEMINI_V2P5_FLASH


def test_models_mixture_validation():
    # Valid mixture of two models with weights
    settings = AlphaEvolveGenerationSettings(
        models=[
            AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V2P5_PRO, weight=0.7),
            AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V2P5_FLASH, weight=0.3),
        ]
    )
    assert len(settings.models) == 2
    assert settings.models[0].weight == 0.7

    # Invalid: more than 2 models
    with pytest.raises(ValueError):
        AlphaEvolveGenerationSettings(
            models=[
                AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V2P5_PRO),
                AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V2P5_FLASH),
                AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V3P5_FLASH),
            ]
        )

    # Invalid: negative weight
    with pytest.raises(ValueError):
        AlphaEvolveModelConfig(name=AlphaEvolveModel.GEMINI_V2P5_PRO, weight=-0.5)


def test_parse_models_from_env():
    parsed_single = parse_models_from_env("GEMINI_V2P5_FLASH")
    assert parsed_single == [{"name": AlphaEvolveModel.GEMINI_V2P5_FLASH}]

    parsed_mixture = parse_models_from_env("GEMINI_V2P5_PRO:0.7, GEMINI_V2P5_FLASH:0.3")
    assert parsed_mixture == [
        {"name": AlphaEvolveModel.GEMINI_V2P5_PRO, "weight": 0.7},
        {"name": AlphaEvolveModel.GEMINI_V2P5_FLASH, "weight": 0.3},
    ]

    parsed_semicolon = parse_models_from_env("GEMINI_V2P5_PRO:0.6;GEMINI_V2P5_FLASH:0.4")
    assert parsed_semicolon == [
        {"name": AlphaEvolveModel.GEMINI_V2P5_PRO, "weight": 0.6},
        {"name": AlphaEvolveModel.GEMINI_V2P5_FLASH, "weight": 0.4},
    ]


def test_pydantic_models_invalid():
    with pytest.raises(ValueError):
        # Missing required fields
        AlphaEvolveExperimentConfig(title="Only Title")


def test_experiment_init(mock_client):
    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    assert exp.max_programs_evaluated == 50
    assert exp.stats["num_programs_evaluated"] == 0


def test_create_experiment(mock_client):
    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.create_experiment({"title": "Test"})
    assert exp.session_name == "sessions/123"
    assert exp.experiment_name == "exp/456"


def test_create_session_failure(mock_client):
    mock_client.create_session.return_value = None
    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    with pytest.raises(RuntimeError, match="Failed to create a Gemini Enterprise session"):
        exp.create_experiment({"title": "Test"})


def test_create_experiment_failure(mock_client):
    mock_client.create_experiment.return_value = None
    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    with pytest.raises(RuntimeError, match="Failed to create experiment at AlphaEvolve API"):
        exp.create_experiment({"title": "Test"})


def test_list_programs_and_experiments(mock_client):
    mock_client.list_alpha_evolve_programs.return_value = {"programs": []}
    mock_client.list_alpha_evolve_experiments.return_value = {"experiments": []}

    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    exp.session_name = "sessions/123"

    assert exp.list_programs() == {"programs": []}
    assert exp.list_experiments() == {"experiments": []}


def test_create_initial_program_and_start(mock_client):
    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"

    init_prog = {
        "evaluation": {
            "scores": {
                "scores": [{"metric": "accuracy", "score": 0.9}]
            }
        }
    }

    exp.create_initial_program(init_prog)
    assert exp.initial_program_name == "prog/789"
    assert exp.metrics_list == ["accuracy"]

    exp.start_experiment()
    mock_client.start_experiment.assert_called_with("exp/456")


def test_resume_experiment_states(mock_client):
    dummy_eval = lambda: {"scores": {}}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    exp.initial_program = {"evaluation": {"scores": {"scores": [{"metric": "acc"}]}}}
    exp.initial_program_name = "prog/789"

    # Test RUNNING state
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name}
    exp.resume_experiment()
    # Should just log

    # Test CREATED state
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.CREATED.name}
    exp.resume_experiment()
    mock_client.start_experiment.assert_called_with("exp/456")

    # Test PAUSED state
    mock_client.get_alpha_evolve_experiment.side_effect = [
        {"name": "exp/456", "state": AlphaEvolveExperimentState.PAUSED.name},
        {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name},
    ]
    exp.resume_experiment()
    mock_client.resume_experiment.assert_called_with("exp/456")

    # Test FAILED state
    mock_client.get_alpha_evolve_experiment.side_effect = None
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.FAILED.name}
    with pytest.raises(Exception, match="Experiment is failed"):
        exp.resume_experiment()


def test_evaluator_wrapper(mock_client):
    # Test flat dict wrapping
    flat_eval = lambda: {"metric1": 1.0, "metric2": 2.0}
    exp1 = AlphaEvolveExperiment(mock_client, flat_eval, 50)
    res1 = exp1.evaluator()
    assert res1 == {
        "scores": {
            "scores": [
                {"metric": "metric1", "score": 1.0},
                {"metric": "metric2", "score": 2.0},
            ]
        }
    }

    # Test structured dict passthrough
    struct_eval = lambda: {"scores": {"scores": [{"metric": "m", "score": 5.0}]}}
    exp2 = AlphaEvolveExperiment(mock_client, struct_eval, 50)
    res2 = exp2.evaluator()
    assert res2 == {"scores": {"scores": [{"metric": "m", "score": 5.0}]}}


def test_stopping_criteria(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=10)
    exp.experiment_name = "exp/456"

    # Criteria not met
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name}
    assert not exp.stopping_criteria_met()

    # Max evaluated met
    exp.stats["num_programs_evaluated"] = 10
    assert exp.stopping_criteria_met()

    # State COMPLETED met
    exp.stats["num_programs_evaluated"] = 5
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.COMPLETED.name}
    assert exp.stopping_criteria_met()


def test_submit_program_evaluations_success(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    
    submissions = [{"program": "prog/1"}]
    exp.submit_program_evaluations(submissions)
    mock_client.submit_program_evaluations.assert_called_with("exp/456", submissions)


def test_submit_program_evaluations_auto_resume_retry(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    exp.initial_program = {"evaluation": {"scores": {"scores": [{"metric": "acc"}]}}}
    exp.initial_program_name = "prog/789"
    
    submissions = [{"program": "prog/1"}]
    
    # Reset side effects/mocks
    mock_client.get_alpha_evolve_experiment.side_effect = None
    mock_client.submit_program_evaluations.side_effect = None
    
    # Mock submit_program_evaluations to raise FAILED_PRECONDITION first, then succeed
    mock_client.submit_program_evaluations.side_effect = [
        Exception("Precondition check failed. FAILED_PRECONDITION"),
        {"status": "OK"}
    ]
    
    # Mock get_alpha_evolve_experiment to return PAUSED, PAUSED, then RUNNING
    mock_client.get_alpha_evolve_experiment.side_effect = [
        {"name": "exp/456", "state": AlphaEvolveExperimentState.PAUSED.name},
        {"name": "exp/456", "state": AlphaEvolveExperimentState.PAUSED.name},
        {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name}
    ]
    
    exp.submit_program_evaluations(submissions)
    
    # Verify client methods were called
    assert mock_client.submit_program_evaluations.call_count == 2
    mock_client.resume_experiment.assert_called_with("exp/456")


def test_acquire_programs_success(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    
    mock_client.acquire_programs.return_value = {"programs": []}
    
    res = exp.acquire_programs(desired_programs_count=3)
    assert res == {"programs": []}
    mock_client.acquire_programs.assert_called_with("exp/456", 3)


def test_acquire_programs_auto_resume_retry(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    exp.initial_program = {"evaluation": {"scores": {"scores": [{"metric": "acc"}]}}}
    exp.initial_program_name = "prog/789"
    
    # Reset side effects/mocks
    mock_client.get_alpha_evolve_experiment.side_effect = None
    mock_client.acquire_programs.side_effect = None
    mock_client.resume_experiment.side_effect = None
    
    # Mock acquire_programs to succeed on the first call
    mock_client.acquire_programs.return_value = {"programs": []}
    
    # Mock get_alpha_evolve_experiment to return:
    # 1. PAUSED (the initial check in acquire_programs)
    # 2. PAUSED (the initial check in resume_experiment)
    # 3. RUNNING (the polling check in resume_experiment)
    mock_client.get_alpha_evolve_experiment.side_effect = [
        {"name": "exp/456", "state": AlphaEvolveExperimentState.PAUSED.name},
        {"name": "exp/456", "state": AlphaEvolveExperimentState.PAUSED.name},
        {"name": "exp/456", "state": AlphaEvolveExperimentState.RUNNING.name}
    ]
    
    res = exp.acquire_programs(desired_programs_count=5)
    assert res == {"programs": []}
    
    # Verify client methods were called
    assert mock_client.acquire_programs.call_count == 1
    mock_client.resume_experiment.assert_called_with("exp/456")


def test_acquire_programs_failed_state(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    
    # Mock get_alpha_evolve_experiment to return FAILED
    mock_client.get_alpha_evolve_experiment.side_effect = None
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.FAILED.name}
    
    with pytest.raises(ValueError, match="Experiment is FAILED. No further action can be taken."):
        exp.acquire_programs(desired_programs_count=3)


def test_stopping_criteria_met_failed_state(mock_client):
    dummy_eval = lambda: {}
    exp = AlphaEvolveExperiment(mock_client, dummy_eval, max_programs_evaluated=50)
    exp.experiment_name = "exp/456"
    
    # Mock get_alpha_evolve_experiment to return FAILED
    mock_client.get_alpha_evolve_experiment.side_effect = None
    mock_client.get_alpha_evolve_experiment.return_value = {"name": "exp/456", "state": AlphaEvolveExperimentState.FAILED.name}
    
    with pytest.raises(Exception, match="Experiment is FAILED. No further action can be taken."):
        exp.stopping_criteria_met()



