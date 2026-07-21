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

"""Controller loop for AlphaEvolve experiments.

Implements the acquire + evaluate + submit cycle that drives the evolutionary
search. The controller continuously acquires candidate programs from the
backend, evaluates them locally using a user-provided evaluator script, and
submits the scores back to the backend.
"""

from __future__ import annotations

import dataclasses
import pathlib
import time
from typing import Any

from . import client as client_module
from . import evaluator as evaluator_module
from . import locks
from . import nicknames


# Experiment states that indicate the loop should stop.
_TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

# How long to wait when no programs are available, in seconds.
_POLL_INTERVAL_SECONDS = 5

# How many consecutive empty acquires before checking experiment state.
_EMPTY_ACQUIRE_THRESHOLD = 3

# Save the nickname index to disk every N iterations to avoid losing
# nickname mappings if the controller crashes or is interrupted.
_INDEX_SAVE_INTERVAL = 10


class ControllerStats:
  """Tracks statistics for the controller loop."""

  def __init__(self) -> None:
    self.total_evaluated: int = 0
    self.total_succeeded: int = 0
    self.total_failed: int = 0
    self.best_score: float | None = None
    self.best_program: str | None = None
    self.scores: list[float] = []

  def record(self, score: float, program_name: str, success: bool) -> None:
    """Records the result of an evaluation."""
    self.total_evaluated += 1
    if success:
      self.total_succeeded += 1
      self.scores.append(score)
      if self.best_score is None or score > self.best_score:
        self.best_score = score
        self.best_program = program_name
    else:
      self.total_failed += 1

  def to_dict(self) -> dict[str, int | float | str | None]:
    """Serializes stats to a dictionary."""
    return {
        "total_evaluated": self.total_evaluated,
        "total_succeeded": self.total_succeeded,
        "total_failed": self.total_failed,
        "best_score": self.best_score,
        "best_program": self.best_program,
    }


class ControllerCallbacks:
  """Callbacks for controller loop events. Override for custom behavior."""

  def on_acquire(self, program_name: str, nickname: str) -> None:
    """Called when a program is acquired."""

  def on_evaluate(
      self,
      program_name: str,
      nickname: str,
      result: evaluator_module.EvaluationResult,
  ) -> None:
    """Called after a program is evaluated."""

  def on_submit(self, program_name: str, nickname: str, score: float) -> None:
    """Called after a score is submitted."""

  def on_new_best(self, program_name: str, nickname: str, score: float) -> None:
    """Called when a new best score is found."""

  def on_no_programs(self) -> None:
    """Called when no programs are available."""

  def on_experiment_terminal(self, state: str) -> None:
    """Called when the experiment reaches a terminal state."""

  def on_error(self, stage: str, error: Exception) -> None:
    """Called when an error occurs."""

  def on_progress(
      self, stats: ControllerStats, iteration: int, max_iterations: int
  ) -> None:
    """Called periodically with progress info."""


def run_controller_loop(
    client: client_module.AlphaEvolveClient,
    experiment_name: str,
    evaluator_path: pathlib.Path | str,
    max_iterations: int = 0,
    timeout: int = evaluator_module.DEFAULT_TIMEOUT_SECONDS,
    backend: str = "local",
    poll_interval: int = _POLL_INTERVAL_SECONDS,
    callbacks: ControllerCallbacks | None = None,
    lock_cache: locks.LockCache | None = None,
    python_binary: str | None = None,
    extra_evaluator_args: str | None = None,
) -> ControllerStats:
  """Runs the acquire + evaluate + submit controller loop.

  Continuously acquires candidate programs from the AlphaEvolve backend,
  evaluates them locally, and submits the scores back. Stops when:
   - max_iterations is reached (if > 0)
   - the experiment reaches a terminal state (COMPLETED, FAILED, CANCELLED)
   - the caller interrupts (KeyboardInterrupt)

  Args:
   client: An AlphaEvolveClient instance.
   experiment_name: Full resource name of the experiment.
   evaluator_path: Path to the evaluator script.
   max_iterations: Maximum number of evaluation iterations (0 = unlimited).
   timeout: Timeout per evaluation in seconds.
   backend: Evaluation backend ('local' or 'podman').
   poll_interval: Seconds to wait when no programs are available.
   callbacks: Optional ControllerCallbacks for event notifications.
   lock_cache: Optional LockCache for managing program locks.
   python_binary: Python binary for subprocess evaluation.
   extra_evaluator_args: Extra arguments to pass to the evaluator script.

  Returns:
   ControllerStats with the final statistics.
  """
  if callbacks is None:
    callbacks = ControllerCallbacks()

  stats: ControllerStats = ControllerStats()
  index: nicknames.NicknameIndex = nicknames.NicknameIndex()
  eval_path: pathlib.Path = pathlib.Path(evaluator_path)
  consecutive_empty: int = 0
  iteration: int = 0

  while True:
    # Check max iterations.
    if max_iterations > 0 and iteration >= max_iterations:
      break

    # --- Acquire ---
    try:
      result = client.acquire_programs(experiment_name, desired_count=1)
    except client_module.ApiError as e:
      callbacks.on_error("acquire", e)
      time.sleep(poll_interval)
      continue

    programs: list[dict[str, Any]] = result.get("programs") or result.get(
        "alphaEvolvePrograms", []
    )
    lock_token: str | None = result.get("lockToken", "")

    if not programs:
      consecutive_empty += 1
      callbacks.on_no_programs()

      # After several empty acquires, check experiment state.
      if consecutive_empty >= _EMPTY_ACQUIRE_THRESHOLD:
        try:
          exp_data = client.get_experiment(experiment_name)
          state = exp_data.get("state", "")
          if state in _TERMINAL_STATES:
            callbacks.on_experiment_terminal(state)
            break
        except client_module.ApiError:
          pass
        consecutive_empty = 0

      time.sleep(poll_interval)
      continue

    consecutive_empty = 0

    for prog in programs:
      prog_name: str = prog.get("name", "")
      nickname: str = index.get_nickname(prog_name) if prog_name else "?"
      prog_lock: str | None = (
          prog.get("lockToken") or prog.get("lock_token") or lock_token
      )

      # Cache the lock token.
      if lock_cache and prog_name and prog_lock:
        lock_cache.add(prog_name, prog_lock)

      callbacks.on_acquire(prog_name, nickname)

      # --- Extract files ---
      files: list[dict[str, str]] = prog.get("content", {}).get("files", [])
      program_files: list[dict[str, str]] = []
      for f in files:
        program_files.append({
            "path": f.get("path", "program.py"),
            "content": f.get("content", ""),
        })

      # --- Evaluate ---
      if not program_files:
        eval_result = evaluator_module.EvaluationResult(
            score=evaluator_module.FAILURE_SCORE,
            scores=[{
                "metric": "score",
                "score": evaluator_module.FAILURE_SCORE,
            }],
            success=False,
            error="Program has no files.",
        )
      else:
        eval_result = evaluator_module.evaluate_program(
            program_files=program_files,
            evaluator_path=eval_path,
            backend=backend,
            timeout=timeout,
            python_binary=python_binary,
            extra_evaluator_args=extra_evaluator_args,
        )

      callbacks.on_evaluate(prog_name, nickname, eval_result)

      # --- Submit ---
      score: float = eval_result.score
      eval_scores: list[dict[str, str | float]] = [
          {"metric": "score", "score": score}
      ]
      # The JSON maps to nested proto messages:
      # AlphaEvolveProgramEvaluation.scores (AlphaEvolveEvaluationScores)
      #   .scores (repeated AlphaEvolveEvaluationScore)
      # AlphaEvolveProgramEvaluation.insights (AlphaEvolveEvaluationInsights)
      #   .insights (repeated AlphaEvolveEvaluationInsight)
      evaluation: dict[str, Any] = {"scores": {"scores": eval_scores}}
      if eval_result.insights:
        evaluation["insights"] = {
            "insights": [dataclasses.asdict(i) for i in eval_result.insights]
        }
      submission: dict[str, Any] = {
          "program": prog_name,
          "lockToken": prog_lock,
          "evaluation": evaluation,
      }

      try:
        client.submit_evaluations(experiment_name, [submission])
        callbacks.on_submit(prog_name, nickname, score)
      except client_module.ApiError as e:
        callbacks.on_error("submit", e)

      # --- Track stats ---
      is_new_best: bool = (
          stats.best_score is None or score > stats.best_score
      ) and eval_result.success
      stats.record(score, prog_name, eval_result.success)

      if is_new_best:
        callbacks.on_new_best(prog_name, nickname, score)

      iteration += 1
      callbacks.on_progress(stats, iteration, max_iterations)

      # Periodically persist the nickname index so that nicknames survive
      # crashes, interrupts, and are available for `program show` lookups
      # while the loop is still running.
      if iteration % _INDEX_SAVE_INTERVAL == 0:
        index.save()

      if max_iterations > 0 and iteration >= max_iterations:
        break

  # Save the final state of the nickname index.
  index.save()
  return stats
