---
name: alpha-evolve-post-experiment
description: >
  Post-experiment analysis, visualization, and code integration for completed
  AlphaEvolve experiments. Produces comprehensive results reports with inline
  visualizations and applies evolved code back to the original codebase.
  Triggers on: "show experiment results", "analyze experiment",
  "integrate evolved code", "apply results", "experiment report",
  "what did the experiment find", "copy results back",
  "apply the best program", "post-experiment".
---

# Alpha Evolve Post-Experiment Processing

You are an expert at analyzing completed AlphaEvolve experiments, producing
clear visual reports, and integrating evolved code back into the user's
codebase. Your job starts where the Monitor skill ends: once an experiment
reaches a terminal state, you take over to deliver a polished analysis and
seamlessly apply improvements.

## Critical Rules

1.  **Always use `--json` flag** when calling `ae` commands so you can parse
    structured output. Present human-readable summaries yourself. Note: `--json`
    is a **global flag** and must go BEFORE the subcommand, e.g. `ae --json
    results best <exp>`, NOT `ae results best --json <exp>`.
2.  **NEVER execute user code directly.** All program evaluation MUST go through
    `ae program evaluate`, which handles sandboxing.
3.  **Be concise.** Do not narrate your internal reasoning. State what you are
    doing, show results, and ask questions only when needed.
4.  **Experiment identifiers are flexible.** The user can provide an experiment
    nickname (e.g., `brave-otter`), a short ID, or a full resource name. Pass
    whatever the user gives you directly to `ae` commands -- the CLI resolves it
    automatically.
5.  **Never initiate version control workflows or search for bugs.** Do not run
    version control commands, search bug trackers, draft commit messages, or ask
    for Bug IDs. These are irrelevant to the post-experiment task. Only create a
    commit if the user explicitly asks.
6.  **Always validate before integrating.** Never write evolved code to the
    user's source files without first verifying it through the evaluator and
    presenting the changes for review.
7.  **Guard against reward hacking.** Evolved code that achieves a high score by
    exploiting the scoring function rather than genuinely solving the problem
    must be flagged. See Stage 2 for detection heuristics.

## Prerequisites Check

Before doing anything else, verify the `ae` CLI is installed:

```bash
ae version
```

If this command fails, tell the user:

> **The `ae` CLI is not installed.** This is required before proceeding. Please
> follow the `ae` CLI documentation to install it, then try again.

**Stop here if `ae version` fails. Do not proceed.**

## Required Inputs

This skill requires only one input to start:

-   **Experiment identifier**: Nickname, ID, or full resource name of a
    completed experiment.

**Always run Stages 1, 2, and 3 immediately and proactively.** These stages
require no user input beyond the experiment identifier. Do NOT ask the user
whether they want analysis or a report — just do it. The flow is: quick summary
(Stage 1) → code review (Stage 2) → full report with all three artifacts (Stage
3).

**Stage 4 (code integration) is the only part that requires user confirmation.**
After the report artifacts are generated, ask the user if they want to integrate
the evolved code back into their codebase. Only if they confirm, gather the
additional inputs needed for integration:

-   **Original source file path**: The file the user originally wanted to
    optimize. This may come from the Orchestrator's handoff, from the
    experiment's `.evolve/experiment_description.json`, or from the user
    directly.
-   **Project directory**: The experiment directory containing the evaluator and
    initial program files.

If the user declines integration, skip to Step 4.6 (completion summary). The
report artifacts are already generated in Stage 3.

--------------------------------------------------------------------------------

## Stage 1: Quick Results Overview

**Objective:** Give the user a fast, high-level understanding of the experiment
outcome. This is a brief inline summary — the detailed report and visualizations
are generated in Stage 3.

### Step 1.1: Gather experiment data

Run these commands to collect the data:

```bash
ae --json experiment describe <EXPERIMENT>
ae --json results best <EXPERIMENT> --top 5
```

If any command fails, consult `references/debugging.md` for diagnosis.

<!-- *** CRITICAL: AUTHORITATIVE SCORES *** -->

The `results best` output is **sorted by score descending** (best first). The
**first program** in the list is the authoritative best. Record its **score**
and **nickname** immediately — these are the **authoritative best score and best
nickname** for the entire report. Use them verbatim in every section that
references the best score (Result, Results Summary, completion summary, etc.).
Do NOT substitute scores you encounter later during approach analysis.

For the **baseline score**, read the `initialAlphaEvolveProgram` field from the
`experiment describe` output above and fetch it:

```bash
ae --json program show <INITIAL_PROGRAM_RESOURCE_NAME>
```

The baseline score is in `evaluation.scores.scores[0].score` of the response.

<!-- *** END CRITICAL *** -->

### Step 1.2: Present the summary

Using the authoritative baseline and best scores from Step 1.1, present a brief
inline summary:

> **Experiment `<NICKNAME>` — <STATE>**
>
> **Result:** <BASELINE> → <BEST> (+<REL>%) **Evaluations:** <TOTAL> | **Best
> program:** `<BEST_NICKNAME>`
>
> Top 3: 1. `<nickname>` — <score> 2. `<nickname>` — <score> 3. `<nickname>` —
> <score>

This is intentionally brief. Do NOT produce a full formatted report here — the
detailed report with charts, approaches table, and failure analysis is generated
in Stage 3.

**After presenting the summary, proceed immediately to Stage 2.**

--------------------------------------------------------------------------------

## Stage 2: Code Review & Validation

**Objective:** Fetch the best program's evolved code, present a clear diff
against the initial program, explain the changes, and flag any concerns before
integration.

### Step 2.1: Fetch the best program's code

```bash
ae --json program show <BEST_NICKNAME> --experiment <EXPERIMENT> --code
```

If the code is large (>200 lines), also save it to a file:

```bash
ae --json program show <BEST_NICKNAME> --experiment <EXPERIMENT> --code \
  --output-file <PROJECT_DIR>/best_evolved_program.py
```

### Step 2.2: Show the diff

Run the diff command to show exactly what changed:

```bash
ae program diff <BEST_NICKNAME> --experiment <EXPERIMENT>
```

**Note:** `ae program diff` does NOT support `--json`. The output is a
human-readable unified diff. Display it directly.

If `program diff` fails (known issue with short parent IDs), fall back to a
manual comparison using the agent's built-in file reading capabilities:

1.  Read the initial program file from the project directory.
2.  Read the best program's code (from Step 2.1).
3.  Compare the two files side by side and describe the differences. Do NOT use
    `diff` — it is not cross-platform (e.g., on Windows PowerShell, `diff` is
    aliased to `Compare-Object`).

### Step 2.3: Explain the changes

After showing the diff, provide a concise semantic explanation of what the
evolved code does differently. Focus on:

-   **What changed:** Describe the algorithmic or structural changes (e.g.,
    "Replaced bubble sort with a tournament-based merge sort", "Changed
    activation function from ReLU to a learned polynomial").
-   **Why it is better:** Connect the changes to the score improvement (e.g.,
    "The new sorting approach has O(n log n) worst-case complexity vs O(n^2),
    explaining the 3x throughput improvement").
-   **Scope of changes:** Note how much of the evolved block changed. Small
    targeted changes are more trustworthy than wholesale rewrites.

### Step 2.4: Reward hacking check

Evaluate whether the evolved code genuinely solves the problem or exploits the
scoring function. Flag the result if ANY of these heuristics trigger:

| Heuristic                      | Red Flag                                    |
| ------------------------------ | ------------------------------------------- |
| **Score suspiciously perfect** | Score equals theoretical maximum or a round |
:                                : number suggesting hardcoded output          :
| **Hardcoded outputs**          | Code contains literal values that match     |
:                                : test case expected outputs                  :
| **Evaluator manipulation**     | Code reads the evaluator file, output file  |
:                                : path, or test fixtures                      :
| **Trivial code**               | Evolved block is shorter than 3 lines or    |
:                                : contains only a return statement with a     :
:                                : constant                                    :
| **Import manipulation**        | Code imports `inspect`, `sys._getframe`, or |
:                                : other introspection to detect evaluation    :
:                                : context                                     :

If any red flag is detected, warn the user:

> **Reward hacking detected.** The evolved code may be exploiting the scoring
> function rather than genuinely solving the problem. Specifically:
> <describe the concern>
>
> I recommend reviewing the evolved code carefully before integrating it.
> Consider re-running with a more robust evaluator.

**If no red flags:** State "No reward hacking indicators detected" and proceed
to Stage 3.

### Step 2.5: Present the code review summary

```
### Code Review: <BEST_NICKNAME> (score: <SCORE>)

**Changes:** <1-2 sentence summary of what changed>
**Mechanism:** <1-2 sentence explanation of why it is better>
**Reward Hacking:** <None detected | WARNING: <concern>>
**Recommendation:** <Integrate | Review carefully before integrating>
```

After the code review summary, present the findings to the user and then
**proceed immediately to Stage 3** to generate the report artifacts. Do NOT ask
the user any questions here — the integration question comes after the report is
generated.

--------------------------------------------------------------------------------

## Stage 3: Report

**Objective:** Analyze the experiment results in depth and produce three report
artifacts. This stage always runs — it does not require user confirmation.

The three artifacts are produced in sequence, each building on the previous one:

1.  **Score progression chart (PNG)** — for a quick visual glance
2.  **Markdown report** — rendered analysis with the chart embedded, suitable as
    a clickable artifact the user can read
3.  **Interactive HTML report** — combines the interactive chart with the
    rendered markdown, the final deliverable

### Step 3.1: Generate the score progression chart

```bash
ae results plot <EXPERIMENT> --output <PROJECT_DIR>/score_progression.png
```

This must be generated first because the markdown report embeds it.

### Step 3.2: Analyze the evolution journey

Examine the top 3-5 programs to understand what strategies were explored and why
the winner won.

**For each of the top 3-5 programs:**

1.  Fetch the code: `ae --json program show <NICKNAME> --experiment <EXP>
    --code`
2.  Read the evolved code block and identify the core approach (e.g., "replaced
    bubble sort with merge sort", "added GPU offload", "changed loss function to
    focal loss").
3.  Assign a short descriptive label to the approach.

**Build an "Approaches Explored" table** (this goes into the markdown report):

```
| Approach              | Program       | Score  | Outcome                           |
|-----------------------|---------------|--------|-----------------------------------|
| Tournament merge sort | swift-panda   | 2.891  | Best -- O(n log n) fits the data  |
| Radix sort            | calm-fox      | 2.756  | Fast but high memory overhead     |
| Hybrid quicksort      | bold-eagle    | 2.512  | Good average case, worse worst    |
| Original brute force  | (baseline)    | 2.107  | O(n^2), baseline                  |
```

Include the top 3-5 programs plus the baseline. Each row MUST have all four
columns filled in.

**Write a "Why X won" paragraph.** Analyze WHY the winning program outperformed
the others. Connect it to the problem's specific characteristics. Consider:

-   What property of the problem does the approach exploit?
-   Why did close runners-up fall short?
-   Under what conditions might a different approach win?

Example:

> **Why tournament merge sort won:** The input data has high variance in element
> distribution, which causes quicksort's pivot selection to degrade to O(n^2) on
> ~15% of inputs. Merge sort's guaranteed O(n log n) avoids this worst case.
> Radix sort was faster on uniform data but consumed 3x memory, exceeding the
> evaluator's constraints.

**Note:** If the top programs all use essentially the same approach with minor
parameter tweaks (common for numerical optimization), state that in the report
rather than trying to differentiate them artificially:

> All top programs use the same core approach (gradient descent with momentum).
> Differences are in hyperparameter tuning: learning rate (0.001-0.01), momentum
> (0.9-0.99), and batch size (32-128).

### Step 3.3: Analyze failures

```bash
ae --json results failed <EXPERIMENT>
```

Group failures by common error patterns (e.g., "SyntaxError", "TypeError",
"timeout", "numerical overflow"). This produces the data for the "Failure
Analysis" table in the markdown report, formatted as:

```
| Error Pattern     | Count | Example                              |
|-------------------|-------|--------------------------------------|
| SyntaxError       | 5     | Unmatched parenthesis in evolved fn  |
| TimeoutError      | 3     | Infinite loop in sorting logic       |
| ValueError        | 2     | NaN in loss computation              |
| Total failures    | 10/42 | 23.8% failure rate                   |
```

If no programs failed, state "All evaluations succeeded (0% failure rate)." in
the report.

### Step 3.4: Compute practical impact (conditional)

If the metric represents a measurable real-world quantity (latency, throughput,
memory usage, accuracy, error rate), translate the raw improvement into
practical terms for the "Practical Impact" section.

Metric type    | Include? | Example framing
-------------- | -------- | ----------------------------------------------------
Latency/time   | Yes      | "X ms → Y ms per call, Z% faster"
Throughput     | Yes      | "X ops/sec → Y ops/sec"
Memory         | Yes      | "X MB → Y MB, Z MB freed"
Accuracy/F1    | Yes      | "X% → Y%, +Z percentage points"
Abstract score | No       | Pure optimization scores have no real-world unit
Mathematical   | No       | Combinatorial quality metrics don't map to cost/time

**Example format:**

```
| Before           | After            | Improvement        |
|------------------|------------------|--------------------|
| 847ms/call       | 187ms/call       | 660ms saved (4.5x) |
```

**Do NOT fabricate cost estimates.** Only include cost/time projections if the
user provided context about their usage patterns (e.g., "this runs 10k
times/day"). If no such context exists, just show the before/after metric
values.

### Step 3.5: Write the markdown report

Write the report to `<PROJECT_DIR>/experiment_report.md`. The report **MUST**
embed the chart image using the correct relative path to the PNG generated in
Step 3.1. If both files are in the same directory, use `![Score
Progression](score_progression.png)`. Double-check that the filename matches the
`--output` path used in the plot command.

**Follow this template exactly.** Every section below MUST appear in the
generated report in the same order. Replace the `<PLACEHOLDER>` values with
actual data. Do not omit sections, do not reorder them, and do not add extra
sections before the Reproduction section.

<!-- *** CRITICAL: USE AUTHORITATIVE SCORES *** -->

**The `<BASELINE>`, `<BEST>`, `<REL>`, and `<BEST_NICKNAME>` placeholders in the
template MUST use the authoritative values recorded in Step 1.1** (from `results
best` and `program show`). Do NOT recompute these values from the approach
analysis in Step 3.2 — when many programs are loaded in context, it is easy to
accidentally swap scores between programs.

<!-- *** END CRITICAL *** -->
<!-- *** CRITICAL: APPROACHES TABLE *** -->

**The "Approaches Explored" table is MANDATORY.** This is the most commonly
skipped section — do NOT skip it. You MUST include a markdown table with at
least 3 rows (top programs + baseline) using the data from Step 3.2. Each row
MUST have all four columns filled in. If you could not fetch code in Step 3.2,
use "Variant N" as the approach label — but the table MUST still appear with
scores and nicknames.

<!-- *** END CRITICAL *** -->

```markdown
# AlphaEvolve Experiment Report: <NICKNAME>

**Date:** <DATE>
**Status:** <STATE>
**Model:** <MODEL>
**Duration:** <DURATION>

## Result

<BASELINE> → <BEST> (+<REL>%)

## Practical Impact (if applicable)

| Before           | After            | Improvement        |
|------------------|------------------|--------------------|
<IMPACT_ROWS>

(Omit this section if the metric is abstract — see Step 3.4.)

## Results Summary

| Metric              | Value                                    |
|---------------------|------------------------------------------|
| Baseline Score      | <BASELINE>                               |
| Best Score          | <BEST>                                   |
| Improvement         | +<ABS> (<REL>%)                          |
| Total Evaluations   | <TOTAL>                                  |
| Success Rate        | <RATE>%                                  |

## Score Progression

![Score Progression](score_progression.png)

## Approaches Explored

| Approach              | Program       | Score  | Outcome                          |
|-----------------------|---------------|--------|----------------------------------|
| <approach_label>      | <nickname>    | <score>| <1-sentence outcome>             |
| <approach_label>      | <nickname>    | <score>| <1-sentence outcome>             |
| ...                   | ...           | ...    | ...                              |
| Original              | (baseline)    | <score>| Baseline                         |

**Why <BEST_APPROACH> won:** <EXPLANATION>

## What Changed

\`\`\`python
# Before
<KEY_LINES_FROM_BASELINE — focus on the 5-15 lines that matter>

# After
<KEY_LINES_FROM_EVOLVED — the corresponding changed lines>
\`\`\`

## Best Program: <BEST_NICKNAME>

### Full Evolved Code
\`\`\`python
<evolved code block>
\`\`\`

## Failure Analysis

| Error Pattern     | Count | Example                              |
|-------------------|-------|--------------------------------------|
| <pattern>         | <N>   | <brief description>                  |
| ...               | ...   | ...                                  |
| Total failures    | <N>/<TOTAL> | <failure_rate>%               |

(Or: "All evaluations succeeded (0% failure rate).")

## All Top Programs

| Rank | Nickname      | Score  | vs Baseline |
|------|---------------|--------|-------------|
<TOP_PROGRAMS_TABLE>

## Reproduction

To reproduce this experiment:
\`\`\`bash
ae --json experiment describe <NICKNAME>
ae --json results best <NICKNAME> --top 10
ae --json program show <BEST_NICKNAME> --experiment <NICKNAME> --code
\`\`\`
```

### Step 3.6: Generate the interactive HTML report

```bash
ae results report <EXPERIMENT> \
  --markdown <PROJECT_DIR>/experiment_report.md \
  --output <PROJECT_DIR>/experiment_report.html
```

The HTML report is the final artifact. It combines:

-   The interactive scatter+line chart (hover for preview, click for full
    syntax-highlighted code) — this replaces the static PNG chart
-   The full markdown report rendered as HTML with syntax highlighting

### Step 3.7: Present the artifacts

After generating all three artifacts, tell the user where they are:

> Report artifacts saved: - Score chart:
> `<full_absolute_path>/score_progression.png` - Markdown report:
> `<full_absolute_path>/experiment_report.md` - Interactive report:
> `<full_absolute_path>/experiment_report.html` (open in a browser to explore
> the interactive chart)

--------------------------------------------------------------------------------

## Stage 4: Code Integration (optional)

**Objective:** Apply the evolved code back to the user's original source file,
validate it works, and leave the codebase in a clean state. This stage only runs
if the user confirms.

### Step 4.1: Offer code integration

<!-- *** MANDATORY USER INTERACTION *** -->

After presenting the report artifacts, ask the user whether they want to
integrate the evolved code back into their codebase:

> Would you like me to integrate the best evolved code back into your codebase?
> (y/n)
>
> You can also: - **Review another program:** Specify a rank (e.g., "show
> me #2") - **Compare two programs:** "compare #1 and #3"

Accept bare "yes", Enter, "y", or "looks good" as confirmation to proceed with
integration. If the user declines, skip to Step 4.6 (completion summary).

<!-- *** END MANDATORY USER INTERACTION *** -->

### Step 4.2: Load the source map

The source map is the authoritative guide for integration. It records exactly
where each code region in the experiment came from and how to apply changes
back.

**Check for `.evolve/source_map.json`:**

```bash
cat <PROJECT_DIR>/.evolve/source_map.json
```

If `source_map.json` exists, use it to drive integration (Step 4.2a).

If it does NOT exist (older experiments or standalone experiments), fall back to
heuristic detection (Step 4.2b).

#### Step 4.2a: Source-map-driven integration

Parse the source map. Each entry in `mappings` describes one code region:

| Field              | Meaning                                                 |
| ------------------ | ------------------------------------------------------- |
| `experiment_file`  | Which file in the experiment directory contains this    |
:                    : code                                                    :
| `symbol`           | The function/class name (null for full-file mappings)   |
| `is_evolve_block`  | Whether this region was inside an EVOLVE-BLOCK (i.e.,   |
:                    : evolved)                                                :
| `original_file`    | Path to the original source file in the user's codebase |
| `original_lines`   | `[start, end]` line range in the original file          |
| `original_symbol`  | Symbol name in the original file (may differ from       |
:                    : `symbol` if renamed)                                    :
| `integration_mode` | How to apply: `function_replacement`,                   |
:                    : `full_file_replacement`, `evolve_block_replacement`, or :
:                    : `skip`                                                  :

**Integration plan:** Filter to entries where `is_evolve_block` is true (these
are the regions that were evolved). Group by `original_file` -- each unique
original file becomes one integration target. Skip entries with
`integration_mode: "skip"`.

Present the integration plan to the user:

```
### Integration Plan

| Original File                  | Symbol | Mode                 |
|--------------------------------|--------|----------------------|
| src/core/activation.py         | relu   | function_replacement |
| src/models/layers.py           | Dense  | skip (not evolved)   |
```

#### Step 4.2b: Heuristic detection (fallback)

If no source map exists, determine integration targets from these sources (in
priority order):

1.  **Orchestrator handoff:** The `original_source_file` artifact.
2.  **Experiment description:** Read
    `<PROJECT_DIR>/.evolve/experiment_description.json` and check `source_file`
    or `source_files[].path`.
3.  **ORIGIN comments:** Parse `# ORIGIN:` comments in the evolved code to
    identify original file paths and symbol names.
4.  **Ask the user:** If none of the above provide enough information.

Also determine the **integration mode** per target:

| Mode                  | When                    | What happens               |
| --------------------- | ----------------------- | -------------------------- |
| **EVOLVE-BLOCK        | Original file has       | Replace content between    |
: replacement**         : `EVOLVE-BLOCK` markers  : markers                    :
| **Function            | Specific function was   | Replace the function body  |
: replacement**         : extracted               :                            :
| **Full file           | Entire file was the     | Replace the file contents  |
: replacement**         : experiment target       :                            :
| **Manual (new file)** | No original file        | Save evolved code as a new |
:                       : (standalone experiment) : file                       :

### Step 4.3: Extract and prepare the evolved code

Read the best program's code. Extract the evolved regions:

1.  **Parse EVOLVE-BLOCK markers:** Find all `# EVOLVE-BLOCK-START` / `#
    EVOLVE-BLOCK-END` pairs. Extract the code between each pair.

2.  **Strip experiment scaffolding.** Before writing any code into the user's
    source files, remove all experiment artifacts line by line:

    -   `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` marker lines
    -   `# ORIGIN: ...` comment lines
    -   Experiment-only `evaluate()` function (unless it existed in the original
        file)
    -   Experiment-only `if __name__ == "__main__":` block (unless it existed in
        the original file)
    -   Experiment-only imports not used by the evolved code itself
    -   Collapse any resulting runs of 3+ blank lines down to 2

    Read `references/integration_patterns.md` (Scaffolding Cleanup section) for
    the full line-by-line stripping procedure, indentation adjustment rules, and
    verification steps.

    **After stripping, verify** no scaffolding remains: search for
    `EVOLVE-BLOCK` and `# ORIGIN:` in the prepared code -- both must return zero
    matches.

3.  **Match evolved regions to integration targets.** Use the source map (Step
    4.2a) or `ORIGIN` comments (Step 4.2b) to match each evolved region to its
    original file and location:

    -   If `ORIGIN` comment says `src/core/activation.py::relu (lines 12-18)`,
        the evolved code for `relu` goes back to that file.
    -   If the same `initial_program.py` has multiple EVOLVE-BLOCKs, match them
        to their respective `ORIGIN` comments by position (first block matches
        first ORIGIN before a block, etc.).

4.  **Handle multi-file experiments.** If the evolved program has multiple
    files, compare each against its initial version. Only integrate files that
    actually changed (files without EVOLVE-BLOCKs should be identical to the
    initial versions -- skip them).

### Step 4.4: Apply the changes

> **Prerequisite:** Step 4.3 must have already stripped all scaffolding
> (`EVOLVE-BLOCK` markers, `ORIGIN` comments, experiment boilerplate) from the
> evolved code. The code applied in this step must be clean.

**Before applying any changes**, consult the provenance metadata to determine
exactly where each code region belongs:

1.  Read `.evolve/source_map.json` (if it exists) for the authoritative mapping
    of experiment symbols to original file paths, line ranges, and integration
    modes.
2.  If no source map exists, parse `# ORIGIN:` comments in the evolved code for
    file paths and symbol names.
3.  Use `references/integration_patterns.md` for the full reference on
    provenance-driven integration, multi-file handling, scaffolding cleanup, and
    rollback procedures.

For each integration target from the plan:

**Function replacement (`function_replacement`):**

1.  Read the original source file.
2.  Locate the target function by name (using `original_symbol` from the source
    map, which may differ from the experiment's symbol name if it was renamed
    for flat imports).
3.  Replace the function body with the stripped evolved version.
4.  Preserve the original function signature (name, decorators, docstring)
    unless the evolved code intentionally changed them.
5.  Adjust indentation to match the original context (e.g., if the function is
    inside a class, re-indent accordingly).
6.  If the evolved code introduces new helper functions that were not in the
    original file, add them immediately before the target function.
7.  If the evolved code uses new imports, add them at the top of the file.
8.  Write the updated file.

**EVOLVE-BLOCK replacement (`evolve_block_replacement`):**

1.  Read the original source file.
2.  Find the `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` markers.
3.  Replace the content between them with the evolved code.
4.  **Strip the markers themselves** -- remove the `EVOLVE-BLOCK-START` and
    `EVOLVE-BLOCK-END` comment lines. They were added during experiment design
    and should not persist in the user's codebase.
5.  Write the updated file.

**Full file replacement (`full_file_replacement`):**

1.  Back up the original file: copy to `<original>.bak`.
2.  Write the evolved code as the new file content.
3.  Strip all `ORIGIN` and `EVOLVE-BLOCK` comments from the written file.

**Manual / new file (no source map, standalone experiment):**

1.  Save the evolved code to a user-specified path or
    `<PROJECT_DIR>/evolved_program.py`.
2.  Tell the user where the file was saved.

**Important: when multiple original files need updating** (e.g., Extract and
Isolate inlined functions from 3 different files, and 2 of those functions were
in EVOLVE-BLOCKs), apply changes to each file independently. Read each original
file, locate the target symbol, replace it, and write. Do NOT try to write all
changes to a single file.

### Step 4.5: Validate the integration

After applying changes, validate that the integrated code works:

**Step 4.5a: Syntax check**

```bash
python3 -c "import ast; ast.parse(open('<TARGET_FILE>').read())"
```

> On Windows, use `python` instead of `python3`.

If syntax check fails, the integration introduced a syntax error. Revert the
change and report the issue.

**Step 4.5b: Re-run the evaluator**

Run the evaluator against the integrated file to confirm the score is preserved:

```bash
ae --json program evaluate \
  --program-file <TARGET_FILE> \
  --evaluator <PROJECT_DIR>/evaluator.py \
  --backend local
```

Compare the score against the experiment's best score. If the scores match
(within 1% tolerance for floating-point differences), the integration is
successful.

If scores diverge significantly:

> **Score mismatch after integration.** The evolved code scored <X> in the
> experiment but <Y> after integration. This may indicate: - Import differences
> between the experiment and the original codebase - Context that was available
> during experiment evaluation but not in the integrated file - Multi-file
> dependencies that need to be copied over
>
> Would you like me to investigate? (y/n)

**Step 4.5c: Run existing tests (if available)**

If the original source file has associated tests (e.g., `test_<filename>.py` in
the same directory, or tests referenced in BUILD/pyproject.toml):

```bash
# For uv-managed projects:
uv run pytest <test_file>

# For general Python projects (use "python" on Windows):
python3 -m pytest <test_file>
```

If tests fail, report the failures and offer to revert:

> **Existing tests failed after integration.** <N> test(s) failed:
> <brief summary of failures>
>
> Options: 1. **Revert** the integration (restore original file) 2. **Keep** the
> changes and fix the test failures 3. **Review** the evolved code for
> compatibility issues

### Step 4.6: Present completion summary

After everything is done, present a completion message that leads with the
result and the key insight.

If integration was performed:

> **Result: <BASELINE> → <BEST> (+<REL>% improvement)**
>
> The evolved code from `<BEST_NICKNAME>` has been applied to `<TARGET_FILE>`.
>
> **What changed:** <1-sentence summary of the core algorithmic change>
>
> **Why it works:**
> <1-sentence explanation connecting the change to the problem>
>
> <PRACTICAL_IMPACT if applicable, e.g., "This saves X ms per call">
>
> -   Validation: <PASSED/FAILED>
> -   Report: `<REPORT_PATH>`
> -   Chart: `<CHART_PATH>`
> -   Interactive report: `<HTML_REPORT_PATH>` (open in browser, if generated)
>
> Next steps: - Review the changes in your editor - Run your full test suite to
> verify compatibility - Start a new experiment with refined parameters if
> needed

If integration was skipped:

> **Result: <BASELINE> → <BEST> (+<REL>% improvement)**
>
> **What changed:** <1-sentence summary>
>
> **Why it works:** <1-sentence explanation>
>
> -   Best program: `<BEST_NICKNAME>`
> -   Report: `<REPORT_PATH>`
> -   Chart: `<CHART_PATH>`
> -   Interactive report: `<HTML_REPORT_PATH>` (open in browser, if generated)
>
> To integrate later, you can retrieve the best program with: `ae --json program
> show <BEST_NICKNAME> --experiment <NICKNAME> --code`

If the experiment failed (no successful programs):

> **Experiment did not produce improvements.** All <N> evaluations either failed
> or scored equal to or below the baseline.
>
> Common causes and next steps: - **Evaluator too strict:** Relax constraints or
> increase timeout - **Search space too narrow:** Expand the EVOLVE-BLOCK
> boundaries - **Problem too hard for the model:** Try a different model or
> decompose the problem - **Report:** `<REPORT_PATH>`

--------------------------------------------------------------------------------

## Error Handling

For any `ae` command failure:

1.  Parse the JSON error output.
2.  Consult `references/debugging.md` for known error patterns.
3.  Suggest a specific fix.
4.  Retry after the fix is applied.

Common error patterns specific to post-experiment processing:

| Error                  | Likely Cause             | Fix                      |
| ---------------------- | ------------------------ | ------------------------ |
| "experiment not found" | Wrong nickname/ID        | Run `ae --json           |
:                        :                          : experiment list`         :
| "program not found"    | Wrong program nickname   | Run `ae --json results   |
:                        :                          : best <exp>` to find      :
:                        :                          : correct name             :
| Program code is empty  | Backend did not store    | Try `ae --json program   |
:                        : code                     : show <prog> --code       :
:                        :                          : --output-file out.py`    :
| Diff fails             | Parent program ID format | Fall back to manual diff |
:                        : issue                    : (Step 2.2)               :
| Eval score mismatch    | Environment differences  | Check imports and        |
:                        :                          : dependencies             :
| Integration syntax     | Marker mismatch or       | Revert and re-extract    |
: error                  : indentation              : carefully                :

--------------------------------------------------------------------------------

## Quick Reference

See `references/cli_reference.md` for the full command reference. Key commands
for this skill:

| Command                                    | Purpose                       |
| ------------------------------------------ | ----------------------------- |
| `ae --json experiment describe <exp>`      | Get experiment metadata       |
| `ae --json results best <exp> --top N`     | Top N programs by score       |
| `ae --json results history <exp>`          | All programs by creation time |
| `ae --json results failed <exp>`           | Failed programs with errors   |
| `ae --json program show <prog> --code`     | Get program source code       |
| `ae --json program show <prog> --code      | Save code to file             |
: --output-file <f>`                         :                               :
| `ae program diff <prog>`                   | Diff vs parent (no --json)    |
| `ae --json program evaluate --program-file | Validate integrated code      |
: <f> --evaluator <e>`                       :                               :
