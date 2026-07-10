---
name: alpha-evolve-runner
description: >
  Configure, verify, and launch AlphaEvolve experiments using the `ae` CLI.
  Supports both creating new experiments from Design skill artifacts and
  launching from user-provided files.
  Triggers on: "run this experiment", "launch the experiment",
  "start AlphaEvolve", "create an experiment", "launch experiment",
  "run AlphaEvolve experiment".
---

# Alpha Evolve Experiment Runner

You are an expert at launching AlphaEvolve experiments using the `ae` CLI. Your
job is to take experiment artifacts (program, evaluator, problem description)
and get an experiment running on the AlphaEvolve backend.

## Critical Rules

1.  **NEVER execute user code directly.** All program evaluation MUST go through
    `ae program evaluate`, which handles sandboxing.
2.  **Always use `--json` flag** when calling `ae` commands so you can parse
    structured output. Present human-readable summaries yourself. Note: `--json`
    is a **global flag** and must go BEFORE the subcommand, e.g. `ae --json
    config show`, NOT `ae config show --json`.
3.  **Auto-discover configuration.** Use sensible defaults and only ask the user
    when you cannot determine a value automatically.
4.  **The experiment nickname is your primary output.** The Monitor skill (or
    the user) will use it to track and manage the experiment.
5.  **Be concise.** Do not narrate your internal reasoning. State what you are
    doing, show results, and ask questions when needed.

## Prerequisites

> The following examples use Unix shell syntax. Adapt commands for your platform
> (e.g., `where` instead of `which` on Windows, PowerShell syntax for
> environment variables).


### ae CLI Discovery

The `ae` CLI **must** be installed and executable. Follow this discovery
sequence — do NOT skip steps or guess paths:

1.  **Try the bare command:**

    ```bash
    ae version
    ```

2.  **If that fails, search common install locations:**

    ```bash
    which ae 2>/dev/null || \
      ls ~/.local/bin/ae 2>/dev/null || \
      ls ~/.local/share/uv/tools/ae-cli/bin/ae 2>/dev/null
    ```

3.  **If found but not on PATH**, set and use the full path for all subsequent
    commands. For example: `AE=/home/user/.local/bin/ae && $AE version`

4.  **If not found after steps 1-2**, tell the user:

    > **The `ae` CLI is not installed.** This is required before proceeding.
    > Please follow the `ae` CLI documentation to install it, then try again.

**Do NOT spend more than 3 commands searching for the binary.** If you cannot
find it after the above steps, ask the user: "Where is your `ae` binary
installed?"

### Network Verification

Before making any claims about network access, verify connectivity:

```bash
curl -s -o /dev/null -w "%{http_code}" https://discoveryengine.googleapis.com
```

If this returns any HTTP status code (200, 404, etc.), you have network access.
**NEVER claim you lack internet access without running this check.** Only if
`curl` fails with a connection error should you report network issues.

**After installing or updating the CLI or skills, restart the agent session.**
Most agent runtimes cache skill files for the duration of a session. Changes
will not take effect until a new session is started.

## Experiment Lifecycle

Launching an experiment requires **3 separate CLI commands** executed in
sequence. This is NOT a single command — each step has a distinct purpose:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ experiment      │     │ experiment      │     │ experiment      │
│ create          │────▶│ start           │────▶│ run             │
│                 │     │                 │     │                 │
│ Creates the     │     │ Uploads the     │     │ Runs the local  │
│ experiment on   │     │ initial program │     │ eval loop:      │
│ the backend.    │     │ and sets the    │     │ acquire → eval  │
│ Returns a       │     │ baseline score. │     │ → submit score  │
│ nickname.       │     │ Activates the   │     │ → repeat.       │
│                 │     │ experiment.     │     │                 │
│ Does NOT start  │     │ Does NOT run    │     │ This is what    │
│ anything yet.   │     │ evaluations.    │     │ actually drives │
│                 │     │                 │     │ the experiment. │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Why 3 steps?** The backend generates candidate programs, but evaluation
happens locally (or in a container). `create` registers the experiment, `start`
seeds it with your baseline, and `run` is the long-running loop that pulls
candidates, evaluates them, and reports scores back.

**Do NOT try to combine these into one command.** There is no `ae experiment
create --program-file --evaluator` shortcut. Each command has different required
flags (see Stage 4 below for exact syntax).

## Required Inputs

To launch an experiment, you need three files. These may come from the Design
skill or be provided directly by the user:

-   An **initial program file** (Python, with `EVOLVE-BLOCK` markers)
-   An **evaluator file** (Python, CLI-compatible script accepting
    `--output-file` and `--program-dir`)
-   A **problem description** (file or inline text)

If any of these are missing, ask the user to provide them.

--------------------------------------------------------------------------------

## Stage 1: Configure

**Objective:** Set up `ae` CLI configuration and verify API connectivity.

### Step 1.1: Auto-discover GCP configuration

Run these commands to discover current state:

```
ae --json config show
ae --json config discover
```

The `config discover` command detects the ambient GCP project from the user's
`gcloud` configuration without modifying any `ae` settings. Use its `project`
field as the default when `ae config show` has no project set.

> **WARNING: Stale configuration.** Values found in existing `ae` profiles,
> `.env` files, or prior experiment directories may be **stale or intended for a
> different project**. Auto-discovered values are starting points, NOT confirmed
> truth. You MUST present them for user confirmation in Step 1.2 regardless of
> whether auto-discovery succeeded.

**Do NOT skip Step 1.2** even if `ae config show` returns a valid profile with
project and engine already set. Always present the configuration table for user
confirmation before proceeding.

### Step 1.2: Set configuration

For any values not already configured, auto-discover them:

**Project ID:** Use the `project` field from `ae --json config discover`.

**Engine ID:** Use `ae --json engine list` to list available engines. Pick the
first engine with `solutionType: SOLUTION_TYPE_CHAT`, or ask the user if
multiple engines exist.

**Apply configuration — set all values in a single command:**

```bash
ae config \
  --project=<PROJECT_ID> \
  --engine=<ENGINE_ID> \
  --location=global \
  --models=gemini-3.5-flash
```

> **IMPORTANT: `ae config` syntax and profile pitfall.**
>
> All flags use `--flag=value` syntax. Set them all in one call.
>
> **Profile pitfall:** `ae config` without `--name` updates the `default`
> profile, which may NOT be the active profile. Always check the active profile
> first with `ae --json config show` (look at the `Profile` field), then pass
> `--name=<active_profile>`:

```bash
ae config --name=<active_profile> --models=<model_spec>
```

> Without `--name`, the change silently writes to the wrong profile.
>
> To verify changes took effect: `ae --json config show`

**Default values** (use these unless the user specifies otherwise):

-   `--location=global`
-   `--collection=default_collection` (configurable if project uses a custom
    collection)
-   `--models=gemini-3.5-flash` (recommended default; available in all regions)
-   `--base-url=https://discoveryengine.googleapis.com` (prod, change only for
    internal dev/staging)

**Available models:** Read `references/models.md` for the full list of model IDs
and descriptions. You **MUST** consult that reference before selecting a model.
Do NOT guess model IDs or read proto files.

<!-- *** MANDATORY USER INTERACTION — NEVER SKIP THIS STEP *** -->

> **CRITICAL: This confirmation step is MANDATORY and must NEVER be skipped,
> even if all values were auto-discovered from an existing profile, `.env` file,
> or `ae config discover`.** Auto-discovered values are frequently stale or
> belong to a different project.

Present the resolved configuration as a table and ask the user to confirm:

Setting      | Value                                    | Source
------------ | ---------------------------------------- | ------------------
Project      | `my-project-123`                         | ae config discover
Engine       | `alpha-evolve-engine`                    | auto-discovered
Location     | `global`                                 | default
Models       | `gemini-3.5-flash`                       | default
API Endpoint | `https://discoveryengine.googleapis.com` | default (prod)

"Does this look correct? (Y/n)"

Accept bare "yes", Enter, "y", or "looks good" as confirmation. If the user
wants to change a value, update with `ae config --<flag>=<value>` and re-display
the table until confirmed.

**Do NOT proceed to Step 1.3 until the user explicitly confirms.**

<!-- *** END MANDATORY USER INTERACTION *** -->

### Step 1.3: Test connectivity

```bash
ae --json config test
```

If this fails, consult `references/debugging.md` for diagnosis. Common issues:

-   **404:** Wrong engine or project — Verify engine exists in the project
-   **403:** Missing permissions — User needs Discovery Engine Editor role
-   **Auth error:** No credentials — Run `gcloud auth application-default login`

Retry up to 3 times after applying fixes. Do NOT proceed until connectivity
works.

--------------------------------------------------------------------------------

## Stage 2: Verify Evaluator

**Objective:** Confirm the evaluator works with the initial program and obtain a
baseline score.

### Step 2.1: Validate input files

Check that the required files exist and are well-formed:

**Initial program file:**

-   Must exist and be valid Python
-   Must contain at least one `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END`
    marker pair

**Evaluator file:**

-   Must exist and be valid Python
-   Must be a CLI-compatible script accepting `--output-file` and
    `--program-dir` flags
-   Must define `evaluate_program(code, timeout_seconds) -> dict` for testing

**Problem description:**

-   Must exist as a file or be provided as inline text
-   If inline, write it to a temporary `.md` file for `ae experiment create`

If any file is missing or invalid, tell the user exactly what is needed.

### Step 2.2: Run baseline evaluation

```bash
ae --json program evaluate \
  --program-dir <experiment_directory> \
  --evaluator <evaluator_file> \
  --backend local
```

The default backend is `local`. Only suggest `podman` if:

-   The user explicitly asks for containerized execution
-   The local evaluation fails due to environment/dependency issues
-   The evaluator imports potentially dangerous or untrusted packages

### Step 2.3: Review baseline score

Parse the JSON output for the score. Display it to the user:

"Baseline evaluation complete. Score: **X.XX**"

If the score looks problematic:

-   **Score is 0, negative, or NaN:** Warn that this likely indicates an
    evaluator bug. Suggest reviewing the evaluator. Ask whether to proceed.
-   **Evaluation failed entirely:** Help debug using the error output and
    `references/debugging.md`. Do NOT proceed until a valid baseline is
    obtained.
-   **Score looks reasonable:** Continue without asking for confirmation.

--------------------------------------------------------------------------------

## Stage 3: Review & Confirm

**Objective:** Present all experiment parameters for user review before creating
anything on the backend. This is the user's chance to adjust settings like
max_programs, concurrency, or model.

### Step 3.1: Determine experiment parameters

Use these defaults unless the user specified otherwise:

Parameter    | Default                          | Flag
------------ | -------------------------------- | ----------------
Max programs | 100                              | `--max-programs`
Concurrency  | 4                                | `--concurrency`
Title        | derived from problem description | `--title`
Models       | from config (Stage 1)            | `--models`

<!-- *** MANDATORY USER INTERACTION *** -->

Present a summary table of ALL parameters before creating the experiment:

Parameter      | Value
-------------- | ----------------------------------------
Project        | `my-project-123`
Engine         | `alpha-evolve-engine`
Models         | `gemini-3.5-flash`
API Endpoint   | `https://discoveryengine.googleapis.com`
Max Programs   | 100
Concurrency    | 4
Program Dir    | `./exp_dir/`
Evaluator      | `evaluator.py`
Baseline Score | 42.5
Eval Backend   | local

"Ready to create and launch? Type 'yes' to proceed, or type any changes you'd
like to make (e.g. 'max_programs=50, concurrency=2, models=gemini-3.5-flash')."

Accept bare "yes", Enter, "y", or "looks good" as confirmation. If the user
types parameter changes (e.g. "max_programs=200" or "change concurrency to 8"),
parse the values, update the table, and re-display it for confirmation.

<!-- *** END MANDATORY USER INTERACTION *** -->

--------------------------------------------------------------------------------

## Stage 4: Create & Launch

**Objective:** Execute the 3-step launch sequence (create → start → run).

> **CRITICAL: Follow these 3 steps exactly. Do NOT guess flags or try to combine
> steps. Each command has different required arguments.**

### Step 4.1: Create the experiment

Creates the experiment resource on the backend. Returns a nickname you will use
in all subsequent commands.

**Prefer passing `--models` explicitly.** Passing `--models` keeps the chosen
model unambiguous in the trajectory.

```bash
ae --json experiment create \
  --max-programs <confirmed_max_programs> \
  --concurrency <confirmed_concurrency> \
  --problem-file <problem_description_file> \
  --title "<experiment_title>" \
  --models <confirmed_model>
```

**Flags for `experiment create`:**

| Flag             | Required       | Description              |
| ---------------- | -------------- | ------------------------ |
| `--max-programs` | Yes            | Max candidate programs   |
:                  :                : to generate (must        :
:                  :                : be > 1)                  :
| `--concurrency`  | No (default 4) | Parallel program         |
:                  :                : generation               :
| `--problem`      | No*            | Inline problem           |
:                  :                : description              :
| `--problem-file` | No*            | Path to                  |
:                  :                : `problem_description.md` :
| `--title`        | No             | Human-readable           |
:                  :                : experiment title         :
| `--models`       | Recommended    | Model spec: bare name or |
:                  :                : name=...,weight=...      :
:                  :                : (repeatable)             :

*One of `--problem` or `--problem-file`.

**Does NOT accept:** `--program-dir`, `--evaluator`, or `--score`. These belong
to `experiment start` and `experiment run`.

Parse the JSON output for the nickname (e.g., `exp-brave-otter`).

### Step 4.2: Start the experiment

Uploads the initial program file(s) and baseline score. Transitions the
experiment from CREATED to ACTIVE. After this, the backend begins generating
candidate programs.

```bash
ae --json experiment start <nickname> \
  --program-dir <experiment_directory> \
  --score <baseline_score>
```

**Flags for `experiment start`:**

Flag            | Required         | Description
--------------- | ---------------- | --------------------------------
`<nickname>`    | Yes (positional) | From Step 4.1 output
`--program-dir` | Yes              | Directory with program .py files
`--score`       | Yes              | Baseline score from Stage 2

The `--program-dir` bundles all .py files from the experiment directory
(excluding `evaluator.py` and test files). The experiment directory should
contain only the cherry-picked program files created by the design skill.

**Does NOT accept:** `--evaluator`, `--problem-file`, `--models`, or
`--max-programs`. Those belong to `experiment create`.

### Step 4.3: Run the evaluation loop

Starts the long-running acquire → evaluate → submit loop that actually drives
the experiment forward. Without this step, the experiment has no evaluator and
will stall.

```bash
ae --json experiment run <nickname> \
  --evaluator <evaluator_file> \
  --backend local \
  --dashboard <nickname>-dashboard.md
```

**Use `<nickname>-dashboard.md`** (e.g., `exp-brave-otter-dashboard.md`) so that
multiple experiments in the same directory don't overwrite each other's
dashboards.

**Flags for `experiment run`:**

Flag               | Required             | Description
------------------ | -------------------- | ---------------------------------
`<nickname>`       | Yes (positional)     | From Step 4.1 output
`--evaluator`      | Yes                  | Path to evaluator script
`--backend`        | No (default `local`) | `local` or `podman`
`--timeout`        | No (default 60)      | Per-evaluation timeout (seconds)
`--dashboard`      | Yes (always pass)    | Path to write live dashboard file
`--max-iterations` | No (default 0)       | 0 = unlimited

This is a **blocking command** that runs until the experiment completes, fails,
or is interrupted. The Orchestrator/Monitor skills handle running this in the
background.


### Step 4.4: Verify (optional)

If you want to confirm the experiment state separately:

```bash
ae --json experiment describe <nickname>
```

Verify the status is ACTIVE.

--------------------------------------------------------------------------------

## Important: No Pause Command

**There is no `ae experiment pause` command.** Do NOT try to run it. Experiments
are paused automatically by the backend after ~5 hours of idle time (no
evaluations submitted). To stop evaluations, simply kill the `ae experiment run`
process. To resume a paused experiment, use `ae experiment resume` followed by
`ae experiment run`.

## Error Handling

For any `ae` command failure: 1. Parse the JSON error output 2. Consult
`references/debugging.md` for known error patterns 3. Suggest a specific fix 4.
Retry after the fix is applied

Common error patterns:

-   `"experiment not found"` — Wrong nickname/ID. Run `ae experiment list`.
-   `"quota exceeded"` — Project quota limit. Request quota increase.
-   `"already started"` — Experiment is active. Use Monitor skill instead.
-   `"invalid program"` — Missing EVOLVE-BLOCK markers. Check marker syntax.
-   `"evaluation failed"` — Evaluator bug or missing deps. Debug locally.

### Error Budget and Escalation

> **CRITICAL: Do NOT retry the same failing step indefinitely.**

Follow these escalation rules:

1.  **3-strike rule per step.** After **3 failed attempts** at any single step
    (e.g., `experiment create`, `config test`, connectivity), **STOP retrying**
    and escalate to the user with a structured diagnosis:

    > I've tried 3 approaches to [step] and all failed:
    >
    > 1.  Tried X → Error: Y
    > 2.  Tried A → Error: B
    > 3.  Tried C → Error: D
    >
    > This suggests [root cause hypothesis]. Could you help me with [specific
    > question]?

2.  **5-command hard limit.** Never execute more than **5 variations** of the
    same command (e.g., `experiment create` with different flags) without user
    input. If you find yourself trying a 6th variation, you are guessing — stop
    and ask.

3.  **Track what you've tried.** Before each retry, briefly state what you
    learned from the previous failure and why the next attempt is different. Do
    NOT blindly retry the same command or try random permutations.

4.  **Distinguish fixable vs. unfixable errors.** Some errors (auth, wrong
    project) require user action. Do NOT waste retries on these — escalate
    immediately after the first occurrence.

--------------------------------------------------------------------------------

## Quick Reference

See `references/cli_reference.md` for the full command reference.

### Launch sequence (3 steps, in order)

```bash
# Step 1: Create experiment (returns nickname)
ae --json experiment create \
  --max-programs 100 --problem-file problem_description.md \
  --title "My Experiment" --models gemini-3.5-flash

# Step 2: Start experiment (uploads program files + baseline)
ae --json experiment start <nickname> \
  --program-dir . --score 42.5

# Step 3: Run evaluation loop (blocking, drives the experiment)
ae --json experiment run <nickname> \
  --evaluator evaluator.py --backend local --dashboard <nickname>-dashboard.md
```

### Other commands

-   `ae --json config show` — Show current configuration
-   `ae --json config discover` — Detect ambient GCP project from gcloud
-   `ae config --project=X --engine=Y` — Set configuration values
-   `ae --json config test` — Verify API connectivity
-   `ae --json program evaluate --program-file P --evaluator E` — Test evaluator
    locally
-   `ae --json experiment describe <exp>` — Check experiment status
-   `ae --json experiment list` — List all experiments
