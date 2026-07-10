---
name: alpha-evolve-monitor
description: >
  Monitor running AlphaEvolve experiments, run the evaluation control loop,
  and report results using the `ae` CLI.
  Triggers on: "monitor experiment", "check experiment status",
  "run evaluation loop", "show experiment results", "how is the experiment
  doing", "experiment progress", "monitor AlphaEvolve".
---

# Alpha Evolve Experiment Monitor

You are an expert at monitoring AlphaEvolve experiments using the `ae` CLI. Your
job is to run the evaluation control loop, track experiment progress, and
present clear status reports to the user.

## Critical Rules

1.  **Always use `--json` flag** when calling `ae` commands so you can parse
    structured output. Present human-readable summaries yourself. Note: `--json`
    is a **global flag** and must go BEFORE the subcommand, e.g. `ae --json
    experiment describe <exp>`, NOT `ae experiment describe --json <exp>`.
2.  **NEVER execute user code directly.** All program evaluation MUST go through
    `ae experiment run`, which handles sandboxing via the evaluator.
3.  **Be concise.** Do not narrate your internal reasoning. State what you are
    doing, show results, and ask questions only when needed.
4.  **Experiment identifiers are flexible.** The user can provide an experiment
    nickname (e.g., `brave-otter`), a short ID, or a full resource name. Pass
    whatever the user gives you directly to `ae` commands -- the CLI resolves it
    automatically.
5.  **If the experiment name is not provided**, ask the user for it. You can
    also run `ae --json experiment list` to show available experiments and let
    the user pick one.

## Prerequisites Check

Before doing anything else, verify the `ae` CLI is installed:

```bash
ae version
```

If this command fails, tell the user:

> **The `ae` CLI is not installed.** This is required before proceeding. Please
> follow the `ae` CLI documentation to install it, then try again.

**Stop here if `ae version` fails. Do not proceed.**

--------------------------------------------------------------------------------

## Stage 1: Identify the Experiment

**Objective:** Determine which experiment to monitor and confirm it exists.

### Step 1.1: Get the experiment identifier

If the user provided an experiment name/nickname/ID, use it directly.

If not, ask the user:

> Which experiment would you like to monitor? You can provide a nickname (e.g.,
> `brave-otter`), an ID, or a full resource name.

You can also list available experiments to help the user choose:

```bash
ae --json experiment list
```

Parse the JSON output and present a table:

\#  | Nickname    | State     | Created
--- | ----------- | --------- | -------
1   | brave-otter | ACTIVE    | 2h ago
2   | calm-falcon | COMPLETED | 1d ago

Ask the user to pick one.

### Step 1.2: Verify the experiment exists and is running

```bash
ae --json experiment describe <EXPERIMENT>
```

Parse the JSON output. Check the `state` field:

-   **ACTIVE**: Good, proceed to Stage 2.
-   **COMPLETED / FAILED / CANCELLED**: The experiment is finished. Skip to
    Stage 4 (Final Report) to show results.
-   **PAUSED**: Ask the user if they want to resume it: > Experiment
    `<nickname>` is paused. Would you like to resume it? (y/n) If yes: `ae
    --json experiment resume <EXPERIMENT>`
-   **INITIALIZED**: The experiment was created but not started. Tell the
    user: > Experiment `<nickname>` has not been started yet. Use the
    Experiment > Runner skill to start it, or start it manually with: > `ae
    experiment start <nickname> --program-dir <directory> --score <score>`
-   **Any other state or error**: Consult `references/debugging.md`.

Save the experiment nickname for use in reports. You can extract it from the
JSON output's `nickname` field, or derive it: if the JSON does not include a
nickname, the CLI will have resolved it during `describe`.

--------------------------------------------------------------------------------

## Stage 2: Start the Control Loop

> **CRITICAL:** The control loop (`ae experiment run`) is the command that
> actually drives the experiment. It acquires candidate programs, evaluates them
> locally, and submits scores. Without it, the experiment stalls after the
> backend's initial burst. **Starting the control loop is your FIRST action** --
> do NOT just poll status.

**Objective:** Launch the evaluation control loop and generate a live dashboard
for the user.

### Step 2.1: Determine the evaluator

The control loop requires an evaluator script. Check if the user has provided
one.

If the user provided an evaluator file path, use it directly.

If not, ask the user:

> To run the evaluation loop, I need the path to your evaluator script. This is
> the Python file that scores candidate programs (it must accept `--output-file`
> and `--program-dir` flags).
>
> What is the path to your evaluator file?

If the user says the control loop is already running elsewhere (e.g., in another
terminal or on another machine), skip to Step 2.3 (monitor only).

### Step 2.2: Start the control loop with dashboard

Run the control loop in the background **with the `--dashboard` flag** to
generate a live-updating markdown file.

Use `<EXPERIMENT>-dashboard.md` (e.g., `exp-brave-otter-dashboard.md`) so that
multiple experiments in the same directory don't overwrite each other's
dashboards.

**Example (Linux/macOS — adapt for your platform's background job syntax):**

```bash
ae experiment run <EXPERIMENT> \
  --evaluator <EVALUATOR_FILE> \
  --timeout 60 \
  --backend local \
  --dashboard <EXPERIMENT>-dashboard.md \
  > /tmp/ae_control_loop_<EXPERIMENT>.log 2>&1 &

echo $!   # Save the PID to check on later
```

> **Note:** The exact syntax for running a background process and capturing its
> PID varies by platform and shell (bash, PowerShell, cmd.exe). Adapt the
> command accordingly. In many agent environments, the agent runtime handles
> background execution natively.

The `--dashboard` flag makes the CLI write a markdown file after each evaluation
with a score progression chart and leaderboard.

**Score progression chart.** Generate a chart image alongside the dashboard by
running:

```bash
ae results plot <EXPERIMENT> --output score_progression.png
```

This produces a `score_progression.png` with scatter dots for all evaluations, a
green running-best line annotated with program names at each new high, and a red
baseline. The dashboard markdown can reference it with `![Score
Progression](score_progression.png)`.

**You MUST regenerate this chart on every poll** (see Step 2.3). The dashboard
and the chart are a pair — both must be kept in sync.

Tell the user with the **full absolute paths** to both files:

> Started the evaluation control loop for `<nickname>`. Live dashboard:
> `<full_absolute_path>/<EXPERIMENT>-dashboard.md` Score chart:
> `<full_absolute_path>/score_progression.png`

Always use the full path (e.g.,
`/home/user/experiment/exp-brave-otter-dashboard.md`), not a relative path. The
user needs to be able to click the link or navigate to it directly.

**Render the dashboard inline on first poll and on completion.** After the first
poll and when the experiment reaches a terminal state, read the dashboard file
and display its contents directly in the chat so the user does not have to go
find the file. **Always include the full dashboard file path link at the bottom
of the inline rendering** so the user can navigate to the live file:

> [`<EXPERIMENT>-dashboard.md`](`<full_absolute_path>/<EXPERIMENT>-dashboard.md`)

On intermediate polls, only mention the dashboard file path — do not re-render
the full content every cycle.

**Important notes about `ae experiment run`:**

-   This is a **long-running blocking command**. It runs until the experiment
    completes, fails, or is interrupted.
-   By default it runs unlimited iterations. Use `--max-iterations N` if the
    user wants to limit evaluations.
-   The `--timeout` flag is the **per-evaluation timeout** in seconds (default
    60). Increase if evaluations are slow.
-   The `--backend` flag can be `local` (default) or `podman` (containerized).

### Step 2.3: Monitor progress

After starting the control loop, monitor progress by polling periodically. Use
the `schedule` tool to set a timer with `DurationSeconds="60"`.

When the timer fires, **always do both of these**:

1.  Check experiment status:

    ```bash
    ae --json experiment describe <EXPERIMENT>
    ```

2.  Update the chart (the dashboard markdown updates automatically via the
    `--dashboard` flag, but the chart image must be regenerated):

    ```bash
    ae results plot <EXPERIMENT> --output score_progression.png
    ```

**You MUST regenerate the chart on every poll** to keep it in sync with the
dashboard (see Step 2.2).

**Smart reporting -- only message the user when something changed:**

-   **New best score**: Post a brief message: "New best: `<nickname>`,
    score=X.XX (N evals so far)."
-   **State change**: Post: "Experiment state changed to `<STATE>`."
-   **Nothing changed**: **Stay completely silent.** Do NOT post "still running"
    or "no change" messages -- they are pure noise to the user and clutter the
    conversation. The dashboard and chart files have the detailed view.

**IMPORTANT: Do NOT post a message every poll cycle.** Only post when:

1.  A new best score is found.
2.  The experiment state changes.
3.  The experiment reaches a terminal state (-> Stage 4).

**If you are using scheduled timers to poll, the timer firing is NOT a reason to
post a message.** Check the state, and if nothing changed, do nothing — do not
post "no new best score", "still running", or any other heartbeat. The user has
the dashboard and will ask if they want an update.

Present a full Experiment Report (see Stage 3) only on the first poll and when
the experiment reaches a terminal state.

--------------------------------------------------------------------------------

## Stage 3: Experiment Report

**Objective:** Present a formatted report only when meaningful changes occur
(new best, state change, first poll, final state).

### When to post a full report

-   **First poll** after starting the control loop
-   **New best score** discovered
-   **Experiment reaches terminal state** (-> Stage 4)

### Report Template

```
## Experiment Report: <NICKNAME>

**Status:** <STATE>  |  **Evaluations:** <COUNT>  |  **Best Score:** <SCORE>

### Score Trend
- Poll 1 (12:00): best=2.112, evals=10
- Poll 2 (12:05): best=2.601, evals=22

---
Dashboard: `<EXPERIMENT>-dashboard.md` | Control loop running (PID: <PID>).
```

### How to extract report data from JSON

**From `ae --json experiment describe <exp>`:**

-   `state`: the experiment state (strip `EXPERIMENT_STATE_` prefix if present)
-   `createTime`: when the experiment was created
-   `stats.evaluatedCandidatesCount` or `evaluatedProgramsCount`: eval count
-   `stats.bestScore` or `bestScore`: best score (may be absent)
-   `config.title`: experiment title

### Report frequency

-   Poll every **60 seconds** by default.
-   If the user asks for more or less frequent updates, adjust accordingly.
-   Continue until the experiment reaches a terminal state (COMPLETED, FAILED,
    PAUSED, CANCELLED).

### Handling "why did programs fail?"

If the user asks about failed programs during monitoring, use these commands:

-   **All failures in the experiment:** `ae results failed <EXPERIMENT>` — shows
    all failed programs with their error insights, tracebacks, and evolved code.
-   **A specific failed program:** `ae program show <NICKNAME> --insights` —
    shows the evaluation insights (errors, tracebacks, stdout) for one program.
    Add `--experiment <EXPERIMENT>` only if the nickname cannot be resolved.

Summarize the failure patterns (e.g., "2 programs failed due to numerical
overflow in quadratic activation functions") rather than dumping raw output.

### Terminal state handling

When the experiment reaches a terminal state, present a final report (Stage 4)
and stop polling.

--------------------------------------------------------------------------------

## Stage 4: Final Report

**Objective:** When the experiment completes (or fails), present a comprehensive
final summary.

### Step 4.1: Gather final data

Run these commands to collect final results:

```bash
ae --json experiment describe <EXPERIMENT>
ae --json results best <EXPERIMENT> --top 10
```

**Always fetch and display the best program's code automatically:**

```bash
ae --json program show <BEST_PROGRAM_NICKNAME> --experiment <EXPERIMENT> --code
```

*Tip: You can also use `--output-file <path>` to save the code directly to a
file if it is large and might be truncated in the terminal.*

Do NOT just suggest the command and ask the user -- the whole point of running
the experiment is to see the result. Fetch and display the code directly.

### Step 4.1b: Check for failures

If any programs failed during the experiment, fetch failure details:

```bash
ae results failed <EXPERIMENT>
```

This shows all programs with null scores, their error messages, tracebacks, and
the evolved code that caused the failure. Include a brief summary of failures in
the final report (count and common causes).

For details on a specific failed program:

```bash
ae program show <NICKNAME> --experiment <EXPERIMENT> --insights
```

### Step 4.2: Present final report

```
## Final Experiment Report: <NICKNAME>

**Status:** COMPLETED
**Total Evaluations:** <COUNT>
**Best Score:** <SCORE>
**Duration:** <DURATION>
**Model:** <MODEL>

### Top 10 Programs
| Rank | Nickname | Score |
|------|----------|-------|
| 1 | swift-panda | 2.891 |
| ... | ... | ... |

### Best Program: `swift-panda` (score: 2.891)

<display the evolved code block inline>
```

### Step 4.3: Check control loop status

If you started the control loop in Step 2.2, check if it is still running. If it
is still running but the experiment is complete, it will stop on its own (it
checks for terminal states).

**Example (Linux/macOS):**

```bash
ps -p <PID> > /dev/null 2>&1 && echo "running" || echo "stopped"
tail -20 /tmp/ae_control_loop_<EXPERIMENT>.log
```

> Adapt for your platform — the key is to check whether the background process
> is still alive and to view its log output.

### Step 4.4: Offer next steps

After the final report, suggest actionable next steps to the user:

> The experiment is complete. Here are some things you can do:
>
> -   **Compare with parent:** `ae program diff <best_nickname>`
> -   **Integrate the result** into your codebase
> -   **View full history:** `ae results history <nickname>`
> -   **Start a new experiment** with refined parameters

--------------------------------------------------------------------------------

## Error Handling

For any `ae` command failure: 1. Parse the JSON error output (it will have
`error.status` and `error.message` fields). 2. Consult `references/debugging.md`
for known error patterns. 3. Suggest a specific fix. 4. Retry after the fix is
applied.

Common error patterns:

| Error                  | Likely Cause             | Fix                    |
| ---------------------- | ------------------------ | ---------------------- |
| "experiment not found" | Wrong nickname/ID        | Run `ae --json         |
:                        :                          : experiment list`       :
| 404                    | Wrong experiment name or | Verify with `ae --json |
:                        : project                  : config show`           :
| 403                    | Missing permissions      | User needs Discovery   |
:                        :                          : Engine Editor role     :
| "evaluation failed"    | Evaluator bug or missing | Debug locally or try   |
:                        : deps                     : `--backend podman`     :
| Control loop exits     | No programs available    | Wait and retry -- the  |
: immediately            : yet                      : backend may still be   :
:                        :                          : generating             :
| "quota exceeded"       | Project quota limit      | Delete old experiments |
:                        :                          : or request quota       :
:                        :                          : increase               :

--------------------------------------------------------------------------------

## Quick Reference

See `references/cli_reference.md` for the full command reference. Key commands
for this skill:

| Command                             | Purpose                             |
| ----------------------------------- | ----------------------------------- |
| `ae --json experiment describe      | Get experiment status               |
: <exp>`                              :                                     :
| `ae --json experiment run <exp>     | Run control loop                    |
: --evaluator <file>`                 :                                     :
| `ae --json results best <exp> --top | Top N programs by score             |
: N`                                  :                                     :
| `ae --json results failed <exp>`    | All failed programs with errors     |
| `ae --json program show <prog>      | View program source (and optionally |
: --code [--output-file <file>]`      : save to file)                       :
| `ae --json program show <prog>      | View evaluation errors/tracebacks   |
: --insights`                         :                                     :
| `ae program diff <prog>`            | Diff program vs parent (no --json)  |
| `ae --json experiment list`         | List all experiments                |
| `ae --json experiment resume <exp>` | Resume paused experiment            |
