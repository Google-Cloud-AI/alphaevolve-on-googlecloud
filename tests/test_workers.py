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
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from alpha_evolve.workers import EvaluationWorker, SamplingWorker


async def run_worker_and_wait(worker, wait_coro, timeout=5.0):
    """
    Runs the worker in a background task, awaits `wait_coro`, and then
    cancels the worker task properly.
    """
    task = asyncio.create_task(worker.run())
    try:
        return await asyncio.wait_for(wait_coro, timeout=timeout)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


@pytest.mark.asyncio
async def test_sampling_worker():
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    fake_program = {"name": "prog1", "content": {"files": []}}

    # Setup mock to return one program, then empty lists
    mock_experiment.client.acquire_programs.side_effect = [
        {"programs": [fake_program]},
        # Subsequent calls return nothing to let worker loop safely until cancelled
        {"programs": []},
        {"programs": []},
    ]
    mock_experiment.stats = {"num_programs_generated": 0}

    # Use a small poll_interval to speed up test if it hits sleep
    queue = asyncio.Queue()
    worker = SamplingWorker(mock_experiment, queue, poll_interval=0.01)

    # Run worker until the queue has an item
    # We await queue.get() which will return the item put by the worker
    item = await run_worker_and_wait(worker, queue.get())

    assert item == fake_program

    # Check stats and client calls
    mock_experiment.client.acquire_programs.assert_called()
    assert mock_experiment.stats["num_programs_generated"] >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("use_async_evaluator", [True, False])
async def test_evaluation_worker(use_async_evaluator):
    """
    Tests EvaluationWorker with both synchronous and asynchronous evaluators.
    Also verifies that evaluation results are filtered correctly.
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"

    # Input program
    program_data = {"name": "prog1", "lockToken": "token_123"}

    # Expected raw output from evaluator (includes fields to be filtered)
    raw_eval_result = {
        "scores": {"fitness": 0.8},
        "insights": {"some_insight": "details"},
        # keys below should be filtered out
        "artifacts": {"heavy_data": "..."},
        "metadata": "debug_info",
    }

    # Configure evaluator
    if use_async_evaluator:

        async def async_evaluator(prog):
            return raw_eval_result

        mock_experiment.evaluator = async_evaluator
    else:
        # Standard MagicMock works fine for sync functions
        mock_experiment.evaluator = MagicMock(return_value=raw_eval_result)

    mock_experiment.stats = {"num_programs_evaluated": 0}

    queue = asyncio.Queue()
    await queue.put(program_data)

    worker = EvaluationWorker(mock_experiment, queue)

    # Run worker until the queue is fully processed
    await run_worker_and_wait(worker, queue.join())

    # Verify submission
    mock_experiment.client.submit_program_evaluations.assert_called_once()
    args, kwargs = mock_experiment.client.submit_program_evaluations.call_args

    # Locate submissions arg (it's the second positional arg or "evaluation_submissions" kwarg)
    if len(args) > 1:
        submissions = args[1]
    else:
        submissions = kwargs["evaluation_submissions"]

    assert len(submissions) == 1
    submission = submissions[0]

    # Check structure
    assert submission["program"] == program_data["name"]
    assert submission["lock_token"] == program_data["lockToken"]

    # Verify filtering: Only "scores" and "insights" should remain
    assert submission["evaluation"] == {
        "scores": {"fitness": 0.8},
        "insights": {"some_insight": "details"},
    }
    assert "artifacts" not in submission["evaluation"]

    # Verify stats
    assert mock_experiment.stats["num_programs_evaluated"] == 1


@pytest.mark.asyncio
async def test_evaluation_worker_parallel():
    """
    Tests EvaluationWorker with parallel_evaluation=True and a dedicated executor.
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.parallel_evaluation = True

    program_data = {"name": "prog1", "lockToken": "token_123"}
    raw_eval_result = {"scores": {"fitness": 0.8}}

    mock_experiment.evaluator = MagicMock(return_value=raw_eval_result)
    mock_experiment.stats = {"num_programs_evaluated": 0}
    mock_experiment.client.submit_program_evaluations.return_value = {"status": "ok"}

    queue = asyncio.Queue()
    await queue.put(program_data)

    # Use a dedicated executor as intended in the controller
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = EvaluationWorker(mock_experiment, queue, executor=executor)
        await run_worker_and_wait(worker, queue.join())

    mock_experiment.client.submit_program_evaluations.assert_called_once()
    assert mock_experiment.stats["num_programs_evaluated"] == 1


@pytest.mark.asyncio
async def test_evaluation_worker_parallel_default_executor():
    """
    Tests EvaluationWorker with parallel_evaluation=True using the default executor (None).
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.parallel_evaluation = True

    program_data = {"name": "prog1", "lockToken": "token_123"}
    raw_eval_result = {"scores": {"fitness": 0.8}}

    mock_experiment.evaluator = MagicMock(return_value=raw_eval_result)
    mock_experiment.stats = {"num_programs_evaluated": 0}
    mock_experiment.client.submit_program_evaluations.return_value = {"status": "ok"}

    queue = asyncio.Queue()
    await queue.put(program_data)

    worker = EvaluationWorker(mock_experiment, queue, executor=None)
    await run_worker_and_wait(worker, queue.join())

    mock_experiment.client.submit_program_evaluations.assert_called_once()
    assert mock_experiment.stats["num_programs_evaluated"] == 1


@pytest.mark.asyncio
async def test_evaluation_worker_submission_failure():
    """
    Tests that stats are not updated if submission fails (returns None).
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.parallel_evaluation = False

    program_data = {"name": "prog1", "lockToken": "token_123"}
    mock_experiment.evaluator = MagicMock(return_value={"scores": {}})
    mock_experiment.stats = {"num_programs_evaluated": 0}

    # Simulate failure
    mock_experiment.client.submit_program_evaluations.return_value = None

    queue = asyncio.Queue()
    await queue.put(program_data)

    worker = EvaluationWorker(mock_experiment, queue)
    await run_worker_and_wait(worker, queue.join())

    assert mock_experiment.stats["num_programs_evaluated"] == 0


@pytest.mark.asyncio
async def test_evaluation_worker_resilience():
    """
    Verifies that the EvaluationWorker remains alive and continues processing
    even if an individual evaluation fails with an exception.
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.stats = {"num_programs_evaluated": 0}
    mock_experiment.parallel_evaluation = False

    # Two programs: first will fail, second should succeed.
    program1 = {"name": "fail_prog", "lockToken": "token1"}
    program2 = {"name": "success_prog", "lockToken": "token2"}

    def mock_evaluator(prog):
        if prog["name"] == "fail_prog":
            raise ValueError("Intentional failure")
        return {"scores": {"fitness": 0.5}}

    mock_experiment.evaluator = mock_evaluator
    mock_experiment.client.submit_program_evaluations.return_value = {"status": "ok"}

    queue = asyncio.Queue()
    await queue.put(program1)
    await queue.put(program2)

    worker = EvaluationWorker(mock_experiment, queue)

    # Wait for the queue to be fully processed (both items)
    await run_worker_and_wait(worker, queue.join())

    # Only one evaluation should have been successful.
    # If the worker died, it would likely only be 0, and queue.join() would have timed out.
    assert mock_experiment.stats["num_programs_evaluated"] == 1


@pytest.mark.asyncio
async def test_sampling_worker_resilience():
    """
    Verifies that the SamplingWorker continues to poll even after
    encountering an API error.
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.stats = {"num_programs_generated": 0}

    # First call fails, second call succeeds.
    mock_experiment.client.acquire_programs.side_effect = [
        RuntimeError("API is down"),
        {"programs": [{"name": "recovered_prog"}]},
        {"programs": []},  # Subsequent empty responses
    ]

    queue = asyncio.Queue()
    # Use small poll_interval to recover quickly
    worker = SamplingWorker(mock_experiment, queue, poll_interval=0.01)

    # Wait until the item from the second call is in the queue
    item = await run_worker_and_wait(worker, queue.get())

    assert item["name"] == "recovered_prog"
    assert mock_experiment.stats["num_programs_generated"] == 1
    assert mock_experiment.client.acquire_programs.call_count >= 2


@pytest.mark.asyncio
async def test_sampling_worker_malformed_response():
    """
    Verifies that the SamplingWorker handles various malformed API responses.
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.stats = {"num_programs_generated": 0}

    # Setup mock to return various malformed or empty responses
    mock_experiment.client.acquire_programs.side_effect = [
        {"not_programs": []},  # Missing expected key
        None,  # API returns None
        {"programs": None},  # Key exists but value is None (should trigger exception)
        {"programs": [{"name": "valid"}]},  # Recovery
        {"programs": []},
    ]

    queue = asyncio.Queue()
    worker = SamplingWorker(mock_experiment, queue, poll_interval=0.01)

    item = await run_worker_and_wait(worker, queue.get())

    assert item["name"] == "valid"
    assert mock_experiment.client.acquire_programs.call_count >= 4


@pytest.mark.asyncio
async def test_sampling_worker_backoff_on_empty_list():
    """
    Verifies that the SamplingWorker sleeps (backs off) even if the API
    returns a valid but empty list of programs.
    """
    mock_experiment = MagicMock()
    mock_experiment.experiment_name = "test_experiment"
    mock_experiment.stats = {"num_programs_generated": 0}

    # First call returns empty, second returns a program.
    mock_experiment.client.acquire_programs.side_effect = [
        {"programs": []},
        {"programs": [{"name": "delayed_prog"}]},
        {"programs": []},
    ]

    queue = asyncio.Queue()
    # If the worker doesn't sleep on {"programs": []}, it will hit the second call immediately.
    # We can't easily prove it *didn't* sleep without mocking asyncio.sleep,
    # but we can verify it functions correctly and doesn't crash.
    worker = SamplingWorker(mock_experiment, queue, poll_interval=0.01)

    item = await run_worker_and_wait(worker, queue.get())
    assert item["name"] == "delayed_prog"


def test_short_id():
    from alpha_evolve.workers import _short_id
    assert _short_id("projects/p/locations/l/collections/c/engines/e/sessions/s1") == "s1"
    assert _short_id("") == "unknown"
    assert _short_id(None) == "unknown"


def test_scores_summary():
    from alpha_evolve.workers import _scores_summary
    # Valid scores
    evaluation = {
        "scores": {
            "scores": [
                {"metric": "m1", "score": 0.123456},
                {"metric": "m2", "score": 42}
            ]
        }
    }
    assert _scores_summary(evaluation) == "m1=0.1235, m2=42"

    # Empty scores
    assert _scores_summary({}) == "no scores"

    # Malformed (trigger exception)
    assert _scores_summary(None) == "None"

