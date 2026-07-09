# Evaluator Design Patterns

How to write `evaluate()` functions that drive productive evolution.

> **Core rule**: AlphaEvolve treats all use cases as **hill climbing**. It
> **maximizes** all metrics. To minimize something, negate the score.

---

## Understanding the Evaluation Architecture

An AlphaEvolve experiment has **two** evaluation layers:

### 1. `evaluate()` in the program file

Lives in `initial_program.py`. Called by the evaluator to score the candidate.
Returns a dict of metric names to scores.

```python
def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
    """Score the current solution."""
    result = solve(eval_inputs)
    return {"sum_of_radii": float(np.sum(result.radii))}
```

### 2. `evaluator.py` — the CLI-compatible evaluator script

Lives in `evaluator.py`. This is a **standalone CLI script** called by the
`ae` CLI during the evaluation control loop. The `ae` CLI invokes it as:

```bash
python evaluator.py --output-file /path/to/scores.json --program-dir /path/to/workspace
```

The `--program-dir` flag points to the directory containing all program
files. The evaluator finds and exec's `initial_program.py` in that
directory. The evaluator must:

1. Find `initial_program.py` in `--program-dir`
2. Execute the code, capturing stdout/stderr
3. Call the program's `evaluate()` function
4. Write `{"score": float|null, "insights": [...]}` to `--output-file`

```python
def evaluate_program(
    code: str, timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Execute candidate code and return evaluation result.

    Returns {"score": float|None, "insights": [{"label": ..., "text": ...}]}
    """
    ...

def main():
    """CLI entry point called by the ae CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--program-dir", required=True)
    args = parser.parse_args()

    # Add program dir to sys.path so flat imports resolve.
    sys.path.insert(0, args.program_dir)

    code = open(os.path.join(args.program_dir, "initial_program.py")).read()
    # evaluate, write result
```

The evaluation flow:

```
ae CLI → python evaluator.py --output-file X --program-dir workspace/
       → read workspace/initial_program.py, exec(code)
       → program.evaluate(inputs) → score(s)
       → write result JSON to X
```

The output file format depends on the number of metrics:

- **Single metric:** `{"score": float|null, "insights": [...]}`
- **Multiple metrics:** `{"scores": [{"metric": "name", "score": float}, ...], "insights": [...]}`

See the [Score format](#score-format) section below for details.

The `insights` list maps to `AlphaEvolveEvaluationInsights` in the API
and feeds into the LLM's evolution prompt. Always include stdout, stderr,
error messages, and tracebacks as labeled insights.

---

## Pattern 1: Constraining the Search Space with Evolve Blocks

Place hard constraints **outside** evolve blocks. Only mutable logic goes
inside.

```python
import numpy as np
from sklearn import linear_model as glm

# Hard constraint: must use linear model (outside evolve block)

# EVOLVE-BLOCK-START
def model_tuning():
    struct_model = glm.Lasso(alpha=0.1)
    return struct_model
# EVOLVE-BLOCK-END
```

**When to use**: Always. Hard constraints are structural, not scored.

---

## Pattern 2: Multi-Rung Evaluation Ladder

Test on progressively harder inputs. Early rungs filter bad programs cheaply.

```python
import signal

class TimeoutError(Exception):
    pass

def _timeout_handler(signum, frame):
    raise TimeoutError()

def evaluate(eval_inputs):
    rungs = [
        {'n': 5, 'timeout': 2},
        {'n': 20, 'timeout': 5},
        {'n': 100, 'timeout': 30},
    ]
    scores = {}
    for i, rung in enumerate(rungs):
        if hasattr(signal, 'alarm'):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(rung['timeout'])
        try:
            result = solve(rung['n'])
            scores[f'score_rung_{i}'] = score_solution(result)
        except (TimeoutError, Exception):
            scores[f'score_rung_{i}'] = -10**12
            break
        finally:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
    return scores
```

**When to use**: Problem difficulty scales with input size.

---

## Pattern 3: Timeout-Guarded Evaluation

**Always use this.** Without it, infinite loops block the evaluator.

> **Cross-platform note:** `signal.alarm` and `signal.SIGALRM` are only
> available on Unix (Linux/macOS). On Windows, guard their use with
> `hasattr(signal, 'alarm')`. The `ae` CLI provides its own process-level
> timeout via `subprocess.run(timeout=...)`, so the evaluator will still be
> killed if it hangs — the `signal.alarm` guard adds a finer-grained
> per-evaluation timeout *within* the evaluator process.

```python
import signal

def evaluate(eval_inputs):
    if hasattr(signal, 'alarm'):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(60)
    try:
        result = solve(eval_inputs)
        return {'score': compute_score(result)}
    except TimeoutError:
        return {'score': -10**12}
    except Exception:
        return {'score': -10**12}
    finally:
        if hasattr(signal, 'alarm'):
            signal.alarm(0)
```

---

## Pattern 4: Partial Credit

Award continuous scores instead of binary pass/fail.

```python
def evaluate(eval_inputs):
    schedule = solve(tasks)
    if schedule is None:
        return {'score': -10**12}

    on_time = sum(1 for t in schedule if t.finish <= t.deadline)
    valid = all(no_conflicts(schedule))

    # Strict penalty for constraint violation
    if not valid:
        return {'score': -1000.0}

    return {'score': on_time / len(tasks)}
```

**When to use**: Binary pass/fail creates a flat gradient (every candidate
gets `-10**12`), stalling evolution.

---

## Pattern 5: Negation for Minimization

AlphaEvolve always maximizes. Negate minimization targets.

```python
def evaluate(eval_inputs):
    route = solve(cities)
    total_distance = sum(dist(route[i], route[i+1]) for i in range(len(route)-1))
    return {'score': -total_distance}  # Negate: shorter is better
```

---

## Pattern 6: Combining Competing Objectives

Blend into a single scalar. AlphaEvolve cannot compute Pareto frontiers.

```python
def evaluate(eval_inputs):
    length = -compute_length(network)      # Negate (minimize)
    time = -compute_travel_time(network)   # Negate (minimize)

    score = 0.4 * length + 0.6 * time      # Single hill-climbing target

    return {
        'score': score,                    # Optimized by AlphaEvolve
        'total_length': length,            # Logged for monitoring
        'avg_travel_time': time,           # Logged for monitoring
    }
```

---

## Pattern 7: Validation → Verification → Evaluation Pipeline

Strict "feasible-then-optimal" pipeline:

```python
def evaluate(eval_inputs):
    # 1. Validation: does it run?
    try:
        solution = solve(eval_inputs)
    except Exception:
        return {'score': -10**12}

    if solution is None:
        return {'score': -10**12}

    # 2. Verification: is it valid?
    missing = count_missing_nodes(solution)
    if missing > 0:
        return {'score': -1000.0 * missing}

    # 3. Evaluation: how good is it?
    return {'score': compute_quality(solution)}
```

**When to use**: Always. Prevents the LLM from finding shortcuts.

---

## Pattern 8: Deterministic Evaluation

Same program → same score. No randomness, no time-dependence.

```python
def evaluate(eval_inputs):
    rng = np.random.RandomState(42)
    inputs = generate_test_case(rng)
    return {'score': compute_score(solve(inputs), inputs)}
```

---

## Evaluator Script Implementation

The evaluator is a **CLI-compatible script** that the `ae` CLI calls. It
must accept `--output-file` and `--program-dir`, and write
`{"score": float|null, "insights": [...]}` to the output file.

```python
"""Evaluator for {Problem Name}.

CLI-compatible evaluator for use with the ae CLI.
The ae CLI invokes this as:
  python evaluator.py --output-file <path> --program-dir <workspace>
"""

import argparse
import contextlib
import io
import json
import logging
import os
import signal
import sys
import traceback
from typing import Any, Mapping

import numpy as np

logger = logging.getLogger(__name__)

EVALUATION_METRIC = "sum_of_radii"
EVALUATION_INPUTS = {"n": 26}


class EvaluationTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise EvaluationTimeout("Evaluation timed out")


if hasattr(signal, 'alarm'):
    signal.signal(signal.SIGALRM, _timeout_handler)


def evaluate_program(
    code: str, timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Execute candidate code and return the evaluation result.

    Returns:
        Single metric: {"score": float|None, "insights": [...]}
        Multi-metric:  {"scores": [{"metric": str, "score": float}, ...],
                        "insights": [...]}
    """
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        if hasattr(signal, 'alarm'):
            signal.alarm(timeout_seconds)
        exec_namespace: dict[str, Any] = {
            "np": np, "Any": Any, "Mapping": Mapping,
        }

        with contextlib.redirect_stdout(stdout_capture), \
             contextlib.redirect_stderr(stderr_capture):
            exec(code, exec_namespace)
            eval_func = exec_namespace.get("evaluate")

            if callable(eval_func):
                result = eval_func(EVALUATION_INPUTS)
            else:
                return _failure(
                    "Program missing callable 'evaluate' function",
                    stdout=stdout_capture.getvalue(),
                    stderr=stderr_capture.getvalue(),
                )

        raw_score = result.get(EVALUATION_METRIC)
        stdout = stdout_capture.getvalue()
        stderr = stderr_capture.getvalue()

        if raw_score is not None and raw_score != -np.inf:
            insights = []
            if stdout:
                insights.append({"label": "stdout", "text": stdout})
            if stderr:
                insights.append({"label": "stderr", "text": stderr})
            return {"score": float(raw_score), "insights": insights}

        return _failure(
            f"Metric '{EVALUATION_METRIC}' invalid: {raw_score}",
            stdout=stdout, stderr=stderr,
        )

    except EvaluationTimeout:
        return _failure(
            f"Timed out after {timeout_seconds}s",
            tb=traceback.format_exc(),
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
        )
    except Exception as e:
        return _failure(
            f"Evaluation failed: {e}",
            tb=traceback.format_exc(),
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
        )
    finally:
        if hasattr(signal, 'alarm'):
            signal.alarm(0)


def _failure(error, tb=None, stdout="", stderr=""):
    """Build a failure result with insights."""
    insights = [{"label": "error", "text": error}]
    if tb:
        insights.append({"label": "traceback", "text": tb})
    if stdout:
        insights.append({"label": "stdout", "text": stdout})
    if stderr:
        insights.append({"label": "stderr", "text": stderr})
    return {"score": None, "insights": insights}


def main():
    """CLI entry point. Called by the ae CLI as:
      python evaluator.py --output-file <path> --program-dir <workspace>
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--program-dir", required=True)
    args = parser.parse_args()

    # Add program dir to sys.path so flat imports resolve.
    sys.path.insert(0, args.program_dir)

    program_path = os.path.join(args.program_dir, "initial_program.py")
    with open(program_path) as f:
        code = f.read()

    result = evaluate_program(code)

    with open(args.output_file, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
```

### Score format

The `ae` CLI supports two output formats. Choose based on your problem:

**Single metric** (most problems):

```json
{"score": 1.42, "insights": [...]}
```

**Multiple metrics** (composite objectives, e.g., accuracy + latency):

```json
{
  "scores": [
    {"metric": "accuracy", "score": 0.95},
    {"metric": "latency_ms", "score": -12.3}
  ],
  "insights": [...]
}
```

With multiple metrics, the first entry is the **primary score** used for
ranking candidates. Additional metrics are tracked and reported but don't
affect selection. Use multi-metric when you want to monitor secondary
objectives (e.g., solution size, constraint violations) alongside the
primary optimization target.

**On failure**, set score to `null` and include error insights:

```json
{
  "score": null,
  "insights": [
    {"label": "error", "text": "Evaluation failed: ZeroDivisionError"},
    {"label": "traceback", "text": "Traceback (most recent call last):\n..."},
    {"label": "stdout", "text": "Processing 26 circles...\n"},
    {"label": "stderr", "text": "WARNING: overlap detected\n"}
  ]
}
```

Supported insight labels:

| Label | When included | Purpose |
|---|---|---|
| `stdout` | Always (if non-empty) | Program's print output |
| `stderr` | Always (if non-empty) | Program's warning/debug output |
| `error` | On failure | Human-readable error message |
| `traceback` | On exception | Full Python stack trace |

### Writing effective insights

Insights are fed into the LLM's evolution prompt for subsequent
generations. They are the primary feedback channel: the LLM sees the
score *and* the insights when deciding how to modify the program next.
Good insights dramatically improve evolution quality.

**What to include on success:**

- **stdout**: Always capture. If the program prints diagnostics
  (iteration counts, intermediate values, constraint satisfaction),
  these help the LLM understand what the program did.
- **stderr**: Always capture. Warnings (e.g., numpy convergence
  warnings) signal areas the LLM could improve.
- **Validation details**: Add custom insights with diagnostic
  information about the solution quality. For example:

```python
insights = []
if stdout:
    insights.append({"label": "stdout", "text": stdout})

# Add problem-specific diagnostics
insights.append({
    "label": "constraint_violations",
    "text": f"{n_overlaps} circle overlaps detected, "
            f"{n_out_of_bounds} circles out of bounds",
})
insights.append({
    "label": "solution_stats",
    "text": f"min_radius={min_r:.4f}, max_radius={max_r:.4f}, "
            f"coverage={coverage:.1%} of unit square",
})
```

**What to include on failure:**

- **error**: A human-readable one-line summary. Be specific:
  `"ValueError: radii array has 25 elements, expected 26"` is better
  than `"Evaluation failed"`.
- **traceback**: The full `traceback.format_exc()` output. The LLM uses
  this to pinpoint the exact line and fix the bug.
- **stdout/stderr**: Even on failure, capture whatever the program
  printed before crashing -- partial output helps the LLM understand
  how far execution got.

**What NOT to include:**

- Large binary data or base64-encoded content (bloats the prompt).
- The full program source code (the LLM already has it).
- Repetitive logs (truncate after ~50 lines if needed).

**Insight size guidelines:**

- Keep each insight's `text` under ~2000 characters. The LLM's context
  window is finite and insights from many candidates compete for space.
- If stdout is very long (e.g., verbose logging), truncate to the last
  50 lines with a note: `"[truncated, showing last 50 lines]\n..."`.

### Common mistakes

| Mistake | Problem | Fix |
|---|---|---|
| Reading program from stdin | `ae` CLI does not pipe code via stdin | Use `--program-dir` arg, read `initial_program.py` |
| Importing from `evaluator` | `ae` copies evaluator to temp dir, self-import loops | Keep evaluator self-contained |
| Mixing `score` and `scores` keys | Ambiguous output | Use one format: `{"score": N}` for single metric, `{"scores": [...]}` for multiple |
| Missing `--output-file` arg | CLI can't find scores | Always use `argparse` with `--output-file` |
| Missing `if __name__` guard | Evaluator won't run as script | Always include `main()` entry point |
| Returning `NaN` or `Inf` scores | `NaN` is invalid JSON, crashes the CLI | Check `math.isnan()`/`math.isinf()`, return `null` score with error insight |

---

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| `except: return {'score': 0}` | LLM learns to trigger exceptions for safe scores | Return `None` score with error insights |
| All scores are `-10**12` | Too-strict validation, no gradient | Add partial credit (Pattern 4) |
| Everything scores high | Too-lenient validation | Add V-V-E pipeline (Pattern 7) |
| Non-deterministic scores | Random inputs confuse evolution | Use fixed seeds (Pattern 8) |
| String-matching imports | LLM bypasses with `__import__()` | Use environment restriction |
| Side effects in evaluate() | File I/O, network, global state | Keep evaluate() pure |
| Nested evolve blocks | Parser crash | Sequential blocks only |
| Markers on same line as code | Parser fails to extract | Own line, nothing else |

---


--------------------------------------------------------------------------------

## Decision Guide

| Situation | Pattern |
|---|---|
| Any problem | Timeout (3) + V-V-E (7) + Deterministic (8) |
| Difficulty scales with N | Multi-rung ladder (2) |
| Binary pass/fail stalls | Partial credit (4) |
| Minimization | Negation (5) |
| Multiple competing objectives | Composite (6) |
| Constraining search space | Evolve blocks (1) |
| Neural networks / gradient descent | See `references/numerical_stability.md` |
| Floating-point overflow/underflow | See `references/numerical_stability.md` |
