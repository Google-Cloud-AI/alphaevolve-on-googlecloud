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

"""Local evaluation backends for AlphaEvolve programs.

Provides backends for running evaluator scripts against evolved program code.

Each backend writes the program files to a workspace, invokes the evaluator,
and parses the structured JSON score output.

Supported backends:
 - local: Runs the evaluator directly as a subprocess.
 - podman: Runs the evaluator inside a Podman container (planned).
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any


# Sentinel score returned when evaluation fails for any reason.
FAILURE_SCORE = -(10**12)

# Default timeout for evaluation in seconds.
DEFAULT_TIMEOUT_SECONDS = 60


class EvaluationError(Exception):
  """Raised when an evaluation fails."""

  def __init__(
      self,
      message: str,
      stdout: str = "",
      stderr: str = "",
      returncode: int | None = None,
  ):
    self.stdout = stdout
    self.stderr = stderr
    self.returncode = returncode
    super().__init__(message)


@dataclasses.dataclass
class Insight:
  """A single evaluation insight (maps to AlphaEvolveEvaluationInsight)."""

  label: str
  text: str


@dataclasses.dataclass
class EvaluationResult:
  """Structured result from a program evaluation."""

  score: float
  scores: list[dict[str, Any]]
  stdout: str = ""
  stderr: str = ""
  success: bool = True
  error: str = ""
  insights: list[Insight] = dataclasses.field(default_factory=list)

  @property
  def primary_score(self) -> float:
    """Returns the primary (first) score value."""
    return self.score

  def to_dict(self) -> dict[str, Any]:
    """Serializes the result to a dictionary."""
    return dataclasses.asdict(self)


@dataclasses.dataclass
class ParsedScoreOutput:
  """Parsed evaluator score file contents."""

  primary_score: float
  scores: list[dict[str, Any]]
  insights: list[Insight]


def _failure_insights(error_msg: str, stderr: str = "") -> list[Insight]:
  """Build insight list from an error message and optional stderr."""
  insights = [Insight(label="error", text=error_msg)]
  if stderr:
    insights.append(Insight(label="stderr", text=stderr[:2000]))
  return insights


def _parse_score_output(output_path: pathlib.Path) -> ParsedScoreOutput:
  """Parses the JSON score file written by the evaluator.

  Expected format (from evaluator's --output-file):
   {"score": <float>, "insights": [{"label": "...", "text": "..."}]}
  or:
   {"scores": [{"metric": "<name>", "score": <float>}, ...]}

  Args:
   output_path: Path to the JSON score file.

  Returns:
   ParsedScoreOutput with the primary score, scores list, and insights.

  Raises:
   EvaluationError: If the file cannot be parsed or contains no scores.
  """
  if not output_path.exists():
    raise EvaluationError(
        f"Score output file not found: {output_path}",
    )

  try:
    with open(output_path, encoding="utf-8") as f:
      data = json.load(f)
  except (json.JSONDecodeError, OSError) as e:
    raise EvaluationError(
        f"Failed to parse score output: {e}",
    ) from e

  # Extract insights if present.
  raw_insights = data.get("insights", [])
  insights = [Insight(label=i["label"], text=i["text"]) for i in raw_insights]

  # Support both flat {"score": N} and structured {"scores": [...]} formats.
  if "scores" in data and isinstance(data["scores"], list):
    scores_list = data["scores"]
    if not scores_list:
      raise EvaluationError("Score output contains empty scores list.")
    primary = float(scores_list[0].get("score", FAILURE_SCORE))
    return ParsedScoreOutput(primary, scores_list, insights)

  if "score" in data:
    score_val = data["score"]
    if score_val is None:
      return ParsedScoreOutput(
          FAILURE_SCORE,
          [{"metric": "score", "score": FAILURE_SCORE}],
          insights,
      )
    score_val = float(score_val)
    return ParsedScoreOutput(
        score_val, [{"metric": "score", "score": score_val}], insights
    )

  raise EvaluationError(
      f"Score output missing 'score' or 'scores' key: {data}",
  )


def prepare_workspace(
    program_files: list[dict[str, str]],
    evaluator_path: pathlib.Path,
    work_dir: pathlib.Path | None = None,
) -> pathlib.Path:
  """Prepares a workspace directory with program files and evaluator.

  Args:
   program_files: List of dicts with 'path' and 'content' keys.
   evaluator_path: Path to the evaluator script.
   work_dir: Optional directory to use. Creates a temp dir if None.

  Returns:
   Path to the workspace directory.

  Raises:
   FileNotFoundError: If the evaluator script doesn't exist.
   ValueError: If program_files is empty.
  """
  if not program_files:
    raise ValueError("No program files provided.")

  if not evaluator_path.exists():
    raise FileNotFoundError(f"Evaluator not found: {evaluator_path}")

  if work_dir is None:
    work_dir = pathlib.Path(tempfile.mkdtemp(prefix="ae_eval_"))
  else:
    work_dir.mkdir(parents=True, exist_ok=True)

  # Write program files.
  for file_info in program_files:
    file_path = work_dir / file_info["path"]
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(file_info["content"], encoding="utf-8")

  # Copy evaluator into workspace.
  eval_dest = work_dir / "evaluator.py"
  if evaluator_path.resolve() != eval_dest.resolve():
    eval_dest.write_text(
        evaluator_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

  return work_dir


def evaluate_local(
    program_files: list[dict[str, str]],
    evaluator_path: pathlib.Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    work_dir: pathlib.Path | None = None,
    python_binary: str | None = None,
    extra_evaluator_args: str | None = None,
) -> EvaluationResult:
  """Evaluates a program locally by running the evaluator as a subprocess.

  The evaluator script is invoked with a program directory:
   python evaluator.py --output-file <path> --program-dir <workspace>
  The evaluator finds and exec's `initial_program.py` in the program
  directory, then writes a JSON score file to --output-file.

  Args:
   program_files: List of dicts with 'path' and 'content' keys.
   evaluator_path: Path to the evaluator script.
   timeout: Maximum evaluation time in seconds.
   work_dir: Optional workspace directory.
   python_binary: Python interpreter to use. Defaults to sys.executable.
   extra_evaluator_args: Extra arguments to pass to the evaluator script.

  Returns:
   EvaluationResult with scores and metadata.
  """
  if python_binary is None:
    python_binary = sys.executable or shutil.which("python3") or "python3"

  cleanup_work_dir = work_dir is None

  try:
    workspace = prepare_workspace(program_files, evaluator_path, work_dir)
    score_path = workspace / ".eval_scores.json"

    eval_script = workspace / "evaluator.py"

    # Pass --program-dir pointing to the workspace. The evaluator finds
    # and exec's initial_program.py in that directory.
    if not program_files:
      raise ValueError("No program files to evaluate.")
    if not any(pf["path"] == "initial_program.py" for pf in program_files):
      raise ValueError(
          "No initial_program.py found in program files. The main program"
          " file must be named initial_program.py."
      )
    assert python_binary is not None
    cmd = [
        python_binary,
        str(eval_script),
        "--output-file",
        str(score_path),
        "--program-dir",
        str(workspace),
    ]

    if extra_evaluator_args:
      cmd.extend(shlex.split(extra_evaluator_args, posix=(os.name != "nt")))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(workspace),
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    stdout = result.stdout
    stderr = result.stderr

    if result.returncode != 0 and not score_path.exists():
      error_msg = f"Evaluator exited with code {result.returncode}"
      return EvaluationResult(
          score=FAILURE_SCORE,
          scores=[{"metric": "score", "score": FAILURE_SCORE}],
          stdout=stdout,
          stderr=stderr,
          success=False,
          error=error_msg,
          insights=_failure_insights(error_msg, stderr),
      )

    try:
      parsed = _parse_score_output(score_path)
    except EvaluationError as e:
      error_msg = str(e)
      return EvaluationResult(
          score=FAILURE_SCORE,
          scores=[{"metric": "score", "score": FAILURE_SCORE}],
          stdout=stdout,
          stderr=stderr,
          success=False,
          error=error_msg,
          insights=_failure_insights(error_msg, stderr),
      )

    is_success = parsed.primary_score != FAILURE_SCORE and not math.isnan(
        parsed.primary_score
    )
    return EvaluationResult(
        score=parsed.primary_score,
        scores=parsed.scores,
        stdout=stdout,
        stderr=stderr,
        success=is_success,
        error="" if is_success else "Evaluation returned invalid score",
        insights=parsed.insights,
    )

  except subprocess.TimeoutExpired:
    error_msg = f"Evaluation timed out after {timeout} seconds."
    return EvaluationResult(
        score=FAILURE_SCORE,
        scores=[{"metric": "score", "score": FAILURE_SCORE}],
        stdout="",
        stderr="",
        success=False,
        error=error_msg,
        insights=_failure_insights(error_msg),
    )

  except (FileNotFoundError, ValueError, TypeError) as e:
    error_msg = str(e)
    return EvaluationResult(
        score=FAILURE_SCORE,
        scores=[{"metric": "score", "score": FAILURE_SCORE}],
        stdout="",
        stderr="",
        success=False,
        error=error_msg,
        insights=_failure_insights(error_msg),
    )

  finally:
    if cleanup_work_dir and work_dir is None:
      # Clean up temp workspace on success; keep on failure for debugging.
      pass


def evaluate_program(
    program_files: list[dict[str, str]],
    evaluator_path: pathlib.Path,
    backend: str = "local",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    work_dir: pathlib.Path | None = None,
    python_binary: str | None = None,
    extra_evaluator_args: str | None = None,
) -> EvaluationResult:
  """Evaluates a program using the specified backend.

  This is the main entry point for program evaluation. It dispatches to the
  appropriate backend implementation.

  Args:
   program_files: List of dicts with 'path' and 'content' keys.
   evaluator_path: Path to the evaluator script.
   backend: Evaluation backend ('local' or 'podman').
   timeout: Maximum evaluation time in seconds.
   work_dir: Optional workspace directory.
   python_binary: Python interpreter to use (local backend only).
   extra_evaluator_args: Extra arguments to pass to the evaluator script.

  Returns:
   EvaluationResult with scores and metadata.

  Raises:
   ValueError: If the backend is not supported.
  """
  if backend == "local":
    return evaluate_local(
        program_files=program_files,
        evaluator_path=evaluator_path,
        timeout=timeout,
        work_dir=work_dir,
        python_binary=python_binary,
        extra_evaluator_args=extra_evaluator_args,
    )
  elif backend == "podman":
    # Podman backend is planned but not yet implemented.
    raise ValueError(
        "Podman backend is not yet implemented. Use --backend=local."
    )
  else:
    raise ValueError(
        f"Unsupported backend: '{backend}'. Supported: local, podman."
    )
