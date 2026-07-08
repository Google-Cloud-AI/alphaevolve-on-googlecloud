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

import asyncio
from unittest.mock import MagicMock, patch
import pytest
from alpha_evolve.controller import run_controller_loop

@pytest.mark.asyncio
async def test_run_controller_loop_normal_shutdown():
    """Verifies that the controller shuts down correctly under normal conditions."""
    mock_experiment = MagicMock()
    mock_experiment.parallel_evaluation = False
    mock_experiment.stats = {"num_programs_generated": 0, "num_programs_evaluated": 0}

    # We will update stats on the second check to trigger made_progress
    def stopping_effect():
        if stopping_effect.calls == 1:
            mock_experiment.stats = {"num_programs_generated": 1, "num_programs_evaluated": 0}
        stopping_effect.calls += 1
        return stopping_effect.calls > 2
    stopping_effect.calls = 0
    mock_experiment.stopping_criteria_met.side_effect = stopping_effect

    async def mock_run():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            pass

    with patch("alpha_evolve.controller.SamplingWorker") as MockSampler, \
         patch("alpha_evolve.controller.EvaluationWorker") as MockEvaluator, \
         patch("alpha_evolve.controller.PROGRESS_LOG_INTERVAL_S", 0):

        # Ensure run() returns a coroutine
        MockSampler.return_value.run = mock_run
        MockEvaluator.return_value.run = mock_run

        await run_controller_loop(mock_experiment, num_samplers=1, num_evaluators=1)

        assert stopping_effect.calls >= 3
        MockSampler.assert_called()
        MockEvaluator.assert_called()


@pytest.mark.asyncio
async def test_run_controller_loop_executor_cleanup_on_init_failure():
    """
    Verifies that the ThreadPoolExecutor is shut down even if an exception 
    occurs during task initialization (the core goal of the move to the try block).
    """
    mock_experiment = MagicMock()
    mock_experiment.parallel_evaluation = True
    
    # Trigger an exception during task creation (after executor is created)
    # We patch SamplingWorker to raise an error during __init__
    with patch("alpha_evolve.controller.SamplingWorker", side_effect=RuntimeError("Task Spawn Failed")), \
         patch("alpha_evolve.controller.ThreadPoolExecutor") as MockExecutor:
        
        mock_executor_instance = MockExecutor.return_value
        
        with pytest.raises(RuntimeError, match="Task Spawn Failed"):
            await run_controller_loop(mock_experiment, num_samplers=1, num_evaluators=1)
        
        # Verify that executor was shut down despite the error during task spawning
        mock_executor_instance.shutdown.assert_called_once_with(wait=False)

@pytest.mark.asyncio
async def test_run_controller_loop_idle_timeout():
    """
    Verifies the loop exits when the backend stops yielding candidates before
    max_programs_evaluated is reached, instead of hanging forever.
    """
    mock_experiment = MagicMock()
    mock_experiment.parallel_evaluation = False
    mock_experiment.max_programs_evaluated = 10
    mock_experiment.stats = {"num_programs_generated": 9, "num_programs_evaluated": 9}
    mock_experiment.stopping_criteria_met.return_value = False

    async def mock_run():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            pass

    with patch("alpha_evolve.controller.SamplingWorker") as MockSampler, \
         patch("alpha_evolve.controller.EvaluationWorker") as MockEvaluator:

        MockSampler.return_value.run = mock_run
        MockEvaluator.return_value.run = mock_run

        # If the idle timeout doesn't fire, this raises asyncio.TimeoutError.
        await asyncio.wait_for(
            run_controller_loop(
                mock_experiment, num_samplers=1, num_evaluators=1, idle_timeout_s=1
            ),
            timeout=5.0,
        )

    assert mock_experiment.stopping_criteria_met.call_count >= 1


@pytest.mark.asyncio
async def test_run_controller_loop_parallel_evaluation_config():
    """Verifies that the executor is created and passed to workers when parallel_evaluation is True."""
    mock_experiment = MagicMock()
    mock_experiment.parallel_evaluation = True
    mock_experiment.stopping_criteria_met.return_value = True # Exit immediately
    
    async def mock_run():
        pass

    with patch("alpha_evolve.controller.SamplingWorker") as MockSampler, \
         patch("alpha_evolve.controller.EvaluationWorker") as MockEvaluator, \
         patch("alpha_evolve.controller.ThreadPoolExecutor") as MockExecutor:
        
        MockSampler.return_value.run = mock_run
        MockEvaluator.return_value.run = mock_run
        mock_executor_instance = MockExecutor.return_value
        
        await run_controller_loop(mock_experiment, num_samplers=0, num_evaluators=1)
        
        MockExecutor.assert_called_once()
        # Ensure EvaluationWorker was instantiated with the executor
        MockEvaluator.assert_called()
        _, kwargs = MockEvaluator.call_args
        assert kwargs["executor"] == mock_executor_instance
        mock_executor_instance.shutdown.assert_called_once()
