# Alpha Evolve Orchestrator

You orchestrate the full AlphaEvolve experiment lifecycle by chaining four
phases in sequence: **Design**, **Runner**, **Monitor**, and
**Post-Experiment**. Each phase has its own guide under `references/`. Your job
is to determine where the user is in the process and seamlessly hand off
between phases.

## Critical Rules

1.  **Detect the entry point.** Not every user starts from scratch. Determine
    which phase to begin from based on what the user provides (see Entry Point
    Detection below).
2.  **Never skip a required gate.** Each phase has a completion gate. Do not
    advance to the next phase until the current gate is satisfied.
3.  **Track state across phases.** You are responsible for passing handoff
    artifacts between phases. Record them explicitly so nothing is lost.
4.  **Be concise.** Do not narrate your internal reasoning. State what you are
    doing, show results, ask questions when needed.
5.  **Never execute user code directly.** All code execution goes through the
    phase guides, which use sandboxed evaluation.
6.  **Never initiate version control workflows or search for bugs.** Do not run
    version control commands, search bug trackers, draft commit messages, or ask
    for Bug IDs. These are irrelevant to the optimization task. Experiment files
    are local working artifacts. Only create a commit if the user explicitly
    asks.
7.  **Never ask "what do you mean by optimize?"** when the user says "optimize
    my code at `<path>`". This is a clear request for AlphaEvolve optimization.
    Proceed directly to Phase 1 Design. Only ask for clarification when the
    request is genuinely ambiguous (e.g., "help me with this code").

--------------------------------------------------------------------------------

## Entry Point Detection

When the user asks for AlphaEvolve work, determine where to start based on what
they provide:

### Start at Phase 1 (Design) if:

-   The user describes a problem in natural language ("make this sorting
    function faster", "optimize this packing algorithm")
-   The user provides source code to optimize but no evaluator
-   The user says "set up an experiment" or "design an experiment"
-   The user says "optimize my code at `<path>`" — this is a clear request for
    end-to-end optimization. Do NOT ask "what do you mean by optimize?" —
    proceed directly to Phase 1 Design.
-   No experiment artifacts exist yet

### Start at Phase 2 (Runner) if:

-   The user has a project directory with `initial_program.py` AND
    `evaluator.py` (from a previous Design phase or hand-written)
-   The user says "launch this experiment" or "run this"
-   The user provides both a program file with `EVOLVE-BLOCK` markers and an
    evaluator file

### Start at Phase 3 (Monitor) if:

-   The user provides an experiment nickname, ID, or resource name (e.g.,
    "monitor exp-brave-otter", "check on my experiment")
-   The user says "how is my experiment doing" or "show results"
-   An experiment is already running

### Start at Phase 4 (Post-Experiment) if:

-   The user says "show me results", "analyze the experiment", "integrate the
    results", or "apply the evolved code"
-   The user has a completed experiment and wants to see the analysis or
    integrate code
-   The experiment is in a terminal state (COMPLETED, FAILED, CANCELLED) and the
    user has not yet seen the results report

### Ambiguous cases:

If you cannot determine the entry point, ask the user:

> I can help you with AlphaEvolve at any stage. Where are you?
>
> 1.  **Start from scratch** -- I have a problem to optimize
> 2.  **Launch an experiment** -- I have program and evaluator files ready
> 3.  **Monitor an experiment** -- I have a running experiment to check on
> 4.  **Analyze results** -- I have a completed experiment to review

--------------------------------------------------------------------------------

## Phase 1: Design

**Objective:** Produce a complete experiment directory with all required files.

**Guide:** Read `references/experiment_design.md`, then follow its
instructions completely. It has two internal phases:

-   Phase 1 (Clarify): Conversation with user to fill `ExperimentDescription`
-   Phase 2 (Implement): Generate all project files, run tests

**Completion gate:** The project directory contains all 9 required files and `uv
run pytest` passes.

**Record these handoff artifacts** before proceeding to Phase 2:

| Artifact              | Description | Example                                |
| --------------------- | ----------- | -------------------------------------- |
| `project_dir`         | Path to the | `/home/user/my_experiment/`            |
:                       : experiment  :                                        :
:                       : directory   :                                        :
| `program_dir`         | Path to the | `<project_dir>/` (must contain         |
:                       : experiment  : `initial_program.py`)                  :
:                       : directory   :                                        :
| `evaluator`           | Path to the | `<project_dir>/evaluator.py`           |
:                       : evaluator   :                                        :
:                       : file        :                                        :
| `problem_description` | Path to the | `<project_dir>/problem_description.md` |
:                       : problem     :                                        :
:                       : description :                                        :

**Transition:** After the gate is satisfied, **proceed to Phase 2 immediately.**

Do NOT ask "How would you like to proceed?", "Should I launch?", or "Should I
create a commit?". Do NOT offer the user a menu of options. Do NOT stop and wait
for a new prompt. The user asked you to optimize their code — launching the
experiment is the obvious and only next step.

Simply inform the user and continue:

> Design phase complete. Proceeding to launch the experiment.

The only exception: if the user specifically said "design an experiment" or "set
up an experiment" (where they might want to stop after design), ask before
proceeding.

--------------------------------------------------------------------------------

## Phase 2: Runner

**Objective:** Configure the `ae` CLI, verify the evaluator works, and launch
the experiment on the AlphaEvolve backend.

**Guide:** Read `references/runner.md`, then follow its instructions. Provide
the handoff artifacts from Phase 1 (or from the user if they entered at Phase 2
directly).

> **Environment pre-check.** Before diving into the runner workflow, quickly
> verify these prerequisites (they cause the most wasted time if missing):
>
> 1.  `ae version` succeeds (CLI is installed and on PATH)
> 2.  Network works: verify connectivity to
>     `https://discoveryengine.googleapis.com` (e.g., via `curl` or equivalent
>     for your platform)
>
> If any fails, resolve it **before** starting the runner workflow.
> `references/setup.md` has the detailed discovery protocol for `ae`.

**If entering at Phase 2 directly** (user provided files, not from Design):

1.  Ask the user for the paths to their program file, evaluator file, and
    problem description.
2.  Validate that the program file has `EVOLVE-BLOCK` markers.
3.  Validate that the evaluator is a CLI-compatible script (accepts
    `--output-file` and `--program-dir`).
4.  If either is missing, suggest going back to Phase 1 (Design) to create
    proper artifacts.

**Completion gate:** The experiment is in ACTIVE state and the user has received
the experiment nickname.

**Record these handoff artifacts** before proceeding to Phase 3:

| Artifact              | Description           | Example                      |
| --------------------- | --------------------- | ---------------------------- |
| `experiment_nickname` | The experiment's      | `exp-brave-otter`            |
:                       : nickname              :                              :
| `evaluator`           | Path to the evaluator | `<project_dir>/evaluator.py` |
:                       : file                  :                              :

**Transition:** After the gate is satisfied, **IMMEDIATELY proceed to Phase 3 in
the same response.** Do NOT stop, do NOT ask "would you like me to monitor?", do
NOT suggest manual commands. The user asked you to optimize their code —
monitoring is not optional, it is the next required step. Simply inform them:

> Experiment `<nickname>` is now running. Starting the evaluation loop.

Then read `references/monitor.md` and start the control loop. The user should
never have to say "yes continue monitoring".

--------------------------------------------------------------------------------

## Phase 3: Monitor

**Objective:** Run the evaluation control loop and track experiment progress
until completion. The control loop (`ae experiment run`) is the command that
actually drives the experiment forward -- it acquires candidates, evaluates
them, and submits scores. Without it, the experiment stalls.

**Guide:** Read `references/monitor.md`, then follow its instructions. Provide
the experiment nickname and evaluator path from Phase 2 (or from the user if
they entered at Phase 3 directly). The monitor guide will start the control
loop with `--dashboard` to generate a live progress dashboard.

**If entering at Phase 3 directly** (user has a running experiment):

1.  Ask for the experiment nickname/ID if not provided.
2.  Ask for the evaluator file path if the control loop is not already running.

**Completion gate:** The experiment reaches a terminal state (COMPLETED, FAILED,
or CANCELLED).

**Record these handoff artifacts** before proceeding to Phase 4:

| Artifact               | Description          | Example                     |
| ---------------------- | -------------------- | --------------------------- |
| `experiment_nickname`  | The experiment's     | `exp-brave-otter`           |
:                        : nickname             :                             :
| `project_dir`          | Path to the          | `/home/user/my_experiment/` |
:                        : experiment directory :                             :
| `original_source_file` | Path to the user's   | `/home/user/src/solver.py`  |
:                        : original source file : (may be absent if           :
:                        : (if applicable)      : standalone experiment)      :

**Transition:** After the gate is satisfied, **IMMEDIATELY proceed to Phase 4 in
the same response.** Do NOT stop, do NOT suggest manual CLI commands, do NOT
offer a menu of options. Simply inform them:

> Experiment `<nickname>` has finished. Analyzing results...

Then read `references/post_experiment.md` and start the analysis.

--------------------------------------------------------------------------------

## Phase 4: Post-Experiment

**Objective:** Analyze experiment results with rich visualizations, review
evolved code for correctness, and offer to integrate improvements back into the
user's codebase if they choose to.

**Guide:** Read `references/post_experiment.md`, then follow its instructions.
Provide the handoff artifacts from Phase 3.

**If entering at Phase 4 directly** (user has a completed experiment):

1.  Ask for the experiment nickname if not provided.
2.  Ask for the project directory (where the evaluator and initial program live)
    if not known.
3.  Ask for the original source file path if the user wants code integration.

**Completion gate:** The experiment report has been presented and, if
applicable, the evolved code has been integrated and validated.

**After completion:**

The post-experiment guide handles everything: visualization, code review,
integration, and validation. After it completes, the orchestrator's job is done.
If the user wants to run another experiment, they will start a new conversation
or say so explicitly.

--------------------------------------------------------------------------------

## Phase Diagram

```
User Request
     |
     v
[Entry Point Detection]
     |
     +---> Problem description / code to optimize
     |         |
     |         v
     |     [Phase 1: Design]
     |     Read: references/experiment_design.md
     |     Gate: 9 files + pytest passes
     |         |
     |         v (auto-proceed if end-to-end intent, else ask)
     |
     +---> Program + evaluator files ready
     |         |
     |         v
     |     [Phase 2: Runner]
     |     Read: references/runner.md
     |     Gate: experiment ACTIVE + nickname obtained
     |         |
     |         v (proceed immediately, no confirmation needed)
     |
     +---> Running experiment nickname/ID
     |         |
     |         v
     |     [Phase 3: Monitor]
     |     Read: references/monitor.md
     |     Gate: terminal state reached
     |         |
     |         v (proceed immediately, no confirmation needed)
     |
     +---> Completed experiment nickname/ID
               |
               v
           [Phase 4: Post-Experiment]
           Read: references/post_experiment.md
           Gate: report presented + code integrated (if applicable)
               |
               v
           [Done]
```

--------------------------------------------------------------------------------

## Error Recovery

### Phase 1 fails (design issues)

-   Tests do not pass: Debug with the user, fix the evaluator or program
-   User wants to change approach: Go back to Phase 1 clarification

### Phase 2 fails (launch issues)

-   Connectivity errors: Follow `references/runner/debugging.md`
-   Evaluator baseline fails: Go back and fix the evaluator (may need Phase 1)
-   Quota exceeded: Help the user clean up old experiments or request quota

### Phase 3 fails (monitoring issues)

-   Control loop crashes: Check logs, restart the loop
-   Experiment stalls (no evaluations): Debug evaluator, check backend
-   Experiment FAILED state: Diagnose, fix, and optionally relaunch (Phase 2)

### Phase 4 fails (post-experiment issues)

-   Results retrieval fails: Verify experiment exists, check connectivity
-   Code integration fails: Syntax error or score mismatch -- follow the
    validation and rollback guidance in `references/post_experiment.md`
-   Reward hacking detected: The evolved code exploits the evaluator -- go back
    to Phase 1 (Design) to improve the evaluator
-   No improvement over baseline: All programs failed or scored equally --
    consider adjusting the search space or model

### User wants to go back

If the user wants to revisit a previous phase (e.g., "let me fix my evaluator"
during monitoring), pause the current phase and read the matching phase guide.
When they are done, resume from where you left off.

--------------------------------------------------------------------------------

## Quick Reference

Phase                    | Guide                             | Input                                | Output
------------------------ | --------------------------------- | ------------------------------------ | ------
Phase 1: Design          | `references/experiment_design.md` | Problem description                  | Project directory (9 files)
Phase 2: Runner          | `references/runner.md`            | Program + evaluator + problem desc   | Experiment nickname
Phase 3: Monitor         | `references/monitor.md`           | Nickname + evaluator path            | Terminal state
Phase 4: Post-Experiment | `references/post_experiment.md`   | Nickname + project dir + source file | Report + integrated code

The data contracts between phases are in
`references/orchestrator/handoff_contracts.md`.
