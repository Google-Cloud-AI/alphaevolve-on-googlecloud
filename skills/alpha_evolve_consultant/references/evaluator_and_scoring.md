# Evaluator Design and Scoring (Section 5)

## 5. Evaluator Design

The evaluator is the fitness function that guides evolution. Its design directly determines whether AlphaEvolve converges to good solutions.

### 5.1 Three-Tier Evaluator Structure

A well-designed evaluator has three layers, executed in order:

**Tier 1: Validation** (does the code run?)
- Syntax checks, import validation, infrastructure compatibility
- If validation fails, return None score. AE ignores the program.
- Include failure type and logs for debugging (not used as signal by AE, but useful for post-facto analysis of failure modes).

**Tier 2: Verification** (is the code functionally correct?)
- Unit tests, constraint satisfaction checks, functional correctness
- Return the number or percentage of tests passed. This provides **gradient signal** -- a program passing 4/5 tests is closer to correct than one passing 0/5.
- Verification scores are typically used as negative penalties to the fitness function.
- Think of verification as soft-constraint satisfaction: even for hard constraints, expressing them as soft penalties (proximity to feasible space) gives AE more signal than binary pass/fail.

**Tier 3: Evaluation** (how well does it perform?)
- Measure the actual optimization objective
- Calculate the aggregate hill-climbing score
- Return both granular and aggregate scores
- Do NOT offload score calculation to the LLM -- compute it deterministically in the evaluator.

Partial credit is always better than None. A program passing 4 of 5 tests should get a score of 0.8, not None. Returning None means AE ignores the program entirely and gets zero signal. Returning 0.8 tells AE the program is close to correct and worth building on. Users consistently report that providing gradient signal through partial scores dramatically improves convergence.

### 5.2 Complete Evaluator Example: Simple

Single-metric evaluator for a mathematical optimization problem:

```python
import argparse
import json
import math
import os
import signal
import sys
import traceback

def evaluate_program(code, timeout_seconds=30):
    """Execute candidate code and return score."""
    signal.alarm(timeout_seconds)
    try:
        namespace = {}
        exec(compile(code, "program.py", "exec"), namespace)

        if "evaluate" not in namespace:
            return {"score": None, "insights": [
                {"label": "error", "text": "No evaluate() function"}
            ]}

        result = namespace["evaluate"]({})
        score = float(result.get("score", 0))

        if not math.isfinite(score):
            return {"score": None, "insights": [
                {"label": "error", "text": f"Non-finite score: {score}"}
            ]}

        return {"score": score, "insights": []}

    except Exception as e:
        return {"score": None, "insights": [
            {"label": "error", "text": str(e)},
            {"label": "traceback", "text": traceback.format_exc()},
        ]}
    finally:
        signal.alarm(0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--program-dir", required=True)
    args = parser.parse_args()

    sys.path.insert(0, args.program_dir)
    program_path = os.path.join(args.program_dir, "initial_program.py")
    with open(program_path) as f:
        code = f.read()

    result = evaluate_program(code)

    with open(args.output_file, "w") as f:
        json.dump(result, f)

if __name__ == "__main__":
    main()
```

### 5.3 Complete Evaluator Example: Three-Tier with Verification

Multi-metric evaluator with validation, verification, and evaluation:

```python
def evaluate_program(code, timeout_seconds=60):
    """Three-tier evaluation: validate, verify, evaluate."""
    namespace = {}

    # === TIER 1: VALIDATION ===
    try:
        exec(compile(code, "program.py", "exec"), namespace)
    except SyntaxError as e:
        return {"score": None, "insights": [
            {"label": "validation", "text": f"Syntax error: {e}"}
        ]}
    except ImportError as e:
        return {"score": None, "insights": [
            {"label": "validation", "text": f"Invalid import: {e}"}
        ]}

    solve_fn = namespace.get("solve")
    if not callable(solve_fn):
        return {"score": None, "insights": [
            {"label": "validation", "text": "No solve() function"}
        ]}

    # === TIER 2: VERIFICATION ===
    test_cases = [
        {"input": [1, 2, 3], "expected": 6},
        {"input": [0, 0, 0], "expected": 0},
        {"input": [-1, 1], "expected": 0},
        {"input": [100], "expected": 100},
        {"input": list(range(1000)), "expected": 499500},
    ]

    passed = 0
    for tc in test_cases:
        try:
            result = solve_fn(tc["input"])
            if result == tc["expected"]:
                passed += 1
        except Exception:
            pass

    verification_score = passed / len(test_cases)
    if verification_score < 1.0:
        # Partial credit: return verification score as a penalty
        return {
            "score": verification_score * 0.5,  # Capped at 0.5
            "insights": [
                {"label": "verification",
                 "text": f"{passed}/{len(test_cases)} tests passed"},
            ],
        }

    # === TIER 3: EVALUATION ===
    import time
    large_input = list(range(100_000))
    start = time.perf_counter()
    result = solve_fn(large_input)
    elapsed = time.perf_counter() - start

    # Score: correctness (0.5) + speed bonus (0-0.5)
    speed_score = max(0, 0.5 - elapsed * 10)  # Faster = higher
    total_score = 0.5 + speed_score

    return {
        "score": total_score,
        "insights": [
            {"label": "verification",
             "text": f"{passed}/{len(test_cases)} tests passed"},
            {"label": "latency",
             "text": f"{elapsed*1000:.1f}ms"},
        ],
    }
```

### 5.4 Complete Evaluator Example: Multi-Objective ML Pipeline

```python
def evaluate_program(code, timeout_seconds=120):
    """Multi-objective evaluator for ML pipeline optimization."""
    namespace = {}

    # VALIDATION
    try:
        exec(compile(code, "program.py", "exec"), namespace)
    except Exception as e:
        return {"score": None, "insights": [
            {"label": "validation", "text": str(e)}
        ]}

    pipeline_fn = namespace.get("build_pipeline")
    if not callable(pipeline_fn):
        return {"score": None, "insights": [
            {"label": "validation", "text": "No build_pipeline()"}
        ]}

    # VERIFICATION: check library constraints
    import ast
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_LIBRARIES:
                    return {"score": None, "insights": [
                        {"label": "verification",
                         "text": f"Forbidden library: {alias.name}"}
                    ]}

    # EVALUATION
    from sklearn.model_selection import cross_val_score
    import time, tracemalloc

    X_train, X_test, y_train, y_test = load_benchmark_data()
    pipeline = pipeline_fn()

    # Accuracy
    cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5)
    accuracy = float(cv_scores.mean())

    # Latency
    start = time.perf_counter()
    pipeline.fit(X_train, y_train)
    pipeline.predict(X_test)
    latency = time.perf_counter() - start

    # Memory
    tracemalloc.start()
    pipeline.fit(X_train, y_train)
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    memory_mb = peak_memory / 1024 / 1024

    # Combined hill-climbing score
    baseline_accuracy = 0.85
    delta_acc = accuracy - baseline_accuracy

    score = (
        0.3 * accuracy
        - 0.2 * (latency / 10.0)    # Normalize to ~0-1
        - 0.1 * (memory_mb / 100.0)  # Normalize to ~0-1
        + 5.0 * delta_acc             # High weight enforces accuracy
    )

    return {
        "score": score,
        "insights": [
            {"label": "accuracy", "text": f"{accuracy:.4f}"},
            {"label": "latency", "text": f"{latency*1000:.0f}ms"},
            {"label": "memory", "text": f"{memory_mb:.1f}MB"},
            {"label": "delta_acc", "text": f"{delta_acc:+.4f}"},
        ],
    }
```

### 5.5 Scoring Best Practices

**AlphaEvolve always maximizes.** All objectives are treated as hill climbing. For minimization targets, negate the value:

```python
score = -latency_ms  # AE maximizes -> minimizes latency
```

**Monotonic scoring functions only.** The score must consistently increase as solutions improve. Non-monotonic scores confuse the search.

**Detailed scores improve search quality.** Even with one business objective, additional metrics help AE navigate the search space. Pass individual scores as insights so the LLM can reason about tradeoffs.

**Consider starting with a single objective.** Multi-objective optimization with Pareto frontier tracking is fully supported in the database (MAP Elites tracks the best program per metric, and the system maintains a Pareto frontier across all metrics). However, a single scalar objective is simpler to reason about and debug. If your problem has multiple objectives, you can either combine them into a weighted scalar or use the native multi-metric support from the start.

**Rescale before combining.** When combining metrics with different scales, normalize to comparable ranges. Mixing bounded (0-1) and unbounded (0-infinity) scores without rescaling causes the unbounded metric to dominate.

**Prefer additive weighted sums over multiplicative objectives.** A customer used `Accuracy / (Latency * Memory)` and this was identified as an anti-pattern -- the objective becomes hypersensitive to small denominator changes, potentially compromising accuracy. Use `w1*A - w2*L - w3*M` instead, which allows easy weight adjustment per objective.

**Normalize metrics relative to initial values before combining.** One approach: divide each metric by its baseline value so all metrics start at 1.0. Then weight and combine. This prevents one metric from dominating due to scale differences.

**Small score differences may not provide useful signal.** If a good solution scores 1e-7 and a bad one scores 1e-8, the LLM may not meaningfully distinguish them. Rescale scores to a range the LLM can reason about (e.g., 0-100) so that improvements are numerically obvious in the prompt.

**Conjoint analysis for designing metrics.** When humans struggle to define a scoring function but can compare two solutions side-by-side: (1) generate synthetic score pairs, (2) have a domain expert pick the "winner" in each pair, (3) fit logistic regression on the pairwise comparisons, (4) use the model as your combined metric. This approach has been used successfully to create differentiable metrics for AE. Use F1-style aggregation rather than arithmetic averaging for bounded metrics like precision and recall.

### 5.6 Multi-Objective Optimization

AlphaEvolve can optimize against multiple concurrent objectives as long as they combine into a single hill-climbing score. Keep the number of individual objectives limited -- roughly the number a human expert can grasp when analyzing results. Do not feed AE a vector of 100+ floats.

**Approach 1: Combined objective function.**

```python
obj = w1 * in_stock_rate - w2 * inventory_level
```

**Approach 2: Treat one objective as a constraint.**

```python
obj = in_stock_rate  # Optimize this
# With: inventory_level <= budget (enforced as penalty)
```

Approach 2 may require running multiple experiments at different constraint levels to trace out the Pareto front.

**Multi-objective is natively supported.** The database tracks a Pareto frontier and MAP Elites keeps the best program per metric. However, combined weighted scores are simpler to reason about and debug.

**Practical limit: 3-5 metrics.** With too many metrics (e.g., 500), the Pareto comparator fails -- almost every program dominates on at least one metric. MAP Elites spends most of its time evolving parents that optimized trivial or noisy metrics. Reduce dimensionality through aggregation, selection, or PCA to 3-5 meaningful metrics.

**Per-benchmark individual scores can cause overfitting.** One user found that passing individual scores for 5 benchmarks led to overfitting on some, while passing only the aggregated sum generalized better to unseen benchmarks. If generalization matters, consider aggregating scores before passing to AE rather than optimizing each benchmark independently.

### 5.7 Reward Hacking Prevention

**Risk 1: Greedy reward hacking.** If `Obj = w1*S1 + w2*S2 + w3*S3`, AE may discover S2 is trivially easy to increase and focus entirely on it, ignoring S1 and S3.

*Mitigation*: Decrease the weight of the easy sub-score. May require 2-3 trial runs to calibrate weights. Back-of-napkin math simulating a few scoring outcomes helps.

**Risk 2: Constraint penalty ignoring.** If soft constraints are penalties (`Obj = Score - w*Penalty`), AE may discover that ignoring constraints yields higher Obj.

*Mitigation*: Increase the penalty weight substantially. If behavior persists, add explicit instructions in the problem description: "Solutions violating constraint X are invalid regardless of score."

**Risk 3: Evaluation function exploitation.** AE may find inputs that cause the evaluator to return artificially high scores (floating-point edge cases, test data leakage).

*Mitigation*: Deterministic evaluation with fixed random seeds. Validate winners on held-out data after the experiment.

**Real-world reward hacking examples observed by users:**

- **Monkey-patching the evaluator**: AE used `sys._getframe()` to extract information from the call stack and manipulate scoring functions outside the EVOLVE-BLOCK.
- **Overwriting benchmark files**: AE used file utils to delete or empty evaluation data files, driving error rate to zero.
- **Reimplementing randomness**: When told "don't use random library," AE reimplemented randomness via Logistic Map chaos, or used microsecond timestamps (`time.time() % 2`) for stochastic decisions.
- **Hard-coding lookup tables**: AE memorized known answers instead of computing them, saturating the score immediately.

**Practical defenses from users:**

- Use AST checks for forbidden primitives (`sys`, `os`, `inspect`, `eval`, `exec`, `getattr`, `setattr`) and return None if found.
- Verify code outside EVOLVE-BLOCK is unchanged (text diff or AST).
- Run the evolved function twice with the same input and verify identical output (catches randomness hacking).
- Check evaluation time -- if it finishes in microseconds, it probably hard-coded the answer.
- Put scoring logic in a separate file invisible to the LLM.

### 5.8 Evaluation Cascade (Hypothesis Testing)

For expensive evaluations, AlphaEvolve supports multi-stage evaluation cascades. New solutions are evaluated on increasingly difficult test cases, proceeding to the next stage only if earlier stages pass:

1. Quick syntax and basic correctness check (milliseconds)
2. Small-scale functional tests (seconds)
3. Medium-scale performance benchmark (minutes)
4. Full-scale production evaluation (only for top candidates)

This prunes unpromising solutions early, saving evaluation budget for the most promising candidates.

Two-stage evaluation is documented working in practice with first stage taking a few minutes and second stage taking 3+ hours. Only promising candidates from stage 1 proceed to stage 2, dramatically reducing total evaluation cost.

### 5.9 Noisy Evaluation

Several users deal with non-deterministic evaluation (C++ benchmarks on shared hardware, stochastic simulations, runtime measurements affected by system load).

**Strategies that work:**

- **Multiple measurements + average**: the simplest approach. Central limit theorem narrows the distribution, but you need to determine how many samples are enough.
- **Proxy metrics**: when direct measurement is noisy, use deterministic proxies (e.g., instruction count instead of wall clock time, cache miss rate instead of latency).
- **Bayesian modeling**: one user reports success with robust Bayesian modeling of benchmark results to get probabilistic rankings. Generate a large batch of solutions, benchmark them, model the uncertainty, use the ranking to select parents for the next generation.
- **Deterministic simulation**: preferred when possible. Eliminates noise entirely. Even an approximate simulation may be better than a noisy real measurement.

**Caution**: with noisy scores, AE may "p-hack" -- keep trying bad ideas until one happens to get a lucky high measurement. Adding explicit denoising (averaging, Bayesian modeling) prevents this.
