# Alpha Evolve Experiment Design Skill

AI agent skill for scaffolding AlphaEvolve experiments using a test-driven,
two-phase workflow.

## Overview

Automates the process of turning a high-level problem description into a
complete, verified experiment directory ready for the runner. It enforces a
strict separation between problem definition (Phase 1) and file generation
(Phase 2), ensuring robustness via Test-Driven Development (TDD).

This is one of three AlphaEvolve skills:

1.  **Experiment Design** (this skill) — Problem definition, initial program,
    evaluator
2.  **Experiment Runner** — Configuration, verification, launch
3.  **Experiment Monitor** — Evaluation loop, progress tracking, results

## The Design Process

The skill executes a strict two-phase process to ensure accuracy and prevent
"reward hacking" or evaluation bugs.

### Phase 1: Clarify (Architecture & Contract)

The agent works with the user to define the problem boundary before writing any
code.

1.  **Analyze Request:** Determine problem type (Optimization, Algorithm
    discovery, Speedup).
2.  **Propose Description:** Generate a `ExperimentDescription` (Pydantic model)
    specifying:
    -   Metric name and direction (maximize/minimize).
    -   Evaluation strategy (e.g., `FIXED_BENCHMARK`, `MULTI_RUNG_LADDER`).
    -   `eval_inputs` schema.
    -   Evolve block boundaries.
3.  **Clarify Constraints:** Ask targeted questions to resolve ambiguities.
4.  **Approval:** Save `.evolve/experiment_description.json` as the **single
    source of truth** for Phase 2.

### Phase 2: Implement (Test-Driven Development)

The agent generates files in a strict order, writing tests *before*
implementation and verifying at each step.

1.  `pyproject.toml` — Define dependencies (`numpy`, `pytest`).
2.  `test_program.py` — Tests defining the contract for the initial program.
3.  `initial_program.py` — The seed program with `# EVOLVE-BLOCK-START/END`
    markers.
4.  `test_evaluator.py` — Tests for the evaluator (handling syntax errors,
    timeouts).
5.  `evaluator.py` — The AlphaEvolve-compatible evaluator (sandboxed `exec()`,
    timeout guards).
6.  `example_evaluation.json` — Evaluator output running on the initial program.
7.  `problem_description.md` — Rigorous technical spec used in LLM prompts.
8.  `README.md` — Documentation for the experiment.
9.  **Final Verification** — Run all tests together. Green suite is required for
    completion.

## Handoff

-   **Input:** Loose problem description or code snippet.
-   **Output:** A verified project directory (e.g., `/tmp/knapsack_e2e`)
    containing standard files, ready for the `alpha_evolve_runner`.

## Prerequisites

-   Python 3.11+
-   `uv` for dependency management and project isolation.
-   `pytest` for verification.

## Skill Structure

```
alpha_evolve_experiment_design/
  README.md
  SKILL.md                  # Main skill instructions (Phase selection)
  resources/
    experiment_description_schema.py  # Pydantic schema for Phase 1
  references/
    phase_1_clarify.md      # Instructions for Clarify phase
    phase_2_implement.md    # Instructions for Implement phase
    evolve_block_guide.md   # Rules for EVOLVE-BLOCKs
    evaluator_patterns.md   # Patterns for sandboxing and timeouts
    multi_file_guide.md     # Multi-file experiment design
    numerical_stability.md  # Numerical-stability guidance
  examples/
    circle_packing/         # Reference implementation
```
