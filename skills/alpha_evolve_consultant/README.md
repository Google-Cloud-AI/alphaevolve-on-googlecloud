# AlphaEvolve Consultant Skill

A strictly-grounded Q&A skill that answers questions about AlphaEvolve based
on the official expert consultant reference guide.

## What This Skill Does

This skill acts as an AlphaEvolve expert consultant. It answers questions
about experiment design, evaluator implementation, scoring strategies,
EVOLVE-BLOCK placement, concurrency tuning, LLM mixture selection,
troubleshooting, API usage, and the theoretical foundations of AlphaEvolve.

All answers are grounded strictly in the bundled reference guide. The skill
never speculates or provides information beyond what the guide covers.

## How It Differs from Workflow Skills

The existing AlphaEvolve skills are **workflow skills** that execute
multi-step processes:

- `alpha-evolve-experiment-design` -- creates experiment files
- `alpha-evolve-runner` -- launches experiments
- `alpha-evolve-monitor` -- monitors running experiments
- `alpha-evolve-orchestrator` -- chains the above end-to-end

This skill is a **consultant skill** -- it is read-only and advisory. It
answers questions but does not create files, launch experiments, or run
commands.

## Reference Structure

The guide content is split into 7 topic-focused reference files for
on-demand loading:

| Reference File                      | Guide Sections | Topics                                        |
| ----------------------------------- | -------------- | --------------------------------------------- |
| `suitability_and_architecture.md`   | 1-2            | What AE is, suitability, architecture          |
| `experiment_design.md`              | 3-4            | Initial program, EVOLVE-BLOCK placement        |
| `evaluator_and_scoring.md`          | 5              | Evaluator design, scoring, reward hacking      |
| `runtime_configuration.md`          | 6-10           | Data, concurrency, LLM mixtures, hyperparams   |
| `troubleshooting.md`                | 11             | Failure modes, debugging workflows             |
| `api_and_infrastructure.md`         | 12-16          | API reference, architecture, languages, cost   |
| `domain_background.md`             | 17             | Evolutionary computation, key results          |

## Trigger Phrases

- "AlphaEvolve question"
- "AE best practices"
- "Is my problem suitable for AE?"
- "How should I design my evaluator?"
- "Why is my experiment stuck?"
- "What concurrency should I use?"
- "AE troubleshooting"

## Source

Based on the AlphaEvolve Expert Consultant Reference document.
