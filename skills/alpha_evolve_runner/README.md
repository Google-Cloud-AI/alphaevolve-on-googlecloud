# Alpha Evolve Experiment Runner Skill

AI agent skill for configuring, verifying, and launching AlphaEvolve
experiments using the `ae` CLI.

## Overview

Takes experiment artifacts (program, evaluator, problem description) and
launches an experiment on the AlphaEvolve backend through the `ae` CLI.

This is one of three AlphaEvolve skills:

1. **Experiment Design** -- Problem definition, initial program, evaluator
2. **Experiment Runner** (this skill) -- Configuration, verification, launch
3. **Experiment Monitor** -- Evaluation loop, progress tracking, results

Handles:

- GCP configuration auto-discovery and setup
- API connectivity verification
- Evaluator validation with baseline scoring
- Experiment creation and launch

## Handoff

- **Input:** Artifacts from the Design skill or user-provided files
- **Output:** An experiment nickname (e.g., `brave-otter`) for the Monitor
  skill

## Prerequisites

- `ae` CLI installed (see the `ae` CLI documentation for installation instructions)
- `gcloud` CLI installed (the `ae` CLI discovers it automatically; run
  `gcloud auth application-default login` if credentials are needed)
- A Google Cloud project with AlphaEvolve enabled

## Skill Structure

```
experiment_runner/
  OWNERS
  README.md
  skills/alpha_evolve_runner/
    SKILL.md              # Main skill instructions
    references/
      cli_reference.md    # ae CLI command reference
      debugging.md        # Troubleshooting guide
```
