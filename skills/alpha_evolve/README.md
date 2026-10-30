# AlphaEvolve Skill

One agent skill that runs the whole AlphaEvolve workflow from a coding
assistant: fit check and expert Q&A, experiment design, setup, launch,
monitoring, results analysis, and merging the best program back into the code.

Only `SKILL.md` is loaded when the skill triggers. It routes the agent to the
reference file for the current phase, so the rest is read on demand.

## Layout

```
alpha_evolve/
  SKILL.md                      # Triggers, shared rules, phase router
  references/
    setup.md                    # ae CLI install, credentials, GE license, ae config
    consultant.md               # Read-only expert Q&A
    consultant/                 # Reference guide split by topic
    experiment_design.md        # Phase 1: design (clarify, then implement)
    experiment_design/          # Phase guides, evaluator patterns, schema, example
    runner.md                   # Phase 2: configure, verify, launch
    runner/                     # CLI reference, debugging
    monitor.md                  # Phase 3: control loop, progress reports
    monitor/                    # CLI reference, debugging
    post_experiment.md          # Phase 4: report, code review, merge
    post_experiment/            # CLI reference, debugging, integration, charts
    orchestrator.md             # Full end-to-end playbook
    orchestrator/               # Handoff contracts between phases
    models.md                   # Model IDs and the default model
```

## Where the former skills went

This skill replaces six separate skills. Each former `SKILL.md` body is now a
phase guide, and its `references/` directory moved next to it.

Former skill                     | Now
-------------------------------- | ---
`alpha_evolve_orchestrator`      | `SKILL.md` (router) and `references/orchestrator.md`
`alpha_evolve_consultant`        | `references/consultant.md`, `references/consultant/`
`alpha_evolve_experiment_design` | `references/experiment_design.md`, `references/experiment_design/`
`alpha_evolve_runner`            | `references/runner.md`, `references/runner/`, `references/setup.md`
`alpha_evolve_monitor`           | `references/monitor.md`, `references/monitor/`
`alpha_evolve_post_experiment`   | `references/post_experiment.md`, `references/post_experiment/`

`ae skills install` installs this skill and removes the six former skill
directories from the destination.
