---
name: alpha-evolve-experiment-design
description: >
  Design AlphaEvolve experiments for the Cloud API. Takes a natural-language
  problem description and produces a complete, tested experiment directory
  ready for the experiment-runner skill. Triggers on: "design an experiment",
  "set up an AlphaEvolve experiment", "create an experiment for",
  "I want to evolve", "help me set up AlphaEvolve".
---

# Experiment Design Skill

You help users design AlphaEvolve experiments. You take a problem description
and produce a complete, tested project directory that the `experiment-runner`
skill can launch.

## Preconditions

-   The user has a **problem description** (natural language). It may be
    rigorous or vague.
-   *Optional*: existing code to optimize.
-   *Optional*: a target directory path. If not provided, ask. In general, an
    experiment should live in a dedicated new directory containing *only* the
    files created for the experiment.

## Postconditions

A project directory containing:

| File                                  | Purpose                              |
| ------------------------------------- | ------------------------------------ |
| `.evolve/experiment_description.json` | Complete experiment specification    |
| `.evolve/source_map.json`             | Maps code regions to original source |
:                                       : files (only when optimizing existing :
:                                       : code; enables post-experiment        :
:                                       : integration)                         :
| `initial_program.py`                  | Seed program with `EVOLVE-BLOCK`     |
:                                       : markers and `ORIGIN` comments        :
| `evaluator.py`                        | CLI-compatible evaluator script for  |
:                                       : the `ae` CLI                         :
| `problem_description.md`              | Detailed technical problem           |
:                                       : description (used in LLM prompts)    :
| `example_evaluation.json`             | Sample evaluator output              |
| `test_program.py`                     | Pytest tests for the initial program |
| `test_evaluator.py`                   | Pytest tests for the evaluator       |
| `pyproject.toml`                      | `uv` project configuration           |
| `README.md`                           | Experiment documentation             |
| `*.py` (multi-file only)              | Additional context files imported by |
:                                       : the initial program                  :

All pytest tests pass via `uv run pytest`.

--------------------------------------------------------------------------------

## Phases

The skill has exactly two phases. Complete Phase 1 before starting Phase 2.

### Phase 1 — Clarify

**Objective:** Fill the `ExperimentDescription` data structure through
conversation with the user.

**Gate:** Phase 1 is complete when `experiment_description.json` is written to
`project_dir/.evolve/`.

**Details:** Read `references/phase_1_clarify.md` when you reach this phase.

### Phase 2 — Implement

**Objective:** Generate all project files and verify they work.

**Input contract:** The `ExperimentDescription` is the **only input** to
Phase 2. It must contain everything needed to generate all files. If information
is missing, Phase 1 was incomplete — go back and fix it.

**Gate:** Phase 2 is complete when `uv run pytest` passes in the project
directory.

**Details:** Read `references/phase_2_implement.md` when you reach this phase.

--------------------------------------------------------------------------------

## Critical Rules

1.  **Phase 1 is conversation only.** Do not create code files during Phase 1.
    The only file written is `experiment_description.json`.

2.  **Phase 2 requires no user interaction.** The `ExperimentDescription`
    contains everything needed. If you find yourself wanting to ask a question,
    Phase 1 was incomplete.

3.  **Tests first.** In Phase 2, write tests before the code they test.

4.  **Never execute user code directly.** Syntax-check with `uv run python -c
    "import ast; ast.parse(open('file.py').read())"` only. Evaluation happens
    through `uv run pytest` which exercises the code in a controlled way.

    > **CRITICAL: ALWAYS use `uv run` — NEVER bare `python3`.** Do NOT run
    > `python3 evaluator.py`, `python3 test_program.py`, or `python3 -c "from
    > evaluator import ..."`. Always use `uv run python` or `uv run pytest`.
    > This ensures the correct virtual environment and dependencies are
    > available and works cross-platform (`python3` is not always available on
    > Windows). Using bare `python3` can silently use the wrong Python or miss
    > project dependencies.

5.  **The evaluator must be CLI-compatible.** The evaluator file must be
    runnable as `uv run python evaluator.py --output-file <path> --program-dir
    <path>`. It must export `evaluate_program(code, timeout_seconds=30) -> dict`
    for testing (returning `{"score": float|None, "insights": [...]}`), and
    include a `main()` entry point that reads `initial_program.py` from
    `--program-dir`, evaluates it, and writes the result dict to
    `--output-file`. Insights capture stdout, stderr, errors, and tracebacks as
    `{"label": str, "text": str}` dicts that map to the
    `AlphaEvolveEvaluationInsights` API field.

6.  **AlphaEvolve always maximizes.** If the user wants to minimize a metric,
    the evaluator must negate the score.

7.  **Handle non-finite scores.** The evaluator MUST check for `NaN` and `Inf`
    scores (common with neural network training) and return `null` with an error
    insight instead. `NaN` in JSON is invalid and will crash the CLI. Use
    `math.isnan()` and `math.isinf()` before returning.

8.  **Validate EVOLVE-BLOCK markers.** Before declaring Phase 2 complete, verify
    that the initial program contains at least one valid `# EVOLVE-BLOCK-START`
    / `# EVOLVE-BLOCK-END` marker pair. The exact syntax matters --
    `EVOLVE_BLOCK_START` (underscores) or other variants will be rejected by the
    API.

9.  **Use `uv` for all project management.** Projects use `pyproject.toml`,
    dependencies are installed via `uv`, tests run via `uv run pytest`. **Never
    skip `pyproject.toml` creation or test files.** All files listed in Phase 2
    Postconditions are mandatory.

10. **Be concise.** Do not narrate your internal reasoning. State what you are
    doing, show results, ask questions when needed.

11. **Never initiate version-control or commit workflows.** Experiment files are
    local working artifacts. Do not stage or commit changes, search for related
    issues, or draft commit messages. Only create a pull request if the user
    explicitly requests it.

--------------------------------------------------------------------------------

## Key References

| Reference                                    | When to read                  |
| -------------------------------------------- | ----------------------------- |
| `references/phase_1_clarify.md`              | At the start of Phase 1       |
| `references/phase_2_implement.md`            | At the start of Phase 2       |
| `references/evaluator_patterns.md`           | When designing the evaluator  |
| `references/numerical_stability.md`          | When the problem involves     |
:                                              : neural networks, iterative    :
:                                              : optimization, or floating     :
:                                              : point arithmetic              :
| `references/evolve_block_guide.md`           | When writing the initial      |
:                                              : program                       :
| `references/multi_file_guide.md`             | When the user points to a     |
:                                              : directory or multiple files   :
| `resources/experiment_description_schema.py` | For the ExperimentDescription |
:                                              : model                         :
| `examples/circle_packing/`                   | Complete worked example       |

--------------------------------------------------------------------------------

## Constraints

-   **Isolation Principle**: Never modify original workspace source files
    directly. Target code MUST be extracted/copied into program files in the
    experiment directory. For single-file experiments, this means copying into
    `initial_program.py`. For multi-file experiments, this means copying into
    multiple .py files in the experiment directory.
-   **No external imports.** Program files and `evaluator.py` must NEVER import
    from the user's source tree (e.g., `from myproject.models import ...`). The
    `ae` CLI copies files to a temporary directory for evaluation, so imports
    relative to the original codebase will fail with `ModuleNotFoundError`.
    Imports between bundled program files (e.g., `import layers` where
    `layers.py` is another file in the experiment directory) ARE allowed. Only
    stdlib, `pyproject.toml` dependencies, and other bundled program files are
    available at evaluation time. See `references/multi_file_guide.md` for
    multi-file import constraints.
-   Never modify the evaluation metric or scoring logic without user consent.
-   Initial programs MUST be standalone runnable Python files.
-   Always use `uv run python` (or `uv run pytest`) instead of invoking a bare
    Python interpreter. This ensures the correct virtual environment and works
    cross-platform (`python3` is not always available on Windows).
-   **Reward Hacking**: Always verify the semantic validity of evolved code
    during integration to ensure it represents a genuine discovery rather than
    an exploit of the scoring function.
