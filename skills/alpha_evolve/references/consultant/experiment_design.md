# Experiment Design (Sections 3-4)

## 3. Initial Program Design

The initial program (seed) is the most critical input. It defines the search space, constrains the solution structure, and provides the starting point for evolution.

### 3.1 Code Clarity

**"Spaghetti code == Noisy search space."**

Treat AlphaEvolve with the same respect you would afford a human developer. The LLM reads your code to understand what to modify and how. Unclear, poorly organized code produces lower-quality mutations.

Before tagging code with EVOLVE-BLOCKs:

- Clean up variable names and function signatures
- Add concise docstrings explaining what each function does and why
- Remove dead code and unnecessary boilerplate
- Organize code so the optimization target is clearly separated from infrastructure

### 3.2 Minimize Immutable Boilerplate

The LLM sees the entire program -- both mutable (EVOLVE-BLOCK) and immutable regions. Large blocks of boilerplate outside EVOLVE-BLOCKs consume context window without providing useful signal.

**The total program content sent to the API should stay under 150-200k tokens.** Beyond this, the LLM's context window becomes polluted and mutation quality degrades. For ideal performance, the initial program should be distilled to contain only code that is relevant to the optimization or could help guide it.

**What to keep in the program** (sent to the API, visible to the LLM):
- The EVOLVE-BLOCK code (the optimization target)
- Functions and types directly used by the EVOLVE-BLOCK
- Constants, configurations, and constraints the LLM needs to reason about
- Clean inline documentation explaining the problem

**What to move to the evaluator** (client-side, invisible to the LLM):
- Static utility modules and infrastructure code
- Data loading and preprocessing pipelines
- Test harnesses and validation logic
- Large dependency libraries

The evaluator runs on your infrastructure and can import anything. It only needs to call the evolved `evaluate()` function and return scores. All the heavy lifting (data loading, model training infrastructure, test execution) should live in the evaluator, not in the program sent to AlphaEvolve.

Example: if your codebase has 3,759 lines of infrastructure and 20 lines of critical algorithmic code, the program sent to the API should contain the 20 lines of algorithm + enough context for the LLM to understand what it's optimizing. The 3,739 lines of infrastructure stay on the client side in the evaluator.

### 3.3 Do Not Hardcode Data

Do not embed large datasets or sample data directly in the initial program. This:

- Bloats the program, reducing LLM attention on the algorithm
- Makes data management harder across experiment iterations
- Prevents proper data versioning

Instead, have your evaluator (client-side) load data from external sources (files, databases, APIs, or generated synthetically with a fixed seed). The data never needs to be sent to the AlphaEvolve API.

### 3.4 Prime the Initial Program First

Before launching AlphaEvolve, use a standard coding agent to analyze and debug BOTH the initial program AND the evaluator. This is critical for a successful experiment.

**Prime the initial program:**
- Fix wrong loss functions or metrics
- Fix basic algorithmic bugs
- Improve suboptimal default hyperparameters
- Handle edge cases

**Test the evaluator thoroughly:**
- Run the evaluator locally with the initial program and verify the baseline score is reasonable
- Test with intentionally bad programs to verify the evaluator returns None (not a misleading score)
- Test with edge cases (empty functions, NaN outputs, infinite loops) to verify timeout and error handling work
- Verify the score is deterministic (same input = same score)

A broken evaluator is the #1 cause of failed experiments. If the evaluator has bugs, AlphaEvolve will optimize for the bugs, not for the actual objective.

Get the best possible starting point with a working, tested evaluator, THEN let AE search for improvements beyond what direct reasoning can achieve.

### 3.5 The Initial Solution Can Be Rudimentary

The initial implementation inside EVOLVE-BLOCKs must be complete (it must run and return valid results), but it can be simple -- even single-line functions returning constants of the appropriate types. AlphaEvolve will evolve from whatever starting point you provide.

However, a better starting point generally leads to faster convergence. The LLM uses the initial code as a template for understanding the expected structure of solutions.

---

## 4. EVOLVE-BLOCK Placement Strategy

The placement of EVOLVE-BLOCK markers defines the search space. This is the single most impactful design decision.

### 4.1 Providing Degrees of Freedom

The mutable region must provide enough degrees of freedom for meaningful improvement. An EVOLVE-BLOCK containing only `x = 0.5` makes AE a glorified grid search.

Good EVOLVE-BLOCKs contain entire function bodies, algorithm implementations, or multi-step computation pipelines where the LLM can propose structurally different approaches.

### 4.2 Constraining the Search Space

Place hard constraints as immutable code OUTSIDE the EVOLVE-BLOCK.

**Constrained (good):** Force sklearn-only models by importing outside:

```python
import sklearn as sk  # IMMUTABLE: must use sklearn

def model_tuning():
    # EVOLVE-BLOCK-START
    from sklearn import ensemble
    model = ensemble.GradientBoostingClassifier(n_estimators=100)
    # EVOLVE-BLOCK-END
```

**Unconstrained (broader search):** Allow any ML library by importing inside the EVOLVE-BLOCK:

```python
def model_tuning():
    # EVOLVE-BLOCK-START
    import xgboost as xgb  # AE free to replace with tf, sklearn, etc.
    model = xgb.XGBClassifier()
    # EVOLVE-BLOCK-END
```

**Over-constrained (bad):** Forcing a specific model class reduces AE to parameter tuning:

```python
from sklearn import linear_model as glm  # IMMUTABLE

def model_tuning():
    # EVOLVE-BLOCK-START
    model = glm.Lasso(alpha=0.01)  # AE can only tune alpha
    # EVOLVE-BLOCK-END
```

**Caution:** AlphaEvolve has no way of knowing which library imports are valid in your evaluation environment. If AE puts `import tensorflow` inside an EVOLVE-BLOCK but your evaluation environment doesn't have TensorFlow, the program will fail. Your validation tests must catch invalid imports.

### 4.3 Keep EVOLVE-BLOCK Inside Function/Class Definitions

Place markers inside the function body, not above the function definition. This prevents AE from replacing one function with multiple functions or changing the function signature.

```python
# GOOD: evolves the body, preserves the interface
def custom_filter(signal):
    # EVOLVE-BLOCK-START
    filtered = apply_bandpass(signal, low=100, high=1000)
    return filtered
    # EVOLVE-BLOCK-END

# BAD: AE might replace the entire function, change its name/args
# EVOLVE-BLOCK-START
def custom_filter(signal):
    filtered = apply_bandpass(signal, low=100, high=1000)
    return filtered
# EVOLVE-BLOCK-END
```

This is especially important for Verilog and other HDL languages -- keeping EVOLVE-BLOCK-START inside a module definition prevents AE from trying to replace one module with multiple modules.

### 4.4 Multiple EVOLVE-BLOCKs

A program can contain multiple EVOLVE-BLOCKs for optimizing interacting components. AlphaEvolve can modify each block independently or jointly. The LLM sees all blocks and their scores, allowing it to reason about interactions.

```python
def model_architecture():
    # EVOLVE-BLOCK-START
    layers = [Dense(128), ReLU(), Dense(64)]
    # EVOLVE-BLOCK-END
    return Sequential(layers)

def loss_function():
    # EVOLVE-BLOCK-START
    loss = keras.losses.SparseCategoricalCrossentropy()
    # EVOLVE-BLOCK-END
    return loss
```

### 4.5 Encoding Hard vs. Soft Constraints

**Hard constraints** (must be satisfied): Encode as immutable code outside EVOLVE-BLOCKs or as validation checks that return None score on violation.

```python
# Hard constraint: output must be a valid probability distribution
def postprocess(raw_output):
    return softmax(raw_output)  # IMMUTABLE
```

**Soft constraints** (desirable but negotiable): Encode as penalties in the evaluation score. This gives AE gradient signal about how close a solution is to satisfying the constraint, rather than a binary pass/fail.

```python
# Soft constraint: prefer solutions with latency < 100ms
penalty = max(0, latency_ms - 100) * 0.1
score = accuracy - penalty
```

### 4.6 EVOLVE-BLOCK Placement for Different Objectives

The same codebase can be optimized for different objectives by choosing different EVOLVE-BLOCK placements:

**Objective: maximize prediction accuracy (model selection freedom)**

```python
def model_tuning():
    import sklearn as sk
    # EVOLVE-BLOCK-START
    # Free to choose any sklearn model and hyperparameters
    # EVOLVE-BLOCK-END
```

**Objective: optimize feature engineering (model is fixed)**

```python
def preprocessing():
    import scipy as sc
    import statsmodels as sm
    # EVOLVE-BLOCK-START
    # Complex feature transformation using sc and sm
    # EVOLVE-BLOCK-END

def model_tuning():
    from sklearn import linear_model as glm
    model = glm.Lasso  # FIXED: model is not evolved
```
