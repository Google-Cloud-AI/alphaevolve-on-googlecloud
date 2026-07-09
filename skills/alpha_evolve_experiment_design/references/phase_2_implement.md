# Phase 2 — Implement

> [!IMPORTANT]
> **Single-input contract.** The `ExperimentDescription` in
> `project_dir/.evolve/experiment_description.json` is the **only input**
> to this phase. It contains everything needed to generate all output files.
> Do not ask the user any questions. If information is missing, Phase 1 was
> incomplete — go back and fix it.

## Objective

Generate all project files using a test-driven approach. Write tests first,
then implementation, verifying at each step.

---

## File Generation Order

Write files in this exact order. Do not skip steps.

### Step 1: `pyproject.toml`

Create the `uv` project file using values from `ExperimentDescription`:

```toml
[project]
name = "{desc.name}"
version = "0.1.0"
description = "{desc.title}"
requires-python = "{desc.python_version or '>=3.10'}"
dependencies = {desc.dependencies + ["pytest"]}
```

> **No `[build-system]` needed.** Experiment projects are not installable
> packages — they are flat script directories managed by `uv` for dependency
> resolution only. Omitting the build backend avoids setuptools
> auto-discovery errors (e.g., "Multiple top-level modules discovered in a
> flat-layout") and speeds up `uv sync`.

**Dependency version guidance:** Use unpinned or loosely pinned versions
(e.g., `"numpy"` or `"numpy>=1.24"`) rather than exact pins like
`"numpy==1.26.4"`. Exact pins can trigger source builds on newer Python
versions (e.g., Python 3.13), causing long waits during `uv sync`.

Then initialize the project:

```bash
cd project_dir && uv sync
```

This creates the virtual environment and installs dependencies.

---

### Step 2: `test_program.py`

Write pytest tests for the initial program **before writing the program**.
The tests define the contract:

```python
"""Tests for the initial program."""
import pytest

from initial_program import evaluate, solve


def test_solve_returns_valid_output():
    """solve() returns output of the expected type/shape."""
    ...

def test_evaluate_returns_dict_with_metric():
    """evaluate() returns a dict containing the expected metric key."""
    result = evaluate(EVAL_INPUTS)
    assert "{desc.metric_name}" in result

def test_evaluate_returns_finite_score():
    """evaluate() returns a finite numeric score for the initial program."""
    result = evaluate(EVAL_INPUTS)
    score = result["{desc.metric_name}"]
    assert isinstance(score, (int, float))
    assert score > -1e11  # Not a failure sentinel
```

Tailor tests to the specific problem using `desc.eval_inputs` and
`desc.metric_name`.

---

### Step 3: Program Files

Write the seed program file(s). Read `references/evolve_block_guide.md` for
EVOLVE-BLOCK rules.

#### Single-file mode (default)

When `desc.source_files` is not set, generate a single `initial_program.py`:

```python
"""Initial program for {desc.title}.

{desc.problem_description}
"""
from typing import Any, Mapping

# EVOLVE-BLOCK-START

{desc.evolve_block_description - implement as code}

# EVOLVE-BLOCK-END


def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
    """Score the solution. Returns {{metric_name: score}}.

    This function is called by the evaluator. It is OUTSIDE the
    evolve block - its contract is fixed.
    """
    result = solve(eval_inputs)
    # validation logic here
    return {"{desc.metric_name}": score}
```

**If optimizing existing code** (`desc.source_file` is set), add an
`ORIGIN` comment before each code region that was extracted from the
user's codebase. See the **Provenance Tracking** section below.

#### Multi-file mode

When `desc.source_files` is set, generate multiple .py files in the project
directory. Read `references/multi_file_guide.md` for multi-file constraints.

**The main file must be named `initial_program.py`.** It stitches the
cherry-picked context files together: imports from them, contains (or
imports) the EVOLVE-BLOCK code, and defines the `evaluate()` function.
The evaluator always exec's `initial_program.py` by name.

For each entry in `source_files`:

- If `has_evolve_block` is True: write the file with EVOLVE-BLOCK markers
  (this may be `initial_program.py` itself or a context file it imports)
- If `has_evolve_block` is False: write the file as-is (read-only context)

**Add `ORIGIN` comments** for every code region extracted from the user's
codebase. See the **Provenance Tracking** section below.

**Multi-file rules:**
1. `initial_program.py` imports from context files. Context files must NOT
   import back from `initial_program.py` -- it is exec'd, not imported.
2. All files are placed **flat in one directory**. Use `import <filename>`
   (without `.py`). No package-style imports.
3. `initial_program.py` must contain the `evaluate()` function.
4. Only `initial_program.py` (and any file with EVOLVE-BLOCK) will be
   modified by evolution. Context files are preserved unchanged.

**Rules (all modes):**
1. `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` markers on their own lines.
2. `evaluate()` is **outside** the evolve block — its interface is fixed.
3. The solve/core function is **inside** the evolve block.
4. Program files must be **self-contained as a group** — they must not
   import from the user's source tree or any path outside the experiment
   directory. The `ae` CLI copies files to a temp directory for evaluation.
   Only stdlib, `pyproject.toml` dependencies, and other bundled program
   files are available.
5. If `desc.source_code` is set, use it as the initial evolve block content.

**Verify:**
```bash
uv run python -c "import ast; ast.parse(open('initial_program.py').read())"
uv run pytest test_program.py -v
```

Both must pass before proceeding.

---

### Step 4: `test_evaluator.py`

Write pytest tests for the evaluator:

```python
"""Tests for the evaluator."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from evaluator import evaluate_program


def test_evaluate_program_returns_score_and_insights():
    """evaluate_program() returns a dict with score and insights."""
    result = evaluate_program(INITIAL_CODE)
    assert isinstance(result["score"], float)
    assert result["score"] > 0
    assert isinstance(result["insights"], list)

def test_evaluate_program_returns_error_insights_on_failure():
    """evaluate_program() returns error insights for bad code."""
    result = evaluate_program("def !!!")
    assert result["score"] is None
    labels = {i["label"] for i in result["insights"]}
    assert "error" in labels
    assert "traceback" in labels

def test_evaluate_program_captures_stdout():
    """stdout from the program is captured as an insight."""
    code = 'print("hello")\ndef evaluate(ei): return {"%s": 1.0}'
    result = evaluate_program(code % "{desc.metric_name}")
    stdout = [i for i in result["insights"] if i["label"] == "stdout"]
    assert len(stdout) == 1

def test_cli_main_writes_output_file():
    """main() writes a valid JSON output file."""
    tmpdir = tempfile.mkdtemp()
    try:
        # Copy ALL program files and the evaluator to the temp dir.
        # For multi-file experiments, context files must also be copied
        # so that imports resolve correctly in the evaluator subprocess.
        program_files = ["initial_program.py"]  # Add context files here
        for pf in program_files:
            if os.path.exists(pf):
                shutil.copy(pf, os.path.join(tmpdir, pf))
        shutil.copy("evaluator.py", os.path.join(tmpdir, "evaluator.py"))
        output_file = os.path.join(tmpdir, "scores.json")

        # Use sys.executable so the subprocess inherits the current
        # virtual environment. Do NOT hardcode "python3" — it is
        # unavailable on Windows.
        cmd = [sys.executable, "evaluator.py",
               "--output-file", output_file,
               "--program-dir", tmpdir]

        result = subprocess.run(
            cmd,
            cwd=tmpdir, capture_output=True, text=True, timeout=60,
            check=False,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        with open(output_file) as f:
            data = json.load(f)
        assert isinstance(data["score"], (int, float))
        assert "insights" in data
    finally:
        shutil.rmtree(tmpdir)
```

---

### Step 5: `evaluator.py`

Write the evaluation script. Read `references/evaluator_patterns.md` for
patterns. If the problem involves neural networks, iterative optimization,
or floating-point arithmetic, also read
`references/numerical_stability.md` and apply the relevant patterns
(score validation guard, gradient clipping, NaN detection).

> **IMPORTANT:** The evaluator must be a **CLI-compatible script** that works
> with the `ae` CLI. The `ae` CLI calls it as:
> ```
> python evaluator.py --output-file /path/to/scores.json --program-dir <workspace>
> ```
> The `--program-dir` flag points to the directory containing `initial_program.py`
> and any context files. The evaluator reads and exec's `initial_program.py`.

**Contract:**

```python
def evaluate_program(
    code: str, timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Execute candidate code and return the evaluation result.

    Args:
        code: Python source code of the candidate program.
        timeout_seconds: Max seconds before kill.

    Returns:
        A dict with keys:
          - "score": float on success, None on failure. Use this for
            single-metric problems. For multi-metric problems, use
            "scores" instead (see evaluator_patterns.md Score format).
          - "insights": list of {"label": str, "text": str} dicts.
            These map to the AlphaEvolveEvaluationInsights API field.
            Include stdout, stderr, error messages, and tracebacks.
    """
    # ... run candidate code, get raw_score ...

    # MANDATORY: guard against non-finite scores before returning.
    # NaN and Inf are not valid JSON and will crash the ae CLI.
    if raw_score is None:
        return _failure("No score returned")
    if math.isnan(raw_score) or math.isinf(raw_score):
        return _failure(f"Non-finite score: {raw_score}")
    return {"score": float(raw_score), "insights": insights}

def main():
    """CLI entry point. Called by the ae CLI."""
    # Parse --output-file and --program-dir arguments
    # Read initial_program.py from --program-dir, call evaluate_program(), write result
```

The file must be runnable as a script (`if __name__ == "__main__": main()`).

**Implementation pattern:**

1. Parse `--output-file` and `--program-dir` (required) with `argparse`
2. Add `args.program_dir` to `sys.path` so flat imports resolve
3. Read `initial_program.py` from `args.program_dir`
3. Capture stdout/stderr with `contextlib.redirect_stdout/stderr`
4. `exec()` the code in a sandboxed namespace
5. Call the program's `evaluate(eval_inputs)` function
6. Extract the metric value
7. If `desc.metric_direction == "minimize"`, negate the score
8. Build insights list from stdout, stderr, errors, tracebacks
9. Write result to `--output-file`: `{"score": float|null, "insights": [...]}`
   for single metric, or `{"scores": [...], "insights": [...]}` for multiple

**Always include:**

-   `import contextlib, io, math, traceback` for stdout/stderr capture and
    traces
-   `signal.alarm(timeout_seconds)` timeout guard — **must be guarded** with
    `hasattr(signal, 'alarm')` because `signal.alarm` is not available on
    Windows. The `ae` CLI provides a process-level timeout as a fallback.
-   `try/except` returning `{"score": None, "insights": [error + traceback]}`
-   `finally: signal.alarm(0)` to cancel the alarm (also guarded)
-   `argparse` with `--output-file` and `--program-dir` (both required)
-   A `_failure()` helper to build error results consistently
-   **MANDATORY:** `math.isnan()` / `math.isinf()` guard before returning any
    score. `NaN` and `Inf` are not valid JSON and will crash the `ae` CLI
    controller loop, stopping the entire experiment. Always return `None` score
    with an error insight for non-finite values

**Verify:**
```bash
uv run python -c "import ast; ast.parse(open('evaluator.py').read())"
uv run pytest test_evaluator.py -v
```

---

### Step 6: `example_evaluation.json`

Run the evaluator on the initial program and save the output:

```python
import json
from evaluator import evaluate_program

code = open("initial_program.py").read()
result = evaluate_program(code)
with open("example_evaluation.json", "w") as f:
    json.dump(result, f, indent=2)
```

Execute this via `uv run python -c '...'` and verify the output file contains a
valid score and insights list.

---

### Step 7: `problem_description.md`

Write a detailed technical description of the problem. This file will be
included in LLM prompts during evolution, so it should give the model all
the context it needs to generate good solutions.

**Structure:**

```markdown
# {desc.title}

## Problem Statement

{Rigorous definition: inputs, outputs, objective, constraints}

## Formal Specification

{Mathematical formulation if applicable: variables, objective function,
constraint equations}

## Evaluation

- **Metric:** `{desc.metric_name}` ({desc.metric_direction})
- **Strategy:** {desc.evaluation_strategy description}
- **Inputs:** {desc.eval_inputs explained}

## Solution Guidance

{Hints about known approaches, what makes a good solution, common
pitfalls to avoid. This section helps the LLM explore promising
directions.}
```

Draw content from `desc.problem_description`, `desc.constraints`, and
`desc.evolve_block_description`, but expand and formalize them. The
problem_description field in ExperimentDescription is a summary; this
file is the full specification.

---

### Provenance Tracking

> **CRITICAL for post-experiment integration.** Without provenance, the
> post-experiment skill cannot automatically apply evolved code back to
> the correct locations in the user's codebase. This section applies
> whenever code is extracted from existing source files (`source_file` or
> `source_files` is set in the ExperimentDescription). Skip this for
> standalone new-problem experiments.

#### ORIGIN Comments

Add `# ORIGIN: <path>::<symbol> (lines <start>-<end>)` comments in the
generated program files to record where each code region was extracted
from. These comments are placed **outside** EVOLVE-BLOCK markers so they
survive evolution unchanged.

**Format:**

```python
# ORIGIN: <relative_or_absolute_path>::<function_or_class_name> (lines <start>-<end>)
```

**Placement rules:**

1. Place the `ORIGIN` comment on the line **immediately before** the code
   region it describes (before EVOLVE-BLOCK-START if the region is an
   evolve block).
2. For inlined code (Extract and Isolate), place one `ORIGIN` comment per
   extracted function or class.
3. For multi-file bundle mode, place one `ORIGIN` comment at the top of
   each generated file that was copied from the user's codebase.

**Examples:**

Single-file extraction:
```python
# ORIGIN: src/core/activation.py::relu (lines 12-18)
# EVOLVE-BLOCK-START
def relu(x):
    return np.maximum(0, x)
# EVOLVE-BLOCK-END

# ORIGIN: src/models/layers.py::Dense (lines 5-42)
class Dense:
    def __init__(self, input_size, output_size):
        ...
```

Multi-file bundle:
```python
# layers.py
# ORIGIN: src/models/layers.py (full file)
class Dense:
    ...
```

Extract and Isolate (multiple functions inlined into one file):
```python
# ORIGIN: src/models/layers.py::Dense (lines 5-42)
class Dense:
    def __init__(self, input_size, output_size):
        ...

# ORIGIN: src/utils/math_utils.py::clamp (lines 8-10)
def clamp(x, lo, hi):
    return np.clip(x, lo, hi)

# ORIGIN: src/core/activation.py::relu (lines 12-18)
# EVOLVE-BLOCK-START
def relu(x):
    return np.maximum(0, x)
# EVOLVE-BLOCK-END
```

#### Source Map (`source_map.json`)

After generating all program files, write a structured source map to
`.evolve/source_map.json`. This is the authoritative integration
reference used by the post-experiment skill.

```json
{
  "version": 1,
  "experiment_dir": "<absolute_path_to_experiment_dir>",
  "mappings": [
    {
      "experiment_file": "initial_program.py",
      "symbol": "relu",
      "symbol_type": "function",
      "is_evolve_block": true,
      "original_file": "src/core/activation.py",
      "original_lines": [12, 18],
      "original_symbol": "relu",
      "integration_mode": "function_replacement"
    },
    {
      "experiment_file": "initial_program.py",
      "symbol": "Dense",
      "symbol_type": "class",
      "is_evolve_block": false,
      "original_file": "src/models/layers.py",
      "original_lines": [5, 42],
      "original_symbol": "Dense",
      "integration_mode": "skip"
    },
    {
      "experiment_file": "layers.py",
      "symbol": null,
      "symbol_type": "file",
      "is_evolve_block": false,
      "original_file": "src/models/layers.py",
      "original_lines": null,
      "original_symbol": null,
      "integration_mode": "full_file_replacement"
    }
  ],
  "strip_evolve_markers": true
}
```

**Fields:**

| Field | Description |
|-------|-------------|
| `experiment_file` | Filename in the experiment directory |
| `symbol` | Function/class name (null for full-file mappings) |
| `symbol_type` | `"function"`, `"class"`, or `"file"` |
| `is_evolve_block` | Whether this symbol is inside an EVOLVE-BLOCK |
| `original_file` | Path to the original source file (relative to workspace root) |
| `original_lines` | `[start, end]` line numbers in the original file (null for full-file) |
| `original_symbol` | Symbol name in the original file (may differ if renamed for flat imports) |
| `integration_mode` | How to apply changes back: `"function_replacement"`, `"full_file_replacement"`, `"evolve_block_replacement"`, or `"skip"` |
| `strip_evolve_markers` | Whether to remove EVOLVE-BLOCK markers during integration (always true) |

**Integration mode values:**

- `function_replacement`: Replace the function/class body in the original
  file at the specified location.
- `full_file_replacement`: Replace the entire original file with the
  evolved version.
- `evolve_block_replacement`: The original file has EVOLVE-BLOCK markers;
  replace the content between them.
- `skip`: This region was not evolved (context only). Do not modify the
  original file.

**Rules:**

1. Only generate `source_map.json` when `source_file` or `source_files`
   is set. For standalone experiments, omit it.
2. Entries with `is_evolve_block: false` should have
   `integration_mode: "skip"` unless they are full-file mappings in
   multi-file bundle mode.
3. The `original_lines` field uses 1-based line numbers matching what
   the user sees in their editor.

---

### Step 8: `README.md`

Generate documentation:

```markdown
# {desc.title}

{Brief problem description - 1-2 paragraphs}

## Files

| File | Purpose |
|---|---|
| `initial_program.py` | Seed program with EVOLVE-BLOCK markers |
| `evaluator.py` | CLI-compatible evaluator for the `ae` CLI |
| `problem_description.md` | Detailed problem specification (used in LLM prompts) |
| `test_program.py` | Tests for the initial program |
| `test_evaluator.py` | Tests for the evaluator |
| `example_evaluation.json` | Sample evaluator output |
| `pyproject.toml` | Project configuration |

## Running Tests

```bash
uv sync
uv run pytest -v
```

## Metric

- **Name:** `{desc.metric_name}`
- **Direction:** {desc.metric_direction}
- **Evaluation strategy:** {desc.evaluation_strategy}

## Launching

Use the `experiment-runner` skill or the `ae` CLI to launch this experiment.
```

---

### Step 9: Final Verification

Run all tests together:

```bash
cd project_dir && uv run pytest -v
```

**All tests must pass.** If any fail, fix the code and re-run. Do not
proceed until green.

> [!IMPORTANT]
> Phase 2 is complete. Inform the user that the experiment is ready and
> can be launched with the `experiment-runner` skill.
