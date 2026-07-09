# Multi-File Experiment Design

> Read this when the user points to a directory or multiple source files to
> optimize. For single-file experiments, the standard flow applies — skip this
> guide.

## When to Use Multi-File

Use multi-file when the optimization target spans multiple tightly coupled
files — e.g., a model definition in `model.py` that depends on custom layers
in `layers.py`, where both must be present for evaluation.

**Do NOT use multi-file just because the user has many files.** If only one
function in one file needs optimization, use the standard single-file flow
with the Extract and Isolate strategy (Step 5 below).

## Pipeline Support

Multi-file is fully supported across the stack:

| Layer | Status | How it works |
|-------|--------|--------------|
| API / Proto | Ready | `AlphaEvolveProgramContent.files` is `repeated AlphaEvolveSourceFile` |
| CLI `experiment start` | Ready | `--program-dir` bundles all .py files from a directory |
| Controller | Ready | Extracts all files from `content.files[]` |
| Evaluator | Ready | Writes all files to workspace, passes `--program-dir` to evaluator |
| Backend / LLM | Ready | Only modifies code inside `EVOLVE-BLOCK` markers |

## Token Budget

All files sent to the API contribute to the LLM's context window.

```
TOKEN_BUDGET  = 200,000 tokens
CHARS_PER_TOKEN ≈ 4   (standard approximation for code)
MAX_CHARS     = 800,000
```

Context quality degrades above ~250k tokens. The 200k budget provides a
safety margin. There are no per-file or file-count limits.

## Step 1: Inventory

Scan the source directory. For each file, compute its size (chars),
estimate token count (chars/4), and check whether it contains
EVOLVE-BLOCK markers. Present an inventory table to the user showing
all files in the directory with your proposed include/exclude decision.

Example format (adapt columns and values to the actual codebase):

```markdown
| File | Chars | Est. Tokens | Has EVOLVE-BLOCK? | Include? |
|------|-------|-------------|-------------------|----------|
| model.py | 12,000 | 3,000 | Yes | Yes |
| layers.py | 8,000 | 2,000 | No | Yes (context) |
| utils.py | 4,000 | 1,000 | No | Yes (context) |
| trainer.py | 20,000 | 5,000 | No | No |
| test_model.py | 15,000 | 3,750 | No | No |
| **Total included** | **24,000** | **6,000** | | |
```

The user confirms or adjusts the selection before proceeding.

## Step 2: Cherry-Pick Files

**You must explicitly select which files to include.** Never dump an entire
source tree into the experiment directory. The experiment directory should
contain ONLY the files the LLM needs to see and the evaluator needs to run.

### Decision: multi-file bundle vs. Extract and Isolate

Before cherry-picking files, assess the dependency depth:

1. **Read the target file.** Count its local imports (not stdlib/pip).
2. **For each local import**, check whether IT has further local imports.

Then decide:

| Situation | Strategy |
|-----------|----------|
| Target imports files that are each self-contained (no further local imports) | **Multi-file bundle** -- copy the files, rewrite imports to flat |
| A dependency file is large (>100 lines) and the target uses multiple symbols from it | **Multi-file bundle** -- bundling the whole file is simpler and preserves context for the LLM |
| Target has deep transitive imports (A -> B -> C -> D) or circular imports | **Extract and Isolate** (Step 5) -- inline needed symbols |
| A dependency file is large but only 1-2 small functions are needed from it | **Inline those functions** into initial_program.py, don't bundle the whole file |

**The default should be multi-file bundle.** When a target imports
multiple self-contained files, bundle them as separate files in the
experiment directory rather than inlining everything into
`initial_program.py`. Inlining 200+ lines of layer implementations,
loss functions, or activation libraries produces an unreadable monolith
that is harder for the LLM to evolve and impossible for the user to
reintegrate into the original codebase.

Use Extract and Isolate **only** when:

- The dependency graph is 3+ levels deep (transitive chains)
- There are circular imports that crash at runtime
- The total file count would exceed 10 files

### Multi-file: how to trace and rewrite

When the dependency graph IS shallow enough for multi-file:

1. **Read the target file.** Identify all local imports.
2. **For each local import**, read the imported file. If it has no further
   local imports (only stdlib/pip), it's safe to include.
3. **Stop at 1 level.** If an imported file itself imports other local
   files, do NOT recurse — either inline the needed symbols or switch to
   Extract and Isolate.
4. **Rewrite imports.** All files go into a flat directory, so:
   - `from myproject.src.models import layers`
     becomes `import layers`
   - `from src.core.activation import ReLU` becomes
     `from activation import ReLU`
   - Package-style paths are stripped to bare filenames.
5. **Verify** the rewritten imports by running `uv run pytest`.

### Extract and Isolate: inlining dependencies

When the dependency graph is too deep for multi-file, don't bundle files
at all. Instead, copy the specific functions/classes the target needs
directly into the target file:

```python
# BEFORE (original codebase):
from myproject.models.layers import Dense
from myproject.core.activation import ReLU
from myproject.utils.math_utils import clamp

# AFTER (in experiment's initial_program.py):

# --- Inlined from myproject/models/layers.py (lines 10-35) ---
class Dense:
    def __init__(self, input_size, output_size):
        ...
    def forward(self, x):
        ...
# --- End inlined from myproject/models/layers.py ---

# --- Inlined from myproject/utils/math_utils.py (lines 42-44) ---
def clamp(x, lo, hi):
    return np.clip(x, lo, hi)
# --- End inlined from myproject/utils/math_utils.py ---

# EVOLVE-BLOCK-START
def relu(x):
    return np.maximum(0, x)
# EVOLVE-BLOCK-END
```

**IMPORTANT: Provenance comments.** When inlining code, always add
comments marking where each block came from (file path and line numbers).
This lets the user trace evolved changes back to the original source
files for manual reintegration. Use the format:

```python
# --- Inlined from <original/path.py> (lines N-M) ---
...code...
# --- End inlined from <original/path.py> ---
```

This produces a single self-contained file with zero local imports. It
always works regardless of codebase complexity. The tradeoff is that the
user must manually port evolved changes back using the provenance
comments to find the original locations.

### Include (copy to experiment directory):

- **The optimization target** — the file with the function to evolve.
  This file gets EVOLVE-BLOCK markers.
- **Direct dependencies** — files imported by the target that are required
  for the evaluator to run AND have no further local imports themselves.

### Exclude (do NOT copy):

- Test files, build configs, documentation, scripts, `__init__.py`
- Files the target does NOT import
- Files imported by other parts of the codebase but not by the target
- Files with deep transitive imports (inline the needed symbols instead)
- Large files that provide only a single small utility — copy just that
  utility inline instead

### Worked example

Given a codebase:
```
src/core/activation.py          ← optimization target (evolve relu())
src/models/layers.py             ← imported by activation.py, no further
                                    local imports → safe to bundle
src/models/architectures/resnet_model.py  ← imports activation.py AND
                                            layers.py → deep, skip
src/training/trainer.py          ← not imported by activation.py → skip
src/data/generator.py            ← not imported by activation.py → skip
src/evaluation_framework/evaluator.py  ← codebase evaluator, NOT ours
```

**Selected files for experiment directory:**
```
activation.py   ← evolve target (with EVOLVE-BLOCK)
layers.py       ← context (activation.py imports it)
evaluator.py    ← OUR evaluator (generated by Phase 2, not the codebase one)
```

Everything else is excluded — the LLM doesn't need to see the trainer,
data generator, or resnet model to evolve the activation function.

**Rule: EVOLVE-BLOCK markers determine mutability.** The AlphaEvolve
backend only modifies code inside EVOLVE-BLOCK markers. Files without
markers are preserved unchanged across evolution generations. There is
no need for explicit "read-only" flags — the absence of markers IS the
read-only mechanism.

## Step 3: Budget Check

Sum estimated tokens across all included files.

- **Under 200k tokens:** Proceed.
- **Over 200k tokens:** Apply the Extract and Isolate strategy (Step 5).

Do NOT attempt complex automated distillation (extracting symbols,
collapsing to signatures). These techniques are error-prone. If the
codebase doesn't fit, fall back to extraction.

## Step 4: File Naming and Import Constraints

When multiple files are bundled, the evaluator writes all of them to a
flat workspace directory and `exec()`s `initial_program.py`. The other
program files are context that `initial_program.py` imports from.

### The `initial_program.py` convention

The main program file **must always be named `initial_program.py`**. It:

- Imports from the other cherry-picked context files
- Contains (or imports) the EVOLVE-BLOCK code
- Contains the `evaluate()` function
- Is the ONLY file the evaluator exec's

The evaluator receives `--program-dir` pointing to the workspace directory
and finds `initial_program.py` there. No scanning, no heuristics -- the
evaluator always reads `os.path.join(args.program_dir, "initial_program.py")`.

### Import rules

1. **Imports must be one-directional.** Context files can be imported BY
   `initial_program.py` (e.g., `from layers import Dense`). But context
   files must NOT import back from `initial_program.py`. It is exec'd,
   not imported as a module -- reverse imports will fail.

2. **All files are placed flat in one directory.** Use simple `import
   <filename>` (without the `.py` extension). Do NOT use package-style
   imports like `from mypackage.models import layers`.

3. **No subdirectory structure.** If the original codebase has
   subdirectories, flatten the files when extracting them. Rename if
   there are name collisions (e.g., `models_layers.py` instead of
   `models/layers.py`).

4. **Avoid stdlib name collisions.** Do NOT name a context file
   `types.py`, `collections.py`, `io.py`, etc. Rename to
   `types_lib.py`, `collections_lib.py`, etc.

## Step 5: Extract and Isolate (Fallback)

When the codebase is too large (over the token budget), or when only a
small part needs optimization, fall back to extracting the target into a
self-contained file.

**The Condensation Principle:** Create a single file (or tiny bundle well
under the budget) containing the absolute minimum required for the
evaluator to run and test the target logic.

### 5.1: Identify the Hot Path

Isolate the exact functions or classes that need optimization. Ignore
surrounding boilerplate and infrastructure.

### 5.2: Copy Dependencies Inline

Instead of importing from local modules, copy only the necessary helpers
directly into the extracted file. This is more reliable than maintaining
separate context files for large codebases.

### 5.3: Mock Non-Essential Externals

Mock interactions that are NOT essential for the optimization target
(logging, metrics, RPCs). **If an interaction IS essential** (e.g.,
optimizing a query planner that needs a database), do not mock it
silently — ask the user for guidance and propose options:

1. Provision a dedicated sandbox service
2. Use a lightweight in-memory fallback
3. Skip evolution on this layer and optimize a different component

### 5.4: Provenance for Reintegration

When extracting and inlining code, **always add `ORIGIN` comments** to
record where each function or class was copied from. This enables the
post-experiment skill to automatically apply evolved code back to the
correct source files.

```python
# ORIGIN: src/models/layers.py::Dense (lines 5-42)
class Dense:
    def __init__(self, input_size, output_size):
        ...

# ORIGIN: src/utils/math_utils.py::clamp (lines 8-10)
def clamp(x, lo, hi):
    return np.clip(x, lo, hi)

# ORIGIN: src/core/activation.py::relu (lines 12-18)
# EVOLVE-BLOCK-START
def relu(x):
    return np.maximum(0, x)
# EVOLVE-BLOCK-END
```

Also generate `.evolve/source_map.json` with a mapping entry for each
extracted symbol. See `references/phase_2_implement.md` (Provenance
Tracking section) for the full `source_map.json` schema.

Without provenance tracking, the user must manually port changes back.
With it, the post-experiment skill can automatically identify which
original files to update and where to apply the evolved code.

## Phase 1 Impact

When multi-file is detected, Phase 1 must additionally:

- Populate `source_files` in the `ExperimentDescription` (list of source
  file specs with path and content)
- Present the inventory table and get user confirmation on file selection
- Run the budget check
- If over budget, discuss extraction strategy with the user

## Phase 2 Impact

When `source_files` is populated in the `ExperimentDescription`:

- **Create `initial_program.py`** as the main entry point. It imports
  from the cherry-picked context files and contains the `evaluate()`
  function. The evaluator always exec's this file.
- **Copy only the cherry-picked context files** into the experiment
  directory alongside `initial_program.py`. The experiment directory
  must contain ONLY these files, the evaluator, tests, and config.
  Do NOT copy the user's entire source tree.
- Files with EVOLVE-BLOCK markers are optimization targets (may be
  in `initial_program.py` itself or in a context file it imports)
- Files without markers are context (preserved unchanged by the backend)
- `pyproject.toml` does NOT need `[build-system]` -- flat imports work
- Tests must validate all generated files together (copy all program
  files to the test tmpdir)
- **Rewrite imports**: if the original codebase uses package-style imports
  (e.g., `from src.models.layers import Dense`), rewrite them to flat
  imports (`from layers import Dense`) since all files are placed in the
  same directory.

## CLI Usage

```bash
# Bundle all program files from the experiment directory
ae experiment start <nickname> \
  --program-dir ./exp_dir/ \
  --score <baseline_score>
```

The `--program-dir` flag bundles all `.py` files from the directory
(excluding `evaluator.py` and test files). This is why the experiment
directory must contain only the cherry-picked files — anything in the
directory gets sent to the API.
