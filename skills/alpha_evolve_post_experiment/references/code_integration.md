# Code Integration (Stage 4)

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

Field              | Meaning
------------------ | -------
`experiment_file`  | Which file in the experiment directory contains this code
`symbol`           | The function/class name (null for full-file mappings)
`is_evolve_block`  | Whether this region was inside an EVOLVE-BLOCK (i.e., evolved)
`original_file`    | Path to the original source file in the user's codebase
`original_lines`   | `[start, end]` line range in the original file
`original_symbol`  | Symbol name in the original file (may differ from `symbol` if renamed)
`integration_mode` | How to apply: `function_replacement`, `full_file_replacement`, `evolve_block_replacement`, or `skip`

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

Mode                         | When                                     | What happens
---------------------------- | ---------------------------------------- | ------------
**EVOLVE-BLOCK replacement** | Original file has `EVOLVE-BLOCK` markers | Replace content between markers
**Function replacement**     | Specific function was extracted          | Replace the function body
**Full file replacement**    | Entire file was the experiment target    | Replace the file contents
**Manual (new file)**        | No original file (standalone experiment) | Save evolved code as a new file

### Step 4.3: Extract and prepare the evolved code

Read the best program's code. Extract the evolved regions:

1.  **Parse EVOLVE-BLOCK markers:** Find all `# EVOLVE-BLOCK-START` /
    `# EVOLVE-BLOCK-END` pairs. Extract the code between each pair.

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
the same directory, or tests referenced in pyproject.toml):

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
> To integrate later, you can retrieve the best program with:
> `ae --json program show <BEST_NICKNAME> --experiment <NICKNAME> --code`

If the experiment failed (no successful programs):

> **Experiment did not produce improvements.** All <N> evaluations either failed
> or scored equal to or below the baseline.
>
> Common causes and next steps: - **Evaluator too strict:** Relax constraints or
> increase timeout - **Search space too narrow:** Expand the EVOLVE-BLOCK
> boundaries - **Problem too hard for the model:** Try a different model or
> decompose the problem - **Report:** `<REPORT_PATH>`
