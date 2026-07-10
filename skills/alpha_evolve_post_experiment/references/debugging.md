# Debugging Guide for Post-Experiment Processing

Troubleshooting guide for common issues when analyzing results and
integrating evolved code from AlphaEvolve experiments.

## Results Retrieval Issues

### "experiment not found" or 404 error

**Cause:** The experiment nickname, ID, or resource name is incorrect, or
the experiment was deleted.

**Fix:**
1. List all experiments: `ae --json experiment list`
2. Find the correct nickname or ID
3. Verify the config points to the right project: `ae --json config show`
4. If the experiment is in a different project, use:
   `ae --project=<ID> experiment describe <exp>`

### Results commands return empty arrays

**Cause:** The experiment completed without any successful evaluations, or
the experiment was just created and no programs have been evaluated yet.

**Fix:**
1. Check experiment state: `ae --json experiment describe <exp>`
2. If `ACTIVE` or `INITIALIZED`, the experiment is not done yet. Use the
   Monitor skill.
3. If `COMPLETED` or `FAILED`, check for failed results:
   `ae --json results failed <exp>`
4. The experiment may have had 100% failure rate. Examine failure insights
   to understand why.

### Program code is empty or truncated

**Cause:** The backend may not store the full source code for all programs,
or the code was too large for the JSON response.

**Fix:**
1. Try saving to a file instead:
   ```bash
   ae --json program show <prog> --experiment <exp> --code \
     --output-file evolved_code.py
   ```
2. If still empty, the program may have been generated but evaluation
   failed before code was stored. Check insights:
   `ae --json program show <prog> --experiment <exp> --insights`

### ae program diff fails with "Invalid program name"

**Cause:** The API returns parent references as short numeric indices
(e.g., `#1`, `#9`) instead of full resource names. The diff command cannot
resolve these.

**Fix:** Fall back to manual comparison:
1. Fetch the evolved code:
   `ae --json program show <prog> --experiment <exp> --code`
2. Read the initial program file using the agent's built-in file reading
   tool and compare against the fetched evolved code inline. Do NOT use
   `diff` — it is not cross-platform (e.g., on Windows PowerShell,
   `diff` is aliased to `Compare-Object`).

## Integration Issues

### Syntax error after integration

**Cause:** Indentation mismatch between the evolved code and the
integration target, or mismatched EVOLVE-BLOCK markers.

**Fix:**
1. Check if the evolved code used different indentation than the
   original file (e.g., 4 spaces vs 2 spaces, or top-level vs inside
   a class).
2. Adjust indentation to match the target context.
3. Verify EVOLVE-BLOCK markers are correctly matched.
4. Re-run syntax check:
   `python3 -c "import ast; ast.parse(open('file.py').read())"`

### Score mismatch after integration

**Cause:** The integrated code behaves differently in the original
codebase context than in the experiment sandbox.

**Diagnosis:**
1. Check for import differences: the evolved code may rely on packages
   available in the experiment's `pyproject.toml` but not in the
   original environment.
2. Check for missing helper functions: if the experiment had multiple
   files, some helpers may not have been copied over.
3. Check for environment differences: Python version, floating-point
   precision, random seeds.

**Fix:**
1. Add missing imports to the target file.
2. Copy any helper functions or files the evolved code depends on.
3. If the score difference is small (<5%) and the evaluator involves
   randomness, it may be within expected variance. Run the evaluator
   multiple times to confirm.

### Existing tests fail after integration

**Cause:** The evolved code has different behavior from the original for
edge cases or interfaces that the evaluator did not test.

**Fix:**
1. Read the test failure messages carefully.
2. If the failures are due to changed function signatures, update callers.
3. If the failures are due to changed output format, verify the new format
   is correct and update test expectations.
4. If the failures indicate a genuine regression, consider using a different
   program from the top-N list instead.

### Integration target not found

**Cause:** The original source file path is no longer valid (file was
moved, renamed, or deleted since the experiment was designed).

**Fix:**
1. Check the source map first:
   `cat <PROJECT_DIR>/.evolve/source_map.json`
   Look at `original_file` fields in the mappings.
2. Check the experiment description:
   `cat <PROJECT_DIR>/.evolve/experiment_description.json`
   Look for `source_file` or `source_files[].path`.
3. Parse `# ORIGIN:` comments in the initial program file to find
   original paths.
4. Ask the user for the current file path if none of the above work.

### EVOLVE-BLOCK markers not found in original file

**Cause:** The markers were added during experiment design (in the copied
experiment file) but do not exist in the original source file.

**Fix:** Use function replacement mode instead:
1. Check the source map for the `original_symbol` and `original_lines`
   fields -- they tell you exactly which function/class in the original
   file corresponds to the evolve block.
2. If no source map, check `# ORIGIN:` comments in the experiment file
   for the original function name and line range.
3. As last resort, compare the initial program file from the experiment
   directory against the original source file to identify the extracted
   region.

### Same function name in multiple original files

**Cause:** When using Extract and Isolate, functions with the same name
(e.g., `forward()`) may exist in multiple source files. Without
provenance, it is ambiguous which file to update.

**Fix:**
1. Check the source map -- each mapping entry has both `symbol` and
   `original_file`, uniquely identifying the target.
2. If no source map, check `# ORIGIN:` comments which include the full
   file path.
3. If neither exists, ask the user to specify which file should be
   updated.

## Connectivity Issues

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
