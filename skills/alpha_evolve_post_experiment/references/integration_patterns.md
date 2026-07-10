# Code Integration Patterns

Reference guide for applying evolved code back to the user's original
codebase. Covers provenance-driven integration, scaffolding stripping,
common scenarios, edge cases, and validation strategies.

--------------------------------------------------------------------------------

## Provenance System

The experiment design skill produces two provenance artifacts that guide
integration:

### 1. ORIGIN Comments (inline)

`# ORIGIN: <path>::<symbol> (lines <start>-<end>)` comments in program
files record where each code region was extracted from. They are placed
outside EVOLVE-BLOCK markers so they survive evolution unchanged.

```python
# ORIGIN: src/core/activation.py::relu (lines 12-18)
# EVOLVE-BLOCK-START
def relu(x):
    return np.maximum(0, x)
# EVOLVE-BLOCK-END
```

### 2. Source Map (`.evolve/source_map.json`)

A structured JSON file mapping each code region to its original location.
Contains `mappings[]` with entries specifying `experiment_file`, `symbol`,
`is_evolve_block`, `original_file`, `original_lines`, `original_symbol`,
and `integration_mode`.

**Priority:** Use `source_map.json` when available. Fall back to parsing
`ORIGIN` comments if the source map is missing. Fall back to
`experiment_description.json` fields (`source_file`, `source_files`) as
last resort.

### 3. Scaffolding Cleanup

> **CRITICAL:** Experiment scaffolding must NEVER leak into the user's
> codebase. After integration, the resulting code should look like it was
> written by a human -- no experiment artifacts should remain.

#### What to strip

The following lines are **experiment scaffolding** and must be removed
when writing evolved code back to the user's source files:

| Line pattern | Purpose | Strip on integration? |
|-------------|---------|----------------------|
| `# EVOLVE-BLOCK-START` | Marks start of mutable region | **Always strip** |
| `# EVOLVE-BLOCK-END` | Marks end of mutable region | **Always strip** |
| `# ORIGIN: ...` | Records provenance for integration | **Always strip** |
| `evaluate()` function | Experiment scoring harness | Strip unless it existed in the original file |
| `if __name__ == "__main__":` block | Experiment entry point | Strip unless it existed in the original file |
| Experiment-only imports | e.g., `import time` added for benchmarking | Strip if not used by the evolved code itself |

#### How to strip

Process the evolved code **line by line** before writing to the target
file. Apply these rules in order:

1. **Remove marker lines entirely.** Delete any line whose stripped
   content is exactly `# EVOLVE-BLOCK-START` or `# EVOLVE-BLOCK-END`.
   Do not leave blank lines in their place -- collapse them.

2. **Remove ORIGIN comment lines entirely.** Delete any line that starts
   with `# ORIGIN:` (after stripping leading whitespace). These are
   always standalone comment lines (never sharing a line with code).

3. **Remove the `evaluate()` function** if it was added by the experiment
   design skill. Check against the original file: if the original had
   no `evaluate()` function, remove it and any associated imports. If
   the original DID have an `evaluate()` function, preserve it.

4. **Remove the `if __name__ == "__main__":` block** if it was added
   for experiment standalone execution. Same rule: check against the
   original.

5. **Remove experiment-only imports.** Compare the import list in the
   evolved code against (a) the original file's imports and (b) what
   the evolved code actually uses. Remove imports that were added only
   for the experiment harness (e.g., `from typing import Any, Mapping`
   if the original file did not use them and the evolved code does not
   reference them).

6. **Clean up blank lines.** After removing lines, collapse any runs of
   3+ consecutive blank lines down to 2 (standard Python style).

#### Indentation adjustment

When the evolved code was extracted from a class method but the
experiment ran it as a standalone function (common with Extract and
Isolate), the indentation levels differ:

```python
# Experiment file (top-level function, no indentation):
def relu(x):
    return np.maximum(0, x)

# Original file (class method, indented):
class Activations:
    def relu(self, x):
        return np.maximum(0, x)
```

When integrating back, adjust the indentation of the evolved code to
match the original context. If the original function was inside a class
(indented 4 or 8 spaces), re-indent the evolved code to match.

#### Verification

After stripping, verify that no scaffolding remains:

1. Search the written file for `EVOLVE-BLOCK` -- should find zero matches.
2. Search the written file for `# ORIGIN:` -- should find zero matches.
3. Syntax-check the result:
   `python3 -c "import ast; ast.parse(open('<file>').read())"`

If any scaffolding is found or syntax check fails, the stripping was
incomplete. Fix and re-verify.

--------------------------------------------------------------------------------

## Integration Modes

### Mode 1: EVOLVE-BLOCK Replacement (`evolve_block_replacement`)

**When:** The original source file contains `# EVOLVE-BLOCK-START` and
`# EVOLVE-BLOCK-END` markers (placed during experiment design).

**How:**

1. Read the original source file.
2. Find the markers.
3. Replace everything between them with the evolved code.
4. **Strip the markers themselves.** The `EVOLVE-BLOCK-START` and
   `EVOLVE-BLOCK-END` comment lines should be removed from the final
   file. They are experiment scaffolding.

```python
# Original file (with markers added during experiment design)
def solve(data):
    # EVOLVE-BLOCK-START
    # simple brute-force approach
    result = brute_force(data)
    return result
    # EVOLVE-BLOCK-END

# After integration (markers stripped)
def solve(data):
    # evolved tournament-based approach
    result = tournament_merge(data)
    return result
```

**Edge cases:**

- **Multiple EVOLVE-BLOCKs:** If the program has multiple evolve blocks,
  match each one by position (first block in evolved = first block in
  original). Use `ORIGIN` comments to verify each block maps to the
  correct location. The number of blocks must match.
- **Markers not in original:** If the markers were added only for the
  experiment directory copy, identify the function/class boundary that
  corresponds to the evolved block (using `ORIGIN` comments or the source
  map) and replace that region instead. Use function replacement mode.
- **Indentation mismatch:** The evolved code uses the indentation level
  from the experiment file. If the original file has different indentation
  (e.g., the function is inside a class), adjust the indentation to match.

### Mode 2: Function Replacement (`function_replacement`)

**When:** A specific function was extracted for optimization, and the
original file does not have EVOLVE-BLOCK markers. This is the most common
mode for Extract and Isolate experiments.

**How:**

1. Read the original source file.
2. Locate the target function by name. Use `original_symbol` from the
   source map (the function may have been renamed for flat imports in
   the experiment directory).
3. Replace the entire function body with the evolved version.
4. **Strip scaffolding:** Remove any `EVOLVE-BLOCK` markers and `ORIGIN`
   comments from the evolved code before inserting.
5. Preserve: decorators, function signature, and docstring (unless the
   evolved code intentionally modified the signature).

```python
# Original file (src/core/activation.py)
class Activations:
    def relu(self, x):
        """Rectified Linear Unit."""
        # Original implementation
        return np.maximum(0, x)

# Experiment file had:
# ORIGIN: src/core/activation.py::relu (lines 3-6)
# EVOLVE-BLOCK-START
# def relu(x):  <-- note: extracted without self, flat imports
#     return np.where(x > 0, x, 0.01 * x)  # evolved to leaky ReLU
# EVOLVE-BLOCK-END

# After integration (markers stripped, signature preserved)
class Activations:
    def relu(self, x):
        """Rectified Linear Unit."""
        # Evolved to leaky ReLU
        return np.where(x > 0, x, 0.01 * x)
```

**Edge cases:**

- **Symbol name mismatch:** The experiment may have renamed a method
  (e.g., `self.relu(x)` -> `relu(x)` for standalone execution). The
  source map's `original_symbol` field tracks the original name. Always
  use the original name in the integrated file.
- **Nested functions:** If the evolved code introduces helper functions
  that were not in the original, add them immediately before the target
  function.
- **New imports:** If the evolved code uses imports not present in the
  original file, add them at the top of the file following the existing
  import style (stdlib first, then third-party, then local).
- **Changed signature:** If the evolved code changes the function
  signature (e.g., adds parameters), warn the user that callers may need
  updating.
- **Same function name in multiple files:** When the same function name
  exists in multiple source files (e.g., `forward()` in both `model.py`
  and `layers.py`), use `ORIGIN` comments or source map `original_file`
  to determine which file each evolved region maps to. Never guess.

### Mode 3: Full File Replacement (`full_file_replacement`)

**When:** The entire file was the experiment target (common for standalone
scripts or utility modules, or multi-file bundle mode).

**How:**

1. Create a backup: `cp original.py original.py.bak`
2. Write the evolved program as the new file content.
3. **Strip all scaffolding** from the written file: remove `ORIGIN`
   comments, `EVOLVE-BLOCK` markers, experiment-only `evaluate()`
   function, and `if __name__ == "__main__"` blocks added for the
   experiment.
4. Validate with syntax check and evaluator.

**Edge cases:**

- **Imports added by experiment scaffolding:** The experiment copy may
  have added imports (e.g., `import time` for benchmarking) that are not
  needed in the original context. Review and remove scaffolding-only
  imports.
- **Flat import rewriting:** If multi-file bundle mode rewrote imports
  from package-style (`from myproject.models import layers`) to flat
  (`import layers`), revert them to the original package-style imports
  during integration.

### Mode 4: Manual / New File

**When:** The experiment was standalone (no original source file), or the
user wants to save the result without modifying existing files.

**How:**

1. Save the evolved code to `<PROJECT_DIR>/evolved_program.py`.
2. Inform the user of the file path.
3. Optionally save just the evolved block (without boilerplate) to a
   separate file.

--------------------------------------------------------------------------------

## Multi-File Integration

When the experiment used multiple files, integration may need to update
several original source files. The source map is especially important
here because the experiment's flat directory structure maps to a
potentially deep original directory structure.

### Source-map-driven multi-file integration

1. **Read the source map.** Group mappings by `original_file`. Each
   unique original file is an integration target.
2. **Filter to evolved regions.** Only entries with
   `is_evolve_block: true` need integration. Entries with
   `integration_mode: "skip"` are context files that were not evolved.
3. **Check for changes.** For each experiment file, compare the evolved
   version against the initial version. If a file has no EVOLVE-BLOCKs,
   it should be identical -- skip it.
4. **Apply per original file.** For each original file, collect all
   evolved regions that map to it and apply them. If multiple functions
   in the same original file were evolved, apply all changes to that file
   in a single pass (top-to-bottom by line number to avoid offset drift).
5. **Revert flat imports.** If the experiment used flat imports
   (`import layers`) but the original codebase uses package imports
   (`from myproject.models import layers`), revert the import style.

### Extract-and-Isolate multi-file integration

When functions from multiple source files were inlined into a single
`initial_program.py`:

1. **Parse ORIGIN comments.** Each `# ORIGIN:` comment identifies which
   original file and function the following code region came from.
2. **Match evolved blocks to origins.** Each EVOLVE-BLOCK should have
   an `ORIGIN` comment immediately preceding it. This tells you which
   original file to update.
3. **Apply independently.** Open each original file, locate the target
   function, replace it with the evolved version (stripping scaffolding),
   and write. Different EVOLVE-BLOCKs from the same experiment file may
   map to different original files.

### Fallback (no provenance)

If neither source map nor ORIGIN comments exist:

1. **Identify changed files:** Compare each file in the evolved program
   against its initial version. Only integrate files that actually changed.
2. **Maintain import consistency:** If file A imports from file B, and
   both changed, integrate both. If only A changed, ensure its imports
   still resolve against the original B.
3. **Order of integration:** Integrate leaf dependencies first (files
   that don't import from other experiment files), then work up to files
   that depend on them.

--------------------------------------------------------------------------------

## Validation Strategy

### Step 1: Syntax Check

Always verify syntax immediately after writing:

```bash
python3 -c "import ast; ast.parse(open('target_file.py').read())"
```

This catches indentation errors, unmatched brackets, and syntax issues
introduced during integration.

### Step 2: Evaluator Re-run

Use the experiment's evaluator to verify the score is preserved:

```bash
ae --json program evaluate \
  --program-file <TARGET_FILE> \
  --evaluator <PROJECT_DIR>/evaluator.py \
  --backend local
```

**Score tolerance:** Scores should match within 1% for deterministic
evaluators. For stochastic evaluators (e.g., Monte Carlo simulations),
run 3-5 evaluations and compare the mean.

### Step 3: Existing Tests

If the original source file has tests, run them:

```bash
python3 -m pytest <test_file> -v
```

Common test failure patterns after integration:

| Failure | Cause | Fix |
|---------|-------|-----|
| `ImportError` | Evolved code uses new deps | Add missing imports |
| `AttributeError` | Changed function signature | Update callers |
| `AssertionError` | Different output format | Update test expectations if valid |
| `TypeError` | New parameters required | Add default values |

### Step 4: Manual Review

Always recommend the user review the integrated code, even when automated
checks pass. Automated validation can miss:

- Subtle behavioral changes that do not affect the score metric but change
  other behaviors
- Performance regressions in non-measured dimensions
- Code readability degradation
- Security implications of evolved code patterns

--------------------------------------------------------------------------------

## Rollback

If integration fails validation or the user wants to revert:

**If backup was created (Mode 3):**

```bash
cp original.py.bak original.py
```

**If EVOLVE-BLOCK or function replacement was used (Modes 1-2):**

The original file content should have been read before modification. Use
the agent's editing capabilities to restore the original content.

**General principle:** Never delete the experiment directory or its
artifacts after integration. The user may want to refer back to the
experiment results, try a different program from the top-N, or revert.
