# Alpha Evolve Experiment Orchestrator Skill

Orchestrator skill that chains the Design, Runner, and Monitor skills together
for a complete end-to-end AlphaEvolve experience.

## Overview

This orchestrator provides the same end-to-end workflow as the original
monolithic AlphaEvolve skill (v0), but built on the modular v2 skill
architecture. It automatically detects where the user is in the experiment
lifecycle and delegates to the appropriate sub-skill.

The four sub-skills it coordinates:

1.  **Experiment Design** -- Problem definition, initial program, evaluator
2.  **Experiment Runner** -- Configuration, verification, launch
3.  **Experiment Monitor** -- Evaluation loop, progress tracking
4.  **Post-Experiment** -- Results analysis, visualization, code integration

## Entry Points

Users can enter the workflow at any phase:

-   **From scratch** (no artifacts): Starts at Design phase
-   **With existing files** (program + evaluator): Skips to Runner phase
-   **With a running experiment** (nickname/ID): Skips to Monitor phase
-   **With a completed experiment** (nickname/ID): Skips to Post-Experiment
    phase

## Handoff Contracts

| From    | To              | Handoff Artifact         |
| ------- | --------------- | ------------------------ |
| Design  | Runner          | Project directory with   |
:         :                 : program file (any name), :
:         :                 : `evaluator.py`,          :
:         :                 : `problem_description.md` :
| Runner  | Monitor         | Experiment nickname      |
:         :                 : (e.g., `brave-otter`) +  :
:         :                 : evaluator file path      :
| Monitor | Post-Experiment | Experiment nickname +    |
:         :                 : project directory +      :
:         :                 : original source file     :

## Skill Structure

```
alpha_evolve_orchestrator/
  README.md
  SKILL.md                  # Main orchestrator instructions
  references/
    handoff_contracts.md    # Data contracts between phases
```
