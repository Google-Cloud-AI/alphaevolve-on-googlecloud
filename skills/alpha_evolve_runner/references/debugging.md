# Debugging Guide

Troubleshooting guide for common issues when launching AlphaEvolve experiments
with the `ae` CLI.

## Configuration Issues

### "No config profile found"

The `ae` CLI has not been configured yet.

```bash
ae config --project=<PROJECT_ID> --engine=<ENGINE_ID> --location=global
```

### `ae config discover` returns no project

The user has not set a default GCP project in their gcloud configuration.
Ask the user which GCP project to use, then set it with
`ae config --project=<PROJECT_ID>`.

### Engine auto-discovery returns no results

The project may not have an AlphaEvolve engine provisioned. Check:

```bash
ae --json engine list
```

If empty, the user needs to create an engine first via the Cloud Console or
API. See the AlphaEvolve Cloud documentation.

## Connectivity Issues

### 404 Not Found

**Cause:** The engine does not exist in the specified project/location.

**Fix:**

1. Verify the engine name: `ae --json config show`
2. List available engines: `ae --json engine list`
3. Update config: `ae config --engine=<correct_engine>`

### 403 Forbidden

**Cause:** The user lacks permissions on the project.

**Fix:**

1. Ensure the user has the `Discovery Engine Editor` IAM role
2. Check project access: `gcloud projects get-iam-policy <PROJECT_ID>`
3. If using a service account, verify it has the required roles

### Authentication errors / "Could not automatically determine credentials"

**Cause:** Application Default Credentials (ADC) are not configured.

**Fix:**

```bash
gcloud auth application-default login
```

### DNS resolution / network errors

**Cause:** Network connectivity issue or incorrect base URL.

**Fix:**

1. Verify network connectivity: `curl -s https://discoveryengine.googleapis.com`
2. Check base URL: `ae --json config show` (look at `base_url` field)
3. If using a non-prod endpoint, verify the URL is correct

## Evaluation Issues

### "ae program evaluate" fails with ImportError

**Cause:** The evaluator or program has Python dependencies not available in
the local environment.

**Fix (Option A):** Install missing dependencies:

```bash
pip install <missing_package>
```

**Fix (Option B):** Switch to podman backend (provides isolated environment):

```bash
ae --json program evaluate --program-file <prog> --evaluator <eval> --backend podman
```

### ImportError for installed packages (e.g., numpy) when using wrapper scripts

**Cause:** When using a wrapper script or custom `ae` invocation (e.g., with
modified `HOME` or `PYTHONPATH`), the system site-packages may not be on the
Python path. The package is installed but the `ae` process cannot find it.

**Fix:** Add the system site-packages to `PYTHONPATH` before invoking `ae`.
For example, on Unix:

```bash
export PYTHONPATH="$(python3 -c 'import site; print(":".join(site.getsitepackages()))')":$PYTHONPATH
```

Adapt the syntax for your shell if not using bash.

**Prevention:** Avoid creating wrapper scripts that modify `HOME` or
`PYTHONPATH` unless absolutely necessary. See the Prerequisites section in
the main SKILL.md for the recommended approach to CLI discovery.

### Evaluation returns score of 0 or NaN

**Cause:** The evaluator's `evaluate()` function is likely not computing the
score correctly for the initial program.

**Diagnosis:**

1. Check the evaluator's `evaluate()` function logic
2. Run the evaluator manually to see full output:

    ```bash
    ae program evaluate --program-file <prog> --evaluator <eval> --backend local
    ```

    (without `--json` to see full stderr/stdout)
3. Common issues:
   - Division by zero in scoring logic
   - Evaluator expects different function signatures than the program provides
   - Missing test data or fixtures

### Evaluation hangs or times out

**Cause:** The program or evaluator has an infinite loop or very long
computation.

**Fix:**

1. Add a timeout to the evaluation: check `ae program evaluate --help` for
   timeout flags
2. Review the program for infinite loops
3. Consider using podman backend which has built-in resource limits

## Model Selection Issues

### "experiment create" fails with 400 Invalid Argument

**Cause:** The model name may be invalid or unavailable for the configured
region (the API validates `--models` names and returns `INVALID_ARGUMENT`).

**Fix:**

1.  Read `references/models.md` for the recommended model names and regions.
2.  Use the recommended default: `--models gemini-3.5-flash` (available in
    global, us, and eu).
3.  If it fails, the name is likely unavailable in your region — confirm the
    region with `ae --json config show`.
4.  For a higher-quality mixture, pair flash with `gemini-3.1-pro-preview`
    (global only): `--models name=gemini-3.5-flash,weight=0.9 --models
    name=gemini-3.1-pro-preview,weight=0.1`.
5.  Do NOT guess model names that are not in `models.md`.
6. After **2 failed model attempts**, ask the user which model they want.

## Experiment Creation Issues

### "invalid program" when starting experiment

**Cause:** The initial program file is missing required `EVOLVE-BLOCK` markers.

**Fix:** Ensure the program has properly formatted markers:

```python
# EVOLVE-BLOCK-START
def my_function():
    # This code will be evolved
    pass
# EVOLVE-BLOCK-END
```

### "experiment already started"

**Cause:** Attempting to start an experiment that is already active.

**Fix:** The experiment is running. Use the Monitor skill or:

```bash
ae --json experiment describe <nickname>   # check status
ae experiment run <nickname> --evaluator <eval>  # run eval loop
```

### "quota exceeded"

**Cause:** The project has hit its AlphaEvolve quota limit.

**Fix:**

1. Check current experiments: `ae --json experiment list`
2. Delete completed/failed experiments: `ae experiment delete <nickname>`
3. Request quota increase through Cloud Console

## Escalation Protocol

> **CRITICAL: Follow the error budget rules in the main SKILL.md.** Never
> retry the same failing step more than 3 times without asking the user.

### Errors that require immediate user escalation (do NOT retry)

| Error | Why retrying won't help | What to ask the user |
| --- | --- | --- |
| 403 Forbidden | Permission issue — only the user can fix IAM | "Which GCP project should I use, and does your account have Discovery Engine Editor?" |
| Auth error / no credentials | Credentials must be created interactively | "Please run `gcloud auth application-default login`" |
| 400 Invalid Argument on `experiment create` | Usually wrong engine type or unsupported config | "Can you verify this engine supports AlphaEvolve experiments?" |

### Errors worth retrying (up to 3 times)

| Error | Retry strategy |
| --- | --- |
| 404 Not Found | Try different engine name, verify project |
| Network timeout | Wait 10s, retry |
| Evaluation ImportError | Install missing package, retry |
| Evaluation timeout | Increase `--timeout`, retry |

## General Debugging

### Getting verbose output

Add `--verbose` to any `ae` command for detailed logging:

```bash
ae --verbose experiment create --max-programs 100 --problem-file desc.md
```

### Checking CLI version

```bash
ae version
```

Ensure you're running the latest version. To update, follow the `ae` CLI
documentation for installation instructions.

### Inspecting cached data

The CLI caches experiment and program data in `~/.config/ae/cache/`. If data
seems stale, remove the cache directory. On Linux/macOS for example:

```bash
rm -rf ~/.config/ae/cache/
```
