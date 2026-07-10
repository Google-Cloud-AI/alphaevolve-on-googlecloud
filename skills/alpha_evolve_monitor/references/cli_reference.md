# ae CLI Reference for Experiment Monitoring

Quick reference for `ae` CLI commands used by the Experiment Monitor skill.

## Global Flags

These flags apply to ALL commands and must go **BEFORE** the subcommand.

| Flag | Description |
|------|-------------|
| `--json` | Output structured JSON (ALWAYS use this) |
| `--compact` | Compact tab-delimited text output |
| `--verbose` | Enable verbose/debug logging |
| `--project <id>` | Override project for this command |
| `--location <loc>` | Override location for this command |

**Correct:** `ae --json experiment describe exp-brave-otter`
**Wrong:** `ae experiment describe exp-brave-otter --json`

## Experiment Identifiers

Experiments can be identified by any of these forms (used interchangeably):

| Form | Example |
|------|---------|
| Nickname | `exp-brave-otter` (experiments) or `prog-swift-panda` (programs) |
| Short ID | `abc123def` |
| Full resource name | `projects/123/locations/global/.../alphaEvolveExperiments/abc123` |

The CLI resolves all forms automatically.

## Experiment Commands

### ae experiment create

Create a new experiment on the backend. Returns a nickname.

```bash
ae --json experiment create \
  --max-programs <N> \
  --concurrency <N> \
  --problem-file <PATH> \
  --title "<TITLE>" \
  --models <MODEL_NAME>
```

| Flag             | Required    | Default     | Description         |
| ---------------- | ----------- | ----------- | ------------------- |
| `--max-programs` | Yes         | -           | Max candidate       |
:                  :             :             : programs to         :
:                  :             :             : generate (must      :
:                  :             :             : be > 1)             :
| `--concurrency`  | No          | 4           | Parallel program    |
:                  :             :             : generation          :
| `--problem`      | No*         | -           | Inline problem      |
:                  :             :             : description         :
| `--problem-file` | No*         | -           | Path to problem     |
:                  :             :             : description         :
:                  :             :             : markdown            :
| `--title`        | No          | ""          | Human-readable      |
:                  :             :             : experiment title    :
| `--language`     | No          | "python"    | Programming         |
:                  :             :             : language            :
| `--models`       | Recommended | from config | Model spec: bare    |
:                  :             :             : name or             :
:                  :             :             : name=...,weight=... :
:                  :             :             : (repeatable).       :
:                  :             :             : Replaces the        :
:                  :             :             : singular `model`    :
:                  :             :             : flag.               :

*One of `--problem` or `--problem-file` should be provided.

**Does NOT accept:** `--program-file`, `--evaluator`, `--program-dir`.

### ae experiment start

Upload the initial program and baseline score. Activates the experiment.

```bash
ae --json experiment start <EXPERIMENT> \
  --program-dir <DIRECTORY> \
  --score <FLOAT>
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--program-dir` | Yes | - | Directory with program .py files |
| `--score` | Yes | - | Baseline score from local evaluation |

**Does NOT accept:** `--evaluator`, `--problem-file`, `--models`.

### ae experiment describe

Get experiment metadata, state, configuration, and stats.

```bash
ae --json experiment describe <EXPERIMENT>
```

**JSON output fields:**

- `name`: Full resource name
- `nickname`: Two-word nickname
- `state`: Experiment state (may have `EXPERIMENT_STATE_` prefix)
- `createTime`: ISO-8601 creation timestamp
- `config.title`: Experiment title
- `config.problemDescription`: Problem description text
- `config.programLanguage`: Programming language
- `config.model`: Model being used
- `stats.evaluatedCandidatesCount`: Number of evaluated programs
- `stats.bestScore`: Best score (may be absent)
- `evaluatedProgramsCount`: Alternative location for eval count
- `bestScore`: Alternative location for best score

### ae experiment list

List all experiments.

```bash
ae --json experiment list
```

Returns a JSON array of experiment objects sorted by `createTime` descending.

### ae experiment run

Run the automated acquire + evaluate + submit controller loop.

```bash
ae --json experiment run <EXPERIMENT> \
  --evaluator <EVALUATOR_FILE> \
  --max-iterations <N> \
  --timeout <SECONDS> \
  --backend <local|podman>
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--evaluator` | Yes | - | Path to evaluator script |
| `--max-iterations` | No | 0 (unlimited) | Max evaluation iterations |
| `--timeout` | No | 60 | Per-evaluation timeout in seconds |
| `--backend` | No | `local` | Eval backend: `local` or `podman` |
| `--dashboard` | No | None | Path to write a live-updating markdown dashboard |

**Behavior:**

1. Acquires 1 candidate program from the experiment queue
2. Evaluates it locally using the evaluator script
3. Submits the score back to the API
4. Repeats until max_iterations, terminal state, or Ctrl+C

**JSON output** (final, after loop ends):

```json
{
  "total_evaluated": 42,
  "total_succeeded": 38,
  "total_failed": 4,
  "best_score": 2.89,
  "best_program": "projects/.../alphaEvolvePrograms/abc123"
}
```

**Terminal states** that stop the loop: `COMPLETED`, `FAILED`, `CANCELLED`.

### ae experiment resume

Resume a paused experiment.

```bash
ae --json experiment resume <EXPERIMENT>
```

## Results Commands

### ae results best

Show top-scoring programs sorted by score descending.

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

Show all programs sorted by creation time (evaluation history).

```bash
ae --json results history <EXPERIMENT>
```

**JSON output:** Same format as `results best`, sorted by `createTime`
ascending.

### ae results failed

Show all failed programs with their error insights and evolved code.

```bash
ae results failed <EXPERIMENT>
```

Displays each failed program's nickname, error messages, tracebacks, and
the evolved code block. Use `--json` for structured output:

```bash
ae --json results failed <EXPERIMENT>
```

## Program Commands

### ae program evaluate

Run a local evaluation of a program file against an evaluator.

```bash
ae --json program evaluate \
  --program-file <PATH> \
  --evaluator <PATH> \
  --backend local
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--program-file` | Yes | - | Path to the program to evaluate |
| `--evaluator` | Yes | - | Path to the evaluator script |
| `--backend` | No | `local` | `local` or `podman` |

Note: Both `--program-file` (single file) and `--program-dir` (directory)
are supported. Use `--program-dir` for multi-file experiments.

### ae program show

Show details of a specific program, optionally with source code and/or
evaluation insights.

```bash
ae --json program show <PROGRAM> --experiment <EXPERIMENT> --code
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--experiment` | No* | - | Parent experiment (required with short IDs) |
| `--code` | No | false | Include source code in output |
| `--insights` | No | false | Show evaluation insights (errors, tracebacks) |

**Parent program references:** `program show` displays a `Parents` field.
The API returns parent references as short numeric indices (e.g., `#1`,
`#9`), not as nicknames or full resource names. These short IDs are NOT
queryable — do NOT try `ae program show 9`. They only indicate which
generation the program descended from.

### ae program diff

Show a unified diff between a program and its parent.

```bash
ae program diff <PROGRAM> --experiment <EXPERIMENT>
```

Note: `diff` output is human-readable unified diff format. It does not
support `--json` output. Do NOT use `--json` with this command.

**Known issue:** `program diff` may fail with "Invalid program name" if
the API returns short parent IDs instead of full resource names. If this
happens, use `ae program show <prog> --code` to view the evolved code
directly instead of diffing against the parent.

## Experiment States

| State | Meaning | Action |
|-------|---------|--------|
| `ACTIVE` | Running, accepting evaluations | Monitor and run control loop |
| `INITIALIZED` | Created but not started | Needs `ae experiment start` |
| `COMPLETED` | Finished successfully | Show final report |
| `FAILED` | Failed | Check errors, show what we have |
| `PAUSED` | Paused by the backend | Resume with `ae experiment resume` |
| `CANCELLED` | Cancelled | Show final report |

Note: States may appear with an `EXPERIMENT_STATE_` prefix (e.g.,
`EXPERIMENT_STATE_COMPLETED`). Strip this prefix for display.

**There is no `ae experiment pause` command.** Experiments are paused
automatically by the backend after ~5 hours of idle time (no evaluations
submitted). Use `ae experiment resume` to resume, then restart the
evaluation loop with `ae experiment run`.

## Models

See the Runner skill's `references/models.md` for the full list of
available model IDs and descriptions.
