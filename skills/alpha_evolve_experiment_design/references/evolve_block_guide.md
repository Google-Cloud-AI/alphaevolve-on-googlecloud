# EVOLVE-BLOCK Guide

Rules for writing `EVOLVE-BLOCK` markers in AlphaEvolve initial programs.

## Syntax

```python
# EVOLVE-BLOCK-START
# Code that AlphaEvolve will evolve goes here.
# EVOLVE-BLOCK-END
```

## Rules

### 1. Each marker on its own line

Each marker must be the **only content** on its line. No other code, no
inline comments sharing the line.

```python
# ✅ Correct
# EVOLVE-BLOCK-START
def solve(n):
    return n * 2
# EVOLVE-BLOCK-END

# ❌ Wrong: marker shares line with code
def solve(n):  # EVOLVE-BLOCK-START
    return n * 2
# EVOLVE-BLOCK-END
```

### 2. Never put both markers on the same line

Never reference both marker strings on the same line, even in comments
or docstrings. The parser does line-by-line substring matching and will
crash.

```python
# ❌ Wrong: both marker strings on one line (even in a comment)
# The code between EVOLVE-BLOCK-START and EVOLVE-BLOCK-END is evolved.

# ✅ Correct: describe without using the literal marker strings
# The code between the start and end markers is evolved by AlphaEvolve.
```

### 3. No nesting

Evolve blocks cannot be nested. Each `START` must have exactly one
matching `END` before the next `START`.

```python
# ❌ Wrong: nested blocks
# EVOLVE-BLOCK-START
def outer():
    # EVOLVE-BLOCK-START
    def inner():
        pass
    # EVOLVE-BLOCK-END
# EVOLVE-BLOCK-END

# ✅ Correct: sequential blocks
# EVOLVE-BLOCK-START
def function_a():
    pass
# EVOLVE-BLOCK-END

# EVOLVE-BLOCK-START
def function_b():
    pass
# EVOLVE-BLOCK-END
```

### 4. Balanced pairs

Every `START` must have a matching `END`. Unmatched markers cause parser
errors.

### 5. Preserve function names and signatures

Functions defined inside the EVOLVE-BLOCK are called from outside the
block (typically by `evaluate()`). **The function name and parameter
signature must stay the same.** The LLM should only change the function
body (implementation), not its name.

If a function is named `relu(x)` inside the block, the code outside calls
`relu(x)`. If the LLM renames it to `swish(x)`, the call site breaks with
`NameError: name 'relu' is not defined`.

To prevent this, add a comment inside the EVOLVE-BLOCK:

```python
# EVOLVE-BLOCK-START
# IMPORTANT: Keep the function name as 'solve'. Change only the body.
def solve(n):
    return n * 2
# EVOLVE-BLOCK-END
```

Also add a constraint to `problem_description.md`:

> **Do not rename functions.** The function names inside the evolve block
> are called from fixed code outside the block. Changing function names
> will cause a NameError and a failed evaluation.

### 6. Multiple blocks are allowed

Use multiple blocks when different parts of the code should evolve
independently:

```python
import numpy as np

# EVOLVE-BLOCK-START
def compute_layout(n):
    """Compute positions (this function is evolved)."""
    return np.random.rand(n, 2)
# EVOLVE-BLOCK-END

def validate(positions):
    """Validation is NOT evolved (fixed contract)."""
    return np.all(positions >= 0) and np.all(positions <= 1)

# EVOLVE-BLOCK-START
def compute_radii(positions):
    """Compute radii (this function is also evolved)."""
    n = len(positions)
    return np.ones(n) * 0.01
# EVOLVE-BLOCK-END
```

### 7. ORIGIN comments for provenance

When code inside an EVOLVE-BLOCK is extracted from an existing source file,
place an `# ORIGIN:` comment **immediately before** the `EVOLVE-BLOCK-START`
marker to record where the code came from. This enables automatic
integration of evolved code back to the original file.

```python
# ORIGIN: src/core/activation.py::relu (lines 12-18)
# EVOLVE-BLOCK-START
def relu(x):
    return np.maximum(0, x)
# EVOLVE-BLOCK-END
```

The `ORIGIN` comment is OUTSIDE the evolve block, so it is preserved
unchanged through all evolution generations. See
`references/phase_2_implement.md` (Provenance Tracking section) for the
full format specification.

### 8. Marker stripping during integration

EVOLVE-BLOCK markers are experiment scaffolding -- they do not belong in
the user's original source files. The post-experiment skill strips all
`# EVOLVE-BLOCK-START`, `# EVOLVE-BLOCK-END`, and `# ORIGIN:` comments
when integrating evolved code back into the original codebase. Design the
program so that removing these comments does not affect the code's behavior
(they must always be standalone comment lines, never sharing a line with
code).

---

## What goes inside vs. outside

| Inside EVOLVE-BLOCK | Outside EVOLVE-BLOCK |
|---|---|
| The core algorithm / solve function | `evaluate()` function |
| Problem-specific imports used by evolved code | Validation / constraint checking |
| Helper functions the LLM can modify | Fixed boilerplate (I/O, scoring) |
| Constants the LLM might tune | Hard constraints (type checks, bounds) |

### Design principle

Place **hard constraints outside** the evolve block to enforce them
structurally. Place **soft constraints** (things the LLM should optimize)
inside the evolve block and score them in `evaluate()`.

```python
# Outside: hard constraint (must use only these imports)
import numpy as np
from typing import Any, Mapping

# EVOLVE-BLOCK-START
# Inside: the LLM can change the algorithm freely
def solve(n: int) -> tuple[np.ndarray, np.ndarray]:
    centers = np.random.rand(n, 2)
    radii = np.ones(n) * 0.01
    return centers, radii
# EVOLVE-BLOCK-END

# Outside: fixed evaluation contract
def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
    centers, radii = solve(eval_inputs["n"])
    if not _is_valid(centers, radii):
        return {"score": -1e12}
    return {"score": float(np.sum(radii))}
```
