# Debugging Guide for Experiment Monitoring

Troubleshooting guide for common issues when monitoring AlphaEvolve
experiments with the `ae` CLI.

## Experiment Not Found

### "experiment not found" or 404 error

**Cause:** The experiment nickname, ID, or resource name is incorrect, or
the experiment was deleted.

**Fix:**
1. List all experiments: `ae --json experiment list`
2. Find the correct nickname or ID
3. Verify the config points to the right project: `ae --json config show`
4. If the experiment is in a different project, use: `ae --project=<ID> experiment describe <exp>`

## Control Loop Issues

### Control loop exits immediately with no evaluations

**Cause:** The experiment may not have programs ready for evaluation yet.
The backend generates candidate programs asynchronously.

**Fix:**
1. Check experiment state: `ae --json experiment describe <exp>`
2. If `ACTIVE`, wait 1-2 minutes and try again -- the backend is generating programs
3. If `INITIALIZED`, the experiment has not been started. Use the Runner skill
4. If `COMPLETED`/`FAILED`, the experiment is done -- show the final report

### Control loop reports "No programs available" repeatedly

**Cause:** The backend is slower at generating programs than you are at
evaluating them. This is normal for high-concurrency experiments.

**Fix:** This is expected behavior. The loop will automatically retry
every 5 seconds. After 3 consecutive empty acquires, it checks for
terminal state. No action needed.

### Evaluation fails with "Program has no files"

**Cause:** A candidate program was generated without any source code
content. This is rare but can happen.

**Fix:** This is handled automatically -- the failed evaluation is submitted
with a failure score, and the loop continues. No action needed.

### Evaluator script not found

**Cause:** The path to the evaluator script is incorrect.

**Fix:**
1. Verify the evaluator file exists at the given path
2. Use an absolute path if relative paths are not resolving

### Evaluation times out

**Cause:** The evaluator or candidate program takes longer than the
configured timeout.

**Fix:**
1. Increase the timeout: `ae experiment run <exp> --evaluator <eval> --timeout 120`
2. Check if the program has infinite loops (review with `ae program show <prog> --code`)
3. Consider using `--backend podman` for resource isolation

### Evaluation fails with ImportError

**Cause:** The evaluator or program requires Python packages not available
in the local environment.

**Fix (Option A):** Install missing dependencies:
```bash
pip install <missing_package>
```

**Fix (Option B):** Use the podman backend:
```bash
ae experiment run <exp> --evaluator <eval> --backend podman
```

## Monitoring Issues

### Monitor shows stale best_score (always None)

**Cause:** The experiment API response may not include `bestScore` in
the top-level stats. The monitor falls back to querying programs.

**Fix:** If you are polling with `ae experiment describe`, also run
`ae --json results best <exp> --top 1` to get the actual best score.

### Monitor shows 0 evaluations but control loop is running

**Cause:** There may be a delay between submitting scores and the
experiment stats being updated on the backend.

**Fix:** Wait 1-2 poll cycles. The counts should update. If they stay at 0
after several minutes, check the control loop output for errors.

## Connectivity Issues

### 404 Not Found

**Cause:** The engine does not exist in the specified project/location.

**Fix:**
1. Verify config: `ae --json config show`
2. Check the engine exists: `ae --json engine list`
3. Update config: `ae config --engine=<correct_engine>`

### 403 Forbidden

**Cause:** The user lacks permissions on the project.

**Fix:**
1. Ensure the user has the `Discovery Engine Editor` IAM role
2. Check project access: `gcloud projects get-iam-policy <PROJECT_ID>`

### Authentication errors

**Cause:** Application Default Credentials (ADC) are not configured.

**Fix:**
```bash
gcloud auth application-default login
```

## Process Management

### How to check if the control loop is still running

Check whether the background process is still alive using your platform's
process inspection tools. On Linux/macOS for example:

```bash
ps -p <PID> > /dev/null 2>&1 && echo "running" || echo "stopped"
```

### How to stop the control loop

Press Ctrl+C if running in the foreground, or terminate the background process
using your platform's tools (e.g., `kill <PID>` on Linux/macOS).

### How to view control loop output

If you redirected output to a log file, view the last entries. On Linux/macOS
for example:

```bash
tail -50 /tmp/ae_control_loop_<EXPERIMENT>.log
```

## General Debugging

### Getting verbose output

Add `--verbose` to any `ae` command for detailed HTTP request/response logs:
```bash
ae --verbose --json experiment describe <exp>
```

### Clearing cached data

If data seems stale, remove the cache directory. On Linux/macOS for example:
```bash
rm -rf ~/.config/ae/cache/
```

The cache is located at `~/.config/ae/cache/` on all platforms.

### Checking CLI version

```bash
ae version
```

To update, follow the `ae` CLI documentation for installation instructions.
