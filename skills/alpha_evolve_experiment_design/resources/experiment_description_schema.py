"""ExperimentDescription schema for AlphaEvolve experiment design.

This module defines the ExperimentDescription pydantic model — the complete
specification for an AlphaEvolve experiment. It is the sole output of Phase 1
(Clarify) and the sole input to Phase 2 (Implement).

Usage:
    from experiment_description_schema import ExperimentDescription

    desc = ExperimentDescription.model_validate_json(path.read_text())
"""

from __future__ import annotations

import enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator


class EvaluationStrategy(enum.Enum):
  """Evaluation strategy for scoring evolved programs.

  Each value contains a complete description sufficient to implement the
  strategy. To add a new strategy, add a new enum member with its
  implementation guide as the value.
  """

  FIXED_BENCHMARK = (
      "Run the evolved program against a single fixed set of inputs and "
      "compute a scalar score. Use when the problem has a single "
      "well-defined test case or when input size is fixed. The evaluator "
      "calls evaluate(eval_inputs) once and returns the metric value "
      "directly. Always include a timeout guard (signal.alarm) and return "
      "-10**12 for failures (timeout, exception, invalid output). Never "
      "return 0 for failures — the LLM will learn to trigger exceptions "
      "to get a safe score."
  )

  MULTI_RUNG_LADDER = (
      "Evaluate the program on progressively harder inputs. Define a list "
      "of 'rungs', each with increasing problem size and timeout. Start "
      "with the smallest rung; if it fails or times out, skip all "
      "remaining rungs and return -10**12 for skipped metrics. Return a "
      "separate metric for each rung (e.g., score_rung_0, score_rung_1). "
      "The primary optimization target should be the hardest rung's "
      "metric. Use when problem difficulty scales with input size "
      "(combinatorics, graph problems, optimization over N items). "
      "Example rungs: [{'n': 5, 'timeout': 2}, {'n': 20, 'timeout': 5}, "
      "{'n': 100, 'timeout': 30}]."
  )

  PARTIAL_CREDIT = (
      "Award continuous scores for partial correctness instead of binary "
      "pass/fail. This prevents evolution from stalling when no candidate "
      "achieves a perfect solution. Compute a score proportional to how "
      "close the solution is to the target (e.g., fraction of constraints "
      "satisfied, distance to optimal). Apply strict negative penalties "
      "(-1000 or lower) for constraint violations to prevent reward "
      "hacking. Return -10**12 only for total failures (exceptions, "
      "timeouts, invalid output types). Example: on_time_ratio for "
      "scheduling, fraction of valid edges for graph coloring."
  )

  COMPOSITE_MULTI_OBJECTIVE = (
      "Combine multiple competing objectives into a single scalar score "
      "for hill-climbing. AlphaEvolve maximizes a single fitness value; "
      "it cannot compute Pareto frontiers. Define weights for each "
      "objective and return a weighted sum as the primary 'score' metric. "
      "Also return the individual objectives as separate metrics for "
      "monitoring. Negate any objectives that should be minimized. "
      "Example: score = 0.4 * accuracy + 0.3 * (-latency) + 0.3 * "
      "throughput."
  )


class ExperimentDescription(BaseModel):
  """Complete specification for an AlphaEvolve experiment.

  This is the sole output of Phase 1 and the sole input to Phase 2.
  It must contain everything needed to generate all experiment files
  without further user interaction.
  """

  model_config = ConfigDict(
      # Serialize enums by name for human-readable JSON.
      use_enum_values=False,
  )

  @field_validator("evaluation_strategy", mode="before")
  @classmethod
  def _parse_strategy(cls, v: Any) -> EvaluationStrategy:
    """Accept both enum names ('FIXED_BENCHMARK') and enum instances."""
    if isinstance(v, EvaluationStrategy):
      return v
    if isinstance(v, str):
      try:
        return EvaluationStrategy[v]
      except KeyError:
        pass
      # Try matching by value
      for member in EvaluationStrategy:
        if member.value == v:
          return member
    raise ValueError(
        f"Invalid evaluation_strategy: {v!r}. "
        f"Expected one of: {[m.name for m in EvaluationStrategy]}"
    )

  # --- Identity ---

  name: Annotated[
      str,
      Field(
          description=(
              "Short snake_case slug used as the project directory name "
              "and pyproject.toml project name. Example: 'circle_packing'."
          ),
      ),
  ]

  title: Annotated[
      str,
      Field(
          description=(
              "Human-readable title for the experiment. Used in README.md "
              "and as the experiment title in the AlphaEvolve API. "
              "Example: 'Circle Packing in Unit Square'."
          ),
      ),
  ]

  problem_description: Annotated[
      str,
      Field(
          description=(
              "Full natural-language description of the problem. This is "
              "sent to the LLM as context for code generation. Be specific "
              "about inputs, outputs, constraints, and what 'better' means."
          ),
      ),
  ]

  # --- Optimization ---

  metric_name: Annotated[
      str,
      Field(
          description=(
              "Name of the primary metric returned by evaluate(). Must "
              "match the key in the dict returned by the initial program's "
              "evaluate() function. Example: 'sum_of_radii'. AlphaEvolve "
              "maximizes this value."
          ),
      ),
  ]

  metric_direction: Annotated[
      Literal["maximize", "minimize"],
      Field(
          description=(
              "Whether the raw metric should be maximized or minimized. "
              "If 'minimize', the evaluator negates the score before "
              "returning it to the API, since AlphaEvolve always maximizes."
          ),
      ),
  ]

  eval_inputs: Annotated[
      dict[str, Any],
      Field(
          description=(
              "Problem-specific parameters passed to the initial program's "
              "evaluate(eval_inputs) function. These define the test case: "
              "e.g. {'n': 26} for circle packing, {'signal_length': 500} "
              "for signal processing. Not an API field — used locally by "
              "the evaluator to invoke the evolved program's evaluate()."
          ),
      ),
  ]

  # --- Program structure ---

  language: Annotated[
      str,
      Field(
          default="python",
          description=(
              "Programming language for the initial program. Currently "
              "only 'python' is supported."
          ),
      ),
  ]

  allowed_imports: Annotated[
      list[str],
      Field(
          description=(
              "Python packages the evolved code is allowed to use. These "
              "are added to pyproject.toml dependencies and injected into "
              "the exec() namespace. Example: ['numpy', 'scipy']."
          ),
      ),
  ]

  forbidden_imports: Annotated[
      list[str],
      Field(
          default_factory=list,
          description=(
              "Python packages the evolved code must NOT use. Enforced "
              "via environment-level restriction: these packages are "
              "omitted from pyproject.toml so import fails with "
              "ModuleNotFoundError."
          ),
      ),
  ]

  initial_program_description: Annotated[
      str,
      Field(
          description=(
              "Description of what the initial (seed) program should do. "
              "This guides the agent in writing the solve() function — a "
              "naive but correct implementation that evolution will improve."
          ),
      ),
  ]

  evolve_block_description: Annotated[
      str,
      Field(
          description=(
              "Description of what goes inside the EVOLVE-BLOCK markers. "
              "This defines the search space — the code AlphaEvolve will "
              "mutate. Everything outside evolve blocks is frozen."
          ),
      ),
  ]

  # --- Evaluation strategy ---

  evaluation_strategy: Annotated[
      EvaluationStrategy,
      Field(
          description=(
              "Strategy for scoring evolved programs. Each enum value "
              "contains a complete implementation guide as its string "
              "value. Read it for implementation details."
          ),
      ),
  ]

  timeout_seconds: Annotated[
      int,
      Field(
          default=30,
          description=(
              "Maximum seconds before evaluation is killed via "
              "signal.alarm(). Programs exceeding this return -10**12."
          ),
      ),
  ]

  rungs: Annotated[
      list[dict[str, Any]] | None,
      Field(
          default=None,
          description=(
              "For MULTI_RUNG_LADDER strategy only. List of rung configs, "
              "each with problem-specific params and a 'timeout' key. "
              "Ordered from easiest to hardest. Example: "
              "[{'n': 5, 'timeout': 2}, {'n': 100, 'timeout': 30}]."
          ),
      ),
  ]

  # --- Dependencies ---

  python_version: Annotated[
      str,
      Field(
          default=">=3.11",
          description="Python version constraint for pyproject.toml.",
      ),
  ]

  dependencies: Annotated[
      list[str],
      Field(
          default_factory=lambda: ["numpy"],
          description=(
              "PyPI packages to include in pyproject.toml dependencies. "
              "These are available to the evolved code at runtime."
          ),
      ),
  ]

  # --- Source context (optimize-existing-code mode) ---

  source_file: Annotated[
      str | None,
      Field(
          default=None,
          description=(
              "For single-file 'optimize existing code' mode: path to "
              "the original source file. None for standalone/new-problem "
              "mode. Ignored when source_files is set."
          ),
      ),
  ]

  source_code: Annotated[
      str | None,
      Field(
          default=None,
          description=(
              "For single-file 'optimize existing code' mode: the full "
              "text of the function or code block to be optimized, "
              "extracted from source_file. This is the content that will "
              "be placed inside the EVOLVE-BLOCK in the initial program. "
              "None for standalone mode where the agent writes initial "
              "code from scratch. Ignored when source_files is set."
          ),
      ),
  ]

  # --- Multi-file source context ---

  source_files: Annotated[
      list[dict[str, Any]] | None,
      Field(
          default=None,
          description=(
              "For multi-file 'optimize existing code' mode: list of "
              "source files to include in the experiment. Each entry is "
              "a dict with keys: 'path' (original file path), 'content' "
              "(full file text), and 'has_evolve_block' (bool, True if "
              "this file contains or will contain EVOLVE-BLOCK markers). "
              "Files with has_evolve_block=True are the optimization "
              "targets. Files without markers are read-only context "
              "preserved unchanged by the backend. None for single-file "
              "or standalone mode. When set, source_file and source_code "
              "are ignored."
          ),
      ),
  ]

  # --- Additional constraints ---

  constraints: Annotated[
      list[str],
      Field(
          default_factory=list,
          description=(
              "Additional constraints in natural language. Examples: "
              "'Must run in O(n log n) time', 'No external API calls', "
              "'Solution must be deterministic'."
          ),
      ),
  ]
