# Numerical Stability in Evaluators

AlphaEvolve evolves code that may produce numerically unstable results --
`NaN`, `Inf`, exploding gradients, and divergent training loops are common,
especially in neural network and optimization problems. This reference
covers patterns to prevent these issues from crashing the evaluator or
producing invalid scores.

> **Core rule:** The evaluator MUST never return `NaN` or `Inf` as a score.
> `NaN` is not valid JSON and will crash the `ae` CLI. Always check and
> convert to a `null` score with an error insight.

---

## When to read this reference

Read this when:

-   The problem involves **neural network training** (loss functions, gradient
    descent, backpropagation)
-   The problem involves **iterative numerical optimization** (Newton's method,
    gradient descent, eigenvalue computations)
-   The problem involves **floating-point arithmetic** where overflow/underflow
    is possible (e.g., exponentials, logarithms, softmax)
-   You observe `NaN` or `Inf` scores during baseline evaluation in Phase 2

---

## Pattern 1: Score Validation Guard

**Always apply this pattern.** It is the last line of defense.

```python
import math

def evaluate_program(code, timeout_seconds=30):
    ...
    raw_score = result.get(METRIC_NAME)

    # Guard against non-finite scores.
    if raw_score is None:
        return _failure("No score returned")
    if not isinstance(raw_score, (int, float)):
        return _failure(f"Score is not numeric: {type(raw_score)}")
    if math.isnan(raw_score) or math.isinf(raw_score):
        return _failure(
            f"Non-finite score: {raw_score}. "
            "This usually indicates numerical instability "
            "(exploding gradients, overflow, or division by zero)."
        )

    return {"score": float(raw_score), "insights": insights}
```

This prevents the evaluator from returning invalid JSON. The error insight
tells the LLM what went wrong so it can fix the candidate.

---

## Pattern 2: Gradient Clipping for Neural Networks

Evolved activation functions, loss functions, or weight initialization
schemes can cause gradient explosion. Clip gradients in the training loop:

```python
def update_weights(weights, gradients, learning_rate):
    """Update weights with gradient clipping."""
    max_grad_norm = 1.0
    grad_norm = np.sqrt(sum(np.sum(g**2) for g in gradients))
    if grad_norm > max_grad_norm:
        scale = max_grad_norm / grad_norm
        gradients = [g * scale for g in gradients]
    return [w - learning_rate * g for w, g in zip(weights, gradients)]
```

**Place gradient clipping OUTSIDE the evolve block** so it cannot be
removed by evolution. The evolved code should produce the gradients; the
fixed training loop should clip them.

---

## Pattern 3: Conservative Learning Rate

When evolving neural network components (activation functions, loss
functions, optimizers), use a smaller learning rate than you normally
would. Evolved code is untested and may produce much larger gradients
than expected.

```python
# Outside evolve block (fixed)
LEARNING_RATE = 1e-4   # Conservative default
MAX_EPOCHS = 10        # Enough to differentiate candidates, not enough to diverge
```

**Rules of thumb:**

-   Start with 10x smaller learning rate than what works for the
    baseline
-   Use fewer epochs than would be needed for convergence -- you are
    comparing candidates, not training to completion
-   If the baseline produces `NaN` with the chosen learning rate, halve
    it until stable

---

## Pattern 4: Safe Mathematical Operations

Evolved code may call mathematical functions with out-of-range inputs.
Use safe wrappers outside the evolve block:

```python
import numpy as np

# Outside evolve block (safe wrappers)
def safe_exp(x, max_val=500.0):
    """Exponential with overflow protection."""
    return np.exp(np.clip(x, -max_val, max_val))

def safe_log(x, eps=1e-8):
    """Logarithm with underflow protection."""
    return np.log(np.maximum(x, eps))

def safe_div(a, b, eps=1e-8):
    """Division with zero-division protection."""
    return a / (b + eps * np.sign(b + eps))

def safe_softmax(x, axis=-1):
    """Softmax with numerical stability."""
    x_shifted = x - np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x_shifted)
    return exp_x / np.sum(exp_x, axis=axis, keepdims=True)
```

Make these available to evolved code via the exec namespace, or define
them before the evolve block in the program file.

---

## Pattern 5: NaN Propagation Detection

Detect `NaN` early during training and abort with a meaningful score
instead of running all epochs and returning garbage:

```python
def train(model, data, epochs, lr):
    """Training loop with NaN detection."""
    for epoch in range(epochs):
        loss = train_one_epoch(model, data, lr)

        # Early abort on NaN -- no point continuing
        if math.isnan(loss) or math.isinf(loss):
            return {
                "score": None,
                "error": f"Training diverged at epoch {epoch}: loss={loss}",
                "last_valid_epoch": epoch - 1,
            }

    return {"score": -loss, "error": None}
```

This saves evaluation time (don't run 50 epochs when epoch 3 already
diverged) and provides the LLM with diagnostic information about when
divergence occurred.

---

## Pattern 6: Weight Initialization Bounds

Evolved weight initialization schemes may produce very large values. Clamp
initial weights:

```python
def init_weights(shape, init_fn):
    """Initialize weights with magnitude bounds."""
    w = init_fn(shape)
    max_magnitude = 2.0 / np.sqrt(shape[-1])  # Xavier-like bound
    return np.clip(w, -max_magnitude, max_magnitude)
```

---

## Pattern 7: Reduced Evaluation Budget

For neural network problems, reduce the training budget during
evaluation. You are comparing candidates, not training to convergence.

```python
# Outside evolve block (fixed evaluation parameters)
EVAL_CONFIG = {
    "epochs": 10,         # Not 100 -- just enough to differentiate
    "batch_size": 32,     # Standard
    "n_samples": 500,     # Subset, not full dataset
    "learning_rate": 1e-4,
}
```

**Why:** Fewer epochs means less time for gradients to explode, faster
evaluations, and better throughput. The best activation function at 10
epochs will generally be the best at 100 epochs too.

---

## Checklist for Neural Network Problems

When the problem involves neural network training, verify these during
Phase 2 implementation:

- [ ] Score validation guard in evaluator (Pattern 1)
- [ ] Gradient clipping in training loop, outside evolve block (Pattern 2)
- [ ] Conservative learning rate (Pattern 3)
- [ ] NaN detection during training with early abort (Pattern 5)
- [ ] Reduced evaluation budget (Pattern 7)
- [ ] Baseline evaluation produces a finite score
- [ ] Run baseline 3x to check for non-determinism (use fixed seeds)

---

## Checklist for General Optimization Problems

For problems involving iterative optimization (not neural networks):

- [ ] Score validation guard in evaluator (Pattern 1)
- [ ] Safe math wrappers available to evolved code (Pattern 4)
- [ ] Fixed random seeds for determinism
- [ ] Timeout guard (see `evaluator_patterns.md` Pattern 3)

---

## Common Failure Modes and Diagnosis

| Symptom | Likely Cause | Fix |
|---|---|---|
| Score is `NaN` | Division by zero, 0/0, or `log(0)` | Add safe wrappers (Pattern 4), score guard (Pattern 1) |
| Score is `-inf` or `inf` | Overflow in `exp()`, unbounded growth | Add `safe_exp()`, gradient clipping (Pattern 2) |
| Score oscillates wildly between runs | Non-deterministic evaluation | Fix random seeds (evaluator_patterns.md Pattern 8) |
| Score is `NaN` only on some candidates | Evolved code triggers edge case | NaN detection + early abort (Pattern 5) |
| Baseline works but evolved candidates diverge | Learning rate too high for evolved code | Conservative LR (Pattern 3), gradient clipping (Pattern 2) |
| All evolved candidates score `None` | Evolved code always crashes | Check if hard constraints are inside evolve block; move them out |
