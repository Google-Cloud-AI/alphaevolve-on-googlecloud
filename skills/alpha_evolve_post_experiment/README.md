# Alpha Evolve Post-Experiment Processing Skill

AI agent skill for analyzing completed AlphaEvolve experiments, producing
visual reports, and integrating evolved code back into the user's codebase.

## Overview

Takes a completed experiment and delivers two things that are critical for
the user experience after an experiment finishes:

1. **Comprehensive results visualization** -- Score progression charts,
   improvement metrics, failure analysis, and top programs comparison.
2. **Code integration** -- Fetches the best evolved program, reviews the
   changes, validates them, and applies them back to the original source
   file with full validation.

This is one of four AlphaEvolve skills:

1. **Experiment Design** -- Problem definition, initial program, evaluator
2. **Experiment Runner** -- Configuration, verification, launch
3. **Experiment Monitor** -- Evaluation loop, progress tracking
4. **Post-Experiment** (this skill) -- Results analysis, visualization,
   code integration

## The Post-Experiment Process

The skill executes a four-stage workflow:

### Stage 1: Quick Results Overview

- Fetches experiment metadata and top programs
- Presents a brief inline summary: result, improvement, top 3 programs

### Stage 2: Code Review & Validation

- Fetches the best program's source code
- Shows a unified diff against the initial program
- Explains changes semantically (what changed and why it is better)
- Checks for reward hacking (hardcoded outputs, evaluator manipulation)

### Stage 3: Report

- Generates score progression chart (PNG via `ae results plot`)
- Writes the full markdown report (metrics, approaches table, code
  changes, failure analysis)
- Generates interactive HTML report with hoverable/clickable chart
  and syntax-highlighted code

### Stage 4: Code Integration (optional)

- Asks the user whether to integrate evolved code back
- Loads the source map (`.evolve/source_map.json`) for provenance-aware
  integration, or falls back to ORIGIN comments / heuristics
- Determines integration mode per target file (EVOLVE-BLOCK replacement,
  function replacement, full file replacement, or manual)
- Strips all experiment scaffolding (EVOLVE-BLOCK markers, ORIGIN
  comments, experiment harness code)
- Extracts evolved code and applies it to the original source file(s)
- Validates: syntax check, evaluator re-run, existing test suite
- Provides rollback guidance if validation fails

## Outputs

| Artifact | Description |
|----------|-------------|
| `experiment_report.md` | Full markdown report with metrics, approaches, and code |
| `experiment_report.html` | Interactive HTML report with hoverable chart |
| `score_progression.png` | Matplotlib scatter + line chart |
| Integrated source files | Evolved code applied back to the original codebase |

## Handoff

- **Input:** Experiment nickname (e.g., `brave-otter`) from the Monitor
  skill, plus the project directory and optionally the original source
  file path.
- **Output:** Integrated code in the user's source file, plus report
  artifacts (`experiment_report.md`, `experiment_report.html`,
  `score_progression.png`) in the project directory.

## Prerequisites

- `ae` CLI installed (see the `ae` CLI documentation for installation
  instructions)
- A completed AlphaEvolve experiment (state: COMPLETED, FAILED, or
  CANCELLED)

## Skill Structure

```
alpha_evolve_post_experiment/
  README.md
  SKILL.md                        # Main skill instructions (4 stages)
  references/
    cli_reference.md              # ae CLI commands for post-experiment
    integration_patterns.md       # Code integration modes and patterns
    visualization.md              # Chart generation (matplotlib + HTML)
    debugging.md                  # Troubleshooting guide
```
