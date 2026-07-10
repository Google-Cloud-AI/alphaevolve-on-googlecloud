# ae CLI Reference

Quick reference for `ae` CLI commands used by the Experiment Runner skill.

## Global Flags

| Flag | Description |
|------|-------------|
| `--json` | Output structured JSON. **Global flag: must go BEFORE subcommand** (e.g. `ae --json config show`) |
| `--compact` | Compact JSON output (single line) |
| `--verbose` | Enable verbose logging |
| `--project <id>` | Override project for this command |
| `--location <loc>` | Override location for this command |

## Configuration

### ae config

Interactive or non-interactive configuration setup.

```bash
# Non-interactive (set specific values)
ae config --project=my-project --engine=my-engine --location=global

# Set model(s) - bare name, or name=...,weight=... (repeatable)
ae config --models=gemini-3.5-flash

# Set named profile
ae config --name=staging --project=staging-project --engine=staging-engine
```

### ae config show

Display active profile configuration.

```bash
ae --json config show
```

JSON output includes: `profile`, `project`, `location`, `collection`, `engine`,
`session`, `model`, `base_url`.

### ae config test

Test API connectivity with current configuration.

```bash
ae --json config test
```

Returns success/failure with error details on failure.

### ae config list

List all configured profiles.

```bash
ae --json config list
```

### ae config discover

Discover ambient GCP configuration from the `gcloud` CLI without modifying
any `ae` settings. Useful for auto-detecting the user's project when `ae`
has not been configured yet.

```bash
ae --json config discover
```

JSON output includes: `gcloud_found`, `gcloud_path`, `project`,
`projects` (list of accessible projects).

### ae config switch

Switch active profile.

```bash
ae config switch staging
```

## Experiments

### ae experiment create

Create a new experiment.

```bash
ae --json experiment create \
  --max-programs 100 \
  --concurrency 4 \
  --problem-file problem.md \
  --title "My Experiment" \
  --models gemini-3.5-flash
```

| Flag             | Required | Default     | Description         |
| ---------------- | -------- | ----------- | ------------------- |
| `--max-programs` | Yes      | -           | Maximum programs to |
:                  :          :             : generate (must      :
:                  :          :             : be > 1)             :
| `--concurrency`  | No       | 4           | Parallel program    |
:                  :          :             : generation          :
| `--problem`      | No*      | -           | Inline problem      |
:                  :          :             : description         :
| `--problem-file` | No*      | -           | Problem description |
:                  :          :             : file                :
| `--title`        | No       | ""          | Experiment title    |
| `--language`     | No       | "python"    | Programming         |
:                  :          :             : language            :
| `--models`       | No       | from config | Model spec: bare    |
:                  :          :             : name or             :
:                  :          :             : name=...,weight=... :
:                  :          :             : (repeatable).       :
:                  :          :             : Replaces the        :
:                  :          :             : singular `model`    :
:                  :          :             : flag.               :

*One of `--problem` or `--problem-file` should be provided.

JSON output includes: `name` (resource name), `nickname`, `state`.

### ae experiment start

Start an experiment with an initial program and baseline score.

```bash
ae --json experiment start brave-otter \
  --program-dir ./experiment_dir \
  --score 42.5
```

| Flag | Required | Description |
|------|----------|-------------|
| `--program-dir` | Yes | Directory with program .py files |
| `--score` | Yes | Baseline score from evaluation |

The experiment argument can be a nickname, resource name, or ID.

### ae experiment describe

Get experiment metadata and status.

```bash
ae --json experiment describe brave-otter
```

JSON output includes: `name`, `nickname`, `state`, `createTime`,
`scoredProgramCount`, `totalProgramCount`.

### ae experiment list

List all experiments.

```bash
ae --json experiment list
```

### ae experiment resume

Resume a paused experiment.

```bash
ae --json experiment resume brave-otter
```

### ae experiment run

Run the automated acquire/evaluate/submit controller loop.

```bash
ae --json experiment run brave-otter \
  --evaluator evaluator.py \
  --max-iterations 50 \
  --timeout 60 \
  --backend local
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--evaluator` | Yes | - | Path to evaluator file |
| `--max-iterations` | No | 0 (unlimited) | Max evaluation iterations |
| `--timeout` | No | 60 | Timeout per evaluation (seconds) |
| `--backend` | No | "local" | Eval backend: "local" or "podman" |

### ae experiment delete

Delete an experiment and its programs.

```bash
ae --json experiment delete brave-otter
```

## Programs

### ae program evaluate

Evaluate a program locally using the evaluator script.

```bash
ae --json program evaluate \
  --program-dir ./experiment_dir \
  --evaluator evaluator.py \
  --backend local
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--program-file` | No* | - | Path to a local program .py file |
| `--program-name` | No* | - | Resource name or nickname (fetched from API) |
| `--program-dir` | No* | - | Directory containing program files |
| `--experiment` | No | - | Parent experiment (required with --program-name) |
| `--evaluator` | Yes | - | Path to the evaluator script |
| `--backend` | No | "local" | Eval backend: "local" or "podman" |
| `--timeout` | No | 60 | Max evaluation time in seconds |

*One of `--program-file`, `--program-name`, or `--program-dir` must be provided.

### ae program show

Get program content, state, and scores.

```bash
ae --json program show <program_name_or_nickname>
```

### ae program list

List programs in an experiment.

```bash
ae --json program list brave-otter
```

### ae program diff

Show diff between a program and its parent.

```bash
ae program diff <program_name_or_nickname>
```

## Results

### ae results best

Show top-scored programs.

```bash
ae --json results best brave-otter
```

### ae results history

Show all programs sorted by creation time.

```bash
ae --json results history brave-otter
```

## Models

See `models.md` in this references directory for the full list of available
model IDs and descriptions.
