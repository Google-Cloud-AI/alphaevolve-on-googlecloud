"""Tests for the circle packing evaluator."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

from evaluator import evaluate_program


# Valid initial program code (must match initial_program.py)
VALID_PROGRAM = """
from typing import Any, Mapping
import numpy as np

def construct_packing(n, random_seed=42):
    rng = np.random.default_rng(random_seed)
    centers = rng.uniform(0.1, 0.9, size=(n, 2))
    radii = np.full(n, 0.01)
    return centers, radii, float(np.sum(radii))

def evaluate(eval_inputs):
    n = eval_inputs["n"]
    centers, radii, _ = construct_packing(n)
    return {"sum_of_radii": float(np.sum(radii))}
"""


class TestEvaluateProgramSuccess:
  """Tests for successful evaluation."""

  def test_returns_score_for_valid_program(self):
    """Valid programs get a dict with a positive numeric score."""
    result = evaluate_program(VALID_PROGRAM)
    assert isinstance(result["score"], float)
    assert result["score"] > 0

  def test_no_error_insights_on_success(self):
    """Successful evaluations have no error insights."""
    result = evaluate_program(VALID_PROGRAM)
    labels = [i["label"] for i in result["insights"]]
    assert "error" not in labels
    assert "traceback" not in labels

  def test_includes_solution_diagnostics(self):
    """Successful evaluations include solution_stats insight."""
    result = evaluate_program(VALID_PROGRAM)
    stats = [i for i in result["insights"] if i["label"] == "solution_stats"]
    assert len(stats) == 1
    assert "circles_placed=" in stats[0]["text"]
    assert "min_radius=" in stats[0]["text"]

  def test_captures_stdout(self):
    """stdout from the program is captured as an insight."""
    code = """
import sys
print("hello from program")
def evaluate(eval_inputs):
    return {"sum_of_radii": 1.0}
"""
    result = evaluate_program(code)
    assert result["score"] == 1.0
    stdout_insights = [i for i in result["insights"] if i["label"] == "stdout"]
    assert len(stdout_insights) == 1
    assert "hello from program" in stdout_insights[0]["text"]


class TestEvaluateProgramFailures:
  """Tests for failed evaluations -- must return error insights."""

  def test_syntax_error_returns_traceback(self):
    """Syntax errors produce error and traceback insights."""
    result = evaluate_program("def !!!")
    assert result["score"] is None
    labels = {i["label"] for i in result["insights"]}
    assert "error" in labels
    assert "traceback" in labels
    tb_text = next(
        i["text"] for i in result["insights"] if i["label"] == "traceback"
    )
    assert "SyntaxError" in tb_text

  def test_missing_evaluate_returns_error(self):
    """Programs without evaluate() produce an error insight."""
    result = evaluate_program("x = 1\ny = 2")
    assert result["score"] is None
    error_text = next(
        i["text"] for i in result["insights"] if i["label"] == "error"
    )
    assert "missing" in error_text.lower()

  def test_evaluate_that_raises_returns_traceback(self):
    """Programs whose evaluate() raises produce a full traceback."""
    code = """
def evaluate(eval_inputs):
    raise RuntimeError("intentional failure")
"""
    result = evaluate_program(code)
    assert result["score"] is None
    error_text = next(
        i["text"] for i in result["insights"] if i["label"] == "error"
    )
    assert "intentional failure" in error_text
    tb_text = next(
        i["text"] for i in result["insights"] if i["label"] == "traceback"
    )
    assert "RuntimeError" in tb_text

  def test_empty_program_returns_error(self):
    """Empty programs produce an error insight."""
    result = evaluate_program("")
    assert result["score"] is None
    labels = {i["label"] for i in result["insights"]}
    assert "error" in labels

  def test_wrong_metric_returns_error(self):
    """Programs returning wrong metric key produce an error insight."""
    code = """
def evaluate(eval_inputs):
    return {"wrong_metric": 42.0}
"""
    result = evaluate_program(code)
    assert result["score"] is None
    error_text = next(
        i["text"] for i in result["insights"] if i["label"] == "error"
    )
    assert "invalid value" in error_text.lower()

  def test_stderr_captured_on_failure(self):
    """stderr from failing programs is captured as an insight."""
    code = """
import sys
print("debug info", file=sys.stderr)
def evaluate(eval_inputs):
    raise ValueError("boom")
"""
    result = evaluate_program(code)
    assert result["score"] is None
    stderr_insights = [i for i in result["insights"] if i["label"] == "stderr"]
    assert len(stderr_insights) == 1
    assert "debug info" in stderr_insights[0]["text"]


class TestCLIInterface:
  """Tests for the CLI entry point (simulates ae CLI behavior)."""

  def test_cli_writes_score_on_success(self):
    """main() writes score + insights for valid programs."""
    tmpdir = tempfile.mkdtemp()
    try:
      prog_dst = os.path.join(tmpdir, "initial_program.py")
      shutil.copy("initial_program.py", prog_dst)
      shutil.copy("evaluator.py", os.path.join(tmpdir, "evaluator.py"))
      output_file = os.path.join(tmpdir, "scores.json")

      result = subprocess.run(
          [
              sys.executable,
              "evaluator.py",
              "--output-file",
              output_file,
              "--input-program-file",
              "initial_program.py",
          ],
          cwd=tmpdir,
          capture_output=True,
          text=True,
          timeout=60,
          check=False,
      )
      assert result.returncode == 0, f"stderr: {result.stderr}"

      with open(output_file) as f:
        data = json.load(f)
      assert isinstance(data["score"], float)
      assert data["score"] > 0
      assert "insights" in data
    finally:
      shutil.rmtree(tmpdir)

  def test_cli_writes_error_insights_on_failure(self):
    """main() writes error insights for broken programs."""
    tmpdir = tempfile.mkdtemp()
    try:
      broken = os.path.join(tmpdir, "broken.py")
      with open(broken, "w") as f:
        f.write("def !!!")
      shutil.copy("evaluator.py", os.path.join(tmpdir, "evaluator.py"))
      output_file = os.path.join(tmpdir, "scores.json")

      result = subprocess.run(
          [
              sys.executable,
              "evaluator.py",
              "--output-file",
              output_file,
              "--input-program-file",
              "broken.py",
          ],
          cwd=tmpdir,
          capture_output=True,
          text=True,
          timeout=60,
          check=False,
      )
      assert result.returncode == 0, f"stderr: {result.stderr}"

      with open(output_file) as f:
        data = json.load(f)
      assert data["score"] is None
      labels = {i["label"] for i in data["insights"]}
      assert "error" in labels
      assert "traceback" in labels
    finally:
      shutil.rmtree(tmpdir)
