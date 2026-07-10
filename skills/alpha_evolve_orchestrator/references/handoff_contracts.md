# Handoff Contracts Between Phases

This document defines the exact data contracts between the four phases of the
AlphaEvolve orchestrator. Each handoff is a set of artifacts that the
completing phase produces and the next phase consumes.

--------------------------------------------------------------------------------

## Handoff 1: Design -> Runner

The Design skill produces a project directory. The Runner skill needs three
specific files from it.

### Required artifacts

| Artifact | File | Contract |
|----------|------|----------|
| Program directory | The experiment directory (must contain `initial_program.py`) | `initial_program.py` is the main program with at least one `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` marker pair. For multi-file experiments, context files live alongside it in the same directory. |
| Evaluator | `evaluator.py` | CLI-compatible Python script. Accepts `--output-file <path>` and `--program-dir <path>`. Reads `initial_program.py` from the program directory. Writes `{"score": float\|null, "insights": [...]}` (single metric) or `{"scores": [...], "insights": [...]}` (multiple metrics) to the output file. Exports `evaluate_program(code, timeout_seconds) -> dict` for testing. |
| Problem description | `problem_description.md` | Markdown file with a detailed technical description of the optimization problem |

### Optional artifacts (produced by Design but not required by Runner)

| Artifact | File | Purpose |
|----------|------|---------|
| Experiment spec | `.evolve/experiment_description.json` | Pydantic model with all experiment parameters |
| Source map | `.evolve/source_map.json` | Maps experiment code regions to original source locations (for post-experiment integration). Only present when optimizing existing code. |
| Tests | `test_program.py`, `test_evaluator.py` | Pytest tests (already verified passing) |
| Sample output | `example_evaluation.json` | Example evaluator output for reference |
| Project config | `pyproject.toml` | `uv` project configuration |
| Documentation | `README.md` | Human-readable experiment documentation |

### Validation checklist (performed by Runner)

- [ ] Program file exists and contains `EVOLVE-BLOCK-START`/`END` markers
- [ ] `evaluator.py` exists and is runnable as
      `python evaluator.py --output-file X --program-dir .`
- [ ] `problem_description.md` exists and is non-empty
- [ ] Baseline evaluation via `ae program evaluate` succeeds and returns a
      valid score

--------------------------------------------------------------------------------

## Handoff 2: Runner -> Monitor

The Runner skill launches the experiment and produces a nickname. The Monitor
skill uses the nickname and evaluator to run the control loop.

### Required artifacts

| Artifact | Type | Contract |
|----------|------|----------|
| Experiment nickname | String | A short identifier like `brave-otter` assigned by the `ae` CLI |
| Evaluator file path | String | Absolute or relative path to the evaluator Python file |

### Validation checklist (performed by Monitor)

- [ ] `ae experiment describe <nickname>` succeeds and returns state ACTIVE
- [ ] Evaluator file exists at the specified path
- [ ] `ae experiment run` starts successfully with the evaluator

### What if the experiment is not ACTIVE?

| State | Action |
|-------|--------|
| ACTIVE | Proceed normally |
| INITIALIZED | Experiment was created but not started -- go back to Runner |
| PAUSED | Ask user if they want to resume |
| COMPLETED | Skip to final report |
| FAILED | Show error, offer to relaunch |
| CANCELLED | Show info, offer to create new experiment |

--------------------------------------------------------------------------------

## Handoff 3: Monitor -> Post-Experiment

The Monitor skill tracks the experiment until it reaches a terminal state.
The Post-Experiment skill uses the experiment identifier and project context
to analyze results, prompts the user if they want to integrate the changes, and
if yes helps them to integrate code.

### Required artifacts

| Artifact | Type | Contract |
|----------|------|----------|
| Experiment nickname | String | A short identifier like `brave-otter` that has reached a terminal state (COMPLETED, FAILED, or CANCELLED) |
| Project directory | String | Path to the experiment directory containing the evaluator, initial program, and `.evolve/` metadata |

### Optional artifacts

| Artifact | Type | Contract |
|----------|------|----------|
| Original source file | String | Path to the user's original source file that was optimized. Needed for code integration (Stage 3). May be absent for standalone experiments. |
| Evaluator file path | String | Path to `evaluator.py` in the project directory. Used for re-validation after integration. |

### Validation checklist (performed by Post-Experiment)

- [ ] `ae experiment describe <nickname>` succeeds and returns a terminal state
- [ ] `ae results best <nickname>` returns at least one program (for COMPLETED experiments)
- [ ] Project directory exists and contains `evaluator.py` (if integration is requested)
- [ ] Original source file exists (if integration is requested)

### What if the experiment is not in a terminal state?

| State | Action |
|-------|--------|
| COMPLETED | Proceed normally with full analysis + integration |
| FAILED | Proceed with partial analysis (show whatever data exists) |
| CANCELLED | Proceed with partial analysis |
| ACTIVE | Tell user the experiment is still running -- use Monitor skill |
| PAUSED | Ask user if they want to resume (Monitor) or analyze partial results |
| INITIALIZED | Tell user the experiment has not been started -- use Runner skill |

--------------------------------------------------------------------------------

## Direct Entry Points

Users may enter at Phase 2, Phase 3, or Phase 4 without going through earlier
phases. In these cases, the orchestrator must validate the required artifacts
directly.

### Entering at Phase 2 (Runner)

The user provides:

- `initial_program.py` with `EVOLVE-BLOCK` markers
- An evaluator file accepting `--output-file` and `--program-dir`
- A problem description (file or inline text)

If any artifact is missing or invalid, suggest going to Phase 1 (Design) to
create it properly.

### Entering at Phase 3 (Monitor)

The user provides:

- An experiment nickname, short ID, or full resource name
- (Optional) An evaluator file path -- needed only if the control loop is not
  already running

If the experiment does not exist, suggest going to Phase 2 (Runner) to create
and launch one.

### Entering at Phase 4 (Post-Experiment)

The user provides:

- An experiment nickname, short ID, or full resource name for a completed
  experiment
- (Optional) The project directory path
- (Optional) The original source file path for code integration

If the experiment is not in a terminal state, suggest going to Phase 3
(Monitor) to track it to completion first. If the experiment does not exist,
suggest going to Phase 2 (Runner) to create one.
