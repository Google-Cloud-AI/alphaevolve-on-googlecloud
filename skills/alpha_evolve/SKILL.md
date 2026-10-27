---
name: alpha-evolve
description: >
  Run Google AlphaEvolve (Cloud API, `ae` CLI), which improves code by
  LLM-driven evolutionary search against a measurable score. Covers the whole
  lifecycle: check whether a problem fits, design the experiment (seed program
  with EVOLVE-BLOCK markers, evaluator, tests), install and configure the `ae`
  CLI, launch, run the evaluation loop and monitor progress, analyze results
  and merge the best program back into the code, and troubleshoot stuck or
  failed experiments. Use when the user says "optimize/evolve this function
  with AlphaEvolve", "use evolutionary search", "find a better algorithm" or
  "make this faster" against a benchmark or score, "is my problem a good fit
  for AlphaEvolve", "design an AlphaEvolve experiment", "launch/monitor my
  experiment", "show experiment results", "apply the best program", "why is
  my experiment stuck", or asks about AlphaEvolve, EVOLVE-BLOCK markers, or
  evaluators and reward hacking in evolutionary search.
---

# AlphaEvolve

AlphaEvolve evolves code. An LLM proposes changes to the marked regions of a
Python program, the user's evaluator scores each candidate locally, and the
backend keeps the best programs. You drive it with the `ae` CLI.

All paths below are relative to this skill's directory. Read a reference file
when you reach its step. Do not load them all up front.

## Rules for every phase

1.  **Run the setup checks once per session**, before the first `ae` command:
    `references/setup.md` (CLI install and discovery, network, credentials,
    Gemini Enterprise license, `ae config`).
2.  **`--json` is a global flag.** Write `ae --json experiment describe <exp>`,
    never `ae experiment describe --json <exp>`.
3.  **Never execute user code directly.** Evaluation goes through
    `ae program evaluate`, `ae experiment run`, or `uv run pytest`.
4.  **Never start version-control workflows.** No commits, bug searches, or
    commit messages unless the user asks.
5.  **Be concise.** State what you are doing, show results, and ask only when
    needed.

## Pick the starting point

-   **A question about AlphaEvolve** (fit, best practices, evaluator or scoring
    advice, concurrency, models, background): consultant mode, read-only. Read
    `references/consultant.md`.
-   **A problem or code to optimize, but no evaluator**: Phase 1, Design. Read
    `references/experiment_design.md`.
-   **A program with EVOLVE-BLOCK markers and an evaluator**: Phase 2, Runner.
    Read `references/runner.md`.
-   **A running experiment** (nickname, ID, or resource name): Phase 3, Monitor.
    Read `references/monitor.md`.
-   **A finished experiment, or results or a merge wanted**: Phase 4,
    Post-experiment. Read `references/post_experiment.md`.
-   **A stuck, paused, or failed experiment**: read
    `references/consultant/troubleshooting.md`, then the `debugging.md` of the
    current phase.

"Optimize my code at `<path>`" means start at Phase 1. Do not ask what
"optimize" means. If you cannot tell where the user is, ask:

> I can help you with AlphaEvolve at any stage. Where are you?
>
> 1.  **Start from scratch**: I have a problem to optimize
> 2.  **Launch an experiment**: I have program and evaluator files ready
> 3.  **Monitor an experiment**: I have a running experiment to check on
> 4.  **Analyze results**: I have a completed experiment to review

## End-to-end flow

When you will run more than one phase, read `references/orchestrator.md` first.
It holds the handoff artifacts each phase passes on, the checks for entering at
a later phase, and error recovery.

Each phase ends at a gate. When the gate holds, move to the next phase in the
same response.

1.  **Design**: the project directory has all 9 files and `uv run pytest`
    passes. Go to Runner. Ask first only if the user asked just to design or set
    up an experiment.
2.  **Runner**: the experiment is ACTIVE and the user has its nickname. Go to
    Monitor at once.
3.  **Monitor**: the experiment is COMPLETED, FAILED, or CANCELLED. Go to
    Post-experiment at once.
4.  **Post-experiment**: the report is shown, and the code is merged and
    validated if the user agreed. Done.

Do not stop between phases to ask "should I continue?". The confirmations that
remain are the ones the phase guides require: the configuration table and the
launch summary in the runner phase (skipped when the user asked for an
unattended run), and the merge in the post-experiment phase.

## Other references

-   `references/models.md`: model IDs and the default model.
-   `references/<phase>/cli_reference.md` and `references/<phase>/debugging.md`:
    CLI commands and error fixes for each phase.
-   `references/experiment_design/examples/circle_packing/`: a complete worked
    example experiment.

## Limits

-   Python only, tested with Python 3.13.7 and newer.
-   One evolved code location at a time has been tested. Context can come from
    several files.
-   Works on Linux, macOS, and Windows.
