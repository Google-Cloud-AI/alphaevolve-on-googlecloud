# ae CLI Reference for Post-Experiment Processing

Quick reference for `ae` CLI commands used by the Post-Experiment skill.

## Global Flags

These flags apply to ALL commands and must go **BEFORE** the subcommand.

| Flag | Description |
|------|-------------|
| `--json` | Output structured JSON (ALWAYS use this) |
| `--compact` | Compact tab-delimited text output |
| `--verbose` | Enable verbose/debug logging |
| `--project <id>` | Override project for this command |
| `--location <loc>` | Override location for this command |

**Correct:** `ae --json results best exp-brave-otter`
**Wrong:** `ae results best exp-brave-otter --json`

## Experiment Identifiers

Experiments and programs can be identified by any of these forms:

| Form | Example |
|------|---------|
| Nickname | `exp-brave-otter` (experiments) or `prog-swift-panda` (programs) |
| Short ID | `abc123def` |
| Full resource name | `projects/123/locations/global/.../alphaEvolveExperiments/abc123` |

The CLI resolves all forms automatically.

## Results Commands

### ae results best

Show top-scoring programs sorted by score descending. This is the primary
command for post-experiment analysis.

```bash
ae --json results best <EXPERIMENT> --top <N>
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--top` | No | 5 | Number of top programs to show |

**JSON output:** Array of program objects. Each program has:

- `name`: Full resource name
- `nickname`: Two-word nickname
- `state`: Program state
- `createTime`: Creation timestamp
- `evaluation.scores.scores[0].score`: The program's score
- `evaluation.scores.scores[0].metric`: Score metric name
- `content.files[].content`: Program source code (if included)

### ae results history

Show all programs sorted by creation time. Essential for building the score
progression chart.

```bash
ae --json results history <EXPERIMENT>
```

**JSON output:** Same format as `results best`, sorted by `createTime`
ascending. Use this to compute running best score over time.

### ae results failed

Show all programs that failed evaluation, with error details. Use for
failure analysis.

```bash
ae --json results failed <EXPERIMENT>
```

**JSON output:** Array of program objects with null scores. Each includes:

- `nickname`: Program nickname
- `evaluation.insights[]`: Error messages and tracebacks
  - `label`: Insight type (e.g., "error", "traceback", "stdout")
  - `text`: Insight content

## Experiment Commands

### ae experiment describe

Get experiment metadata, state, and configuration. Used for report header.

```bash
ae --json experiment describe <EXPERIMENT>
```

**JSON output fields:**

- `name`: Full resource name
- `nickname`: Two-word nickname
- `state`: Experiment state (may have `EXPERIMENT_STATE_` prefix)
- `createTime`: ISO-8601 creation timestamp
- `config.title`: Experiment title
- `config.model`: Model used
- `stats.evaluatedCandidatesCount`: Number of evaluated programs
- `stats.bestScore`: Best score (may be absent)

## Program Commands

### ae program show

Get program content, optionally with source code. Primary command for
fetching evolved code for integration.

```bash
ae --json program show <PROGRAM> --experiment <EXPERIMENT> --code
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--experiment` | No* | - | Parent experiment (*required with short IDs) |
| `--code` | No | false | Include source code in output |
| `--output-file` | No | - | Save code to file instead of stdout |
| `--insights` | No | false | Show evaluation insights |

**Tip:** Use `--output-file <path>` for large programs to avoid terminal
truncation:

```bash
ae --json program show <PROGRAM> --experiment <EXPERIMENT> --code \
  --output-file best_evolved_program.py
```

### ae program diff

Show unified diff between a program and its parent. Does NOT support
`--json` output.

```bash
ae program diff <PROGRAM> --experiment <EXPERIMENT>
```

**Known issue:** May fail with "Invalid program name" if the API returns
short parent IDs. Fall back to manual diff if this happens.

### ae program evaluate

Evaluate a program locally. Used to validate integrated code after
applying changes to the original source file.

```bash
ae --json program evaluate \
  --program-file <PATH> \
  --evaluator <PATH> \
  --backend local
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--program-file` | Yes | - | Path to the program file to evaluate |
| `--evaluator` | Yes | - | Path to the evaluator script |
| `--backend` | No | `local` | `local` or `podman` |
| `--timeout` | No | 60 | Max evaluation time in seconds |

## Visualization Commands

### ae results plot

Generate a score progression chart as a PNG image.

```bash
ae results plot <EXPERIMENT> --output <PATH> [--title <TITLE>]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--output`, `-o` | No | `score_progression.png` | Output PNG file path |
| `--title` | No | `Experiment: <nickname>` | Chart title |

### ae results report

Generate a self-contained interactive HTML report with a hoverable
chart and embedded markdown content.

```bash
ae results report <EXPERIMENT> --output <PATH> [--markdown <MD_PATH>]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--output`, `-o` | No | `experiment_report.html` | Output HTML file path |
| `--markdown` | No | (none) | Path to markdown report to embed below the chart |

The HTML report includes an interactive canvas-based chart where
hovering over any data point shows the program nickname, score, and
a code preview (first 30 lines).

## Experiment States

| State | Meaning | Post-Experiment Action |
|-------|---------|----------------------|
| `COMPLETED` | Finished successfully | Full analysis + integration |
| `FAILED` | Failed | Partial analysis (show what data exists) |
| `CANCELLED` | Cancelled | Partial analysis (show what data exists) |
| `ACTIVE` | Still running | Tell user to wait or use Monitor skill |
| `PAUSED` | Paused by backend | Tell user to resume or analyze partial results |

Note: States may appear with an `EXPERIMENT_STATE_` prefix (e.g.,
`EXPERIMENT_STATE_COMPLETED`). Strip this prefix for display.
