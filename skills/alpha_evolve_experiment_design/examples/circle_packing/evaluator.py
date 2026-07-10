"""Evaluator for Circle Packing in Unit Square.

CLI-compatible evaluator for use with the ae CLI.
The ae CLI invokes this as:
  python evaluator.py --output-file <path> --input-program-file <path>
"""

import argparse
import contextlib
import io
import json
import logging
import signal
import traceback
from typing import Any, Mapping

import numpy as np

logger = logging.getLogger(__name__)

EVALUATION_METRIC = "sum_of_radii"
EVALUATION_INPUTS = {"n": 26}


class EvaluationTimeoutError(Exception):
  pass


def _timeout_handler(signum, frame):
  raise EvaluationTimeoutError("Evaluation timed out")


if hasattr(signal, "SIGALRM"):
  signal.signal(signal.SIGALRM, _timeout_handler)


def _solution_diagnostics(
    exec_namespace: dict[str, Any],
) -> list[dict[str, str]]:
  """Extract problem-specific diagnostics from the executed program.

  These insights help the LLM understand why a solution scored the way
  it did, guiding it toward better solutions in subsequent generations.
  """
  insights = []
  try:
    construct = exec_namespace.get("construct_packing")
    if not callable(construct):
      return insights

    n = EVALUATION_INPUTS["n"]
    _, radii, _ = construct(n, random_seed=42)
    nonzero = radii[radii > 1e-10]
    if len(nonzero) > 0:
      lines = [
          f"circles_placed={len(nonzero)}/{n}",
          f"min_radius={np.min(nonzero):.6f}",
          f"max_radius={np.max(nonzero):.6f}",
          f"mean_radius={np.mean(nonzero):.6f}",
          f"total_area={np.sum(np.pi * radii**2):.4f} (unit square=1.0)",
      ]
    else:
      lines = [f"circles_placed=0/{n}"]
    insights.append({
        "label": "solution_stats",
        "text": ", ".join(lines),
    })
  except Exception:  # pylint: disable=broad-exception-caught
    pass  # Diagnostics are best-effort; never fail the evaluation.
  return insights


def evaluate_program(code: str, timeout_seconds: int = 30) -> dict[str, Any]:
  """Execute candidate code and return the evaluation result.

  Args:
      code: Python source code of the candidate program.
      timeout_seconds: Max seconds before the evaluation is killed.

  Returns:
      A dict with keys:
        - "score": float on success, None on failure.
        - "insights": list of {"label": str, "text": str} dicts with
          evaluation feedback (stdout, stderr, errors). These map to
          the AlphaEvolveEvaluationInsights API field and are included
          in the LLM's evolution prompt for subsequent generations.
  """
  stdout_capture = io.StringIO()
  stderr_capture = io.StringIO()

  try:
    if hasattr(signal, "alarm"):
      signal.alarm(timeout_seconds)

    exec_namespace: dict[str, Any] = {
        "np": np,
        "Any": Any,
        "Mapping": Mapping,
    }

    # Capture stdout/stderr from the executed program.
    with (
        contextlib.redirect_stdout(stdout_capture),
        contextlib.redirect_stderr(stderr_capture),
    ):
      exec(code, exec_namespace)  # pylint: disable=exec-used
      eval_func = exec_namespace.get("evaluate")

      if callable(eval_func):
        result = eval_func(EVALUATION_INPUTS)
      else:
        return _failure(
            "Program missing callable 'evaluate' function",
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
        )

    stdout = stdout_capture.getvalue()
    stderr = stderr_capture.getvalue()
    raw_score = result.get(EVALUATION_METRIC)

    if raw_score is not None and raw_score != -np.inf:
      insights = []
      if stdout:
        insights.append({"label": "stdout", "text": stdout})
      if stderr:
        insights.append({"label": "stderr", "text": stderr})

      # Add problem-specific diagnostics to help the LLM understand
      # the solution quality and guide future improvements.
      insights.extend(_solution_diagnostics(exec_namespace))

      return {"score": float(raw_score), "insights": insights}

    return _failure(
        f"Metric '{EVALUATION_METRIC}' returned invalid value: {raw_score}",
        stdout=stdout,
        stderr=stderr,
    )

  except EvaluationTimeoutError:
    return _failure(
        f"Evaluation timed out after {timeout_seconds}s",
        tb=traceback.format_exc(),
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue(),
    )
  except Exception as e:  # pylint: disable=broad-exception-caught
    return _failure(
        f"Evaluation failed: {e}",
        tb=traceback.format_exc(),
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue(),
    )
  finally:
    if hasattr(signal, "alarm"):
      signal.alarm(0)


def _failure(
    error: str,
    tb: str | None = None,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, Any]:
  """Build a failure result dict with insights."""
  insights = [{"label": "error", "text": error}]
  if tb:
    insights.append({"label": "traceback", "text": tb})
  if stdout:
    insights.append({"label": "stdout", "text": stdout})
  if stderr:
    insights.append({"label": "stderr", "text": stderr})
  return {"score": None, "insights": insights}


def main():
  """CLI entry point. Called by the ae CLI.

  The ae CLI invokes this as:
    python evaluator.py --output-file <path> --input-program-file <path> [...]
  """
  parser = argparse.ArgumentParser()
  parser.add_argument("--output-file", required=True)
  parser.add_argument(
      "--input-program-file",
      required=True,
      action="append",
      help="Path to a program file to evaluate (repeatable).",
  )
  args = parser.parse_args()

  with open(args.input_program_file[0]) as f:
    code = f.read()

  result = evaluate_program(code)

  with open(args.output_file, "w") as f:
    json.dump(result, f)


if __name__ == "__main__":
  main()
