# Runtime Configuration (Sections 6-10)

## 6. Data Requirements

### 6.1 Basic Use Cases (No External Data Needed)

Most AlphaEvolve use cases do not require large real-world datasets. The constraints, design space, and optimization objective are sufficient when defined correctly:

- Mathematical optimization (circle packing, scheduling, etc.)
- Algorithm design (sorting, searching, heuristics)
- Code optimization (compiler optimizations, kernel design)

The evaluation function generates test data synthetically with fixed seeds for reproducibility.

### 6.2 Complex Use Cases (Real Data Required)

Some high-impact use cases require real-world data:

- Testing functional correctness across a spectrum of inputs (e.g., chip design optimization)
- Estimating performance via predictive modeling (e.g., ML pipeline optimization)
- Directly measuring solution performance when simulation is insufficient (e.g., infrastructure configuration)

### 6.3 Data Handling Guidelines

- **Never hardcode data** into the seed program. This hinders AE's ability to interpret the code and adds data management complexity.
- Data used for evaluation must be **representative of production.**
- Use **deterministic data loading** (fixed seeds, versioned datasets).
- All MLOps best practices for data management still apply.

### 6.4 Large Dataset Strategies

**Option 1: K-fold parallel evaluation.**

Split the full dataset into k folds. Run evaluation concurrently across multiple evaluator instances (one per fold). Perform validation tests only once (data distribution doesn't matter for syntax/import checks). Aggregate performance scores across instances.

Works best when parallel evaluation is cost-effective.

**Option 2: Stratified subsample.**

Use a single sample small enough for fast evaluation. Sample intentionally (stratified, semantic distribution) to ensure the small sample score generalizes to the full dataset. After the experiment, re-validate the optimal solution on the full dataset.

Works best when the distribution structure is well-understood.

---

## 7. Concurrency and Parallelism

The concurrency parameter controls how many programs are generated and evaluated simultaneously. This is the most impactful runtime hyperparameter.

### 7.1 How Concurrency Affects Search

**n=1 (Sequential chain):** Generate one program, wait for evaluation, generate the next. Each generation sees the previous result. Creates a chain of incremental improvements, zooming in on a local optimum. Slowest throughput but most focused exploitation. Useful when you want to intentionally converge on a specific region.

**n=3-12 (Sweet spot):** The most widely used range in practice. Balances exploration and exploitation. Multiple programs are in-flight simultaneously, so some generations don't see the latest results, introducing natural diversity. The evolutionary database has enough throughput for healthy population dynamics.

**n=13-30 (High exploration):** Many programs in parallel. Most generations don't see each other's results. Useful for highly non-convex problems with many local optima where broad exploration matters more than deep exploitation.

**n>30 (Throttled -- avoid):** Going beyond 30 parallel generators throttles the LLM backend. Requests queue up, increasing latency per generation. Unless you have dedicated quota, stay below 30.

### 7.2 Recommendations

| Problem Type | Concurrency | Rationale |
| --- | --- | --- |
| Well-understood, tuning known approach | 3-5 | Focused exploitation |
| General optimization, unknown landscape | 8-12 | Balanced |
| Highly non-convex, many local optima | 15-25 | Broad exploration |
| Intentional local optimum zoom-in | 1 | Sequential chain |

Start with **concurrency=10** and adjust based on:

- **Score plateau**: increase to escape local optima
- **Many failing evaluations**: decrease to reduce wasted compute
- **Slow evaluations (>5 min)**: higher concurrency keeps pipeline busy
- **Fast evaluations (<10 sec)**: lower concurrency to let generations build on each other's results

---

## 8. LLM Mixture Configuration

### 8.1 Specifying Models

Select generation models directly with the repeatable `--models` flag -- one
flag per model, given as either a bare name or `name=<model>,weight=<w>`.
Weights are **relative ratios and need not sum to 1.0** (e.g. `weight=0.9` +
`weight=0.1` is the same 9:1 ratio as `9` + `1`); an omitted weight defaults to
1.0. The chosen models persist in the profile as a `[[models]]` section.

Common configurations:

| Goal                             | `--models` flag(s)                      |
| -------------------------------- | --------------------------------------- |
| High throughput / simple default | `--models gemini-3.5-flash`             |
| General 90/10 Flash/Pro          | `--models                               |
:                                  : name=gemini-3.5-flash,weight=0.9        :
:                                  : --models                                :
:                                  : name=gemini-3.1-pro-preview,weight=0.1` :
| Hard problems (max quality)      | `--models gemini-3.1-pro-preview`       |

**Constraints:** At most 2 models per experiment. Model availability is
per-region: `gemini-3.5-flash` is served in all enterprise regions
(`global`/`us`/`eu`), while `gemini-3.1-pro-preview` is `global` only -- so any
Flash/Pro mix implies `global`.

### 8.2 When to Maximize Pro

Use 100% Pro (`--models gemini-3.1-pro-preview`) when:

- The problem requires novel algorithmic ideas (mathematical optimization, algorithm discovery, complex heuristic design)
- Mutations involve restructuring code logic, not just parameter changes
- The search space is large and requires creative leaps
-   Flash-heavy experiments (a 90/10 mix) plateaued early

Pro provides stronger reasoning, better understanding of complex algorithms, and more creative mutations.

### 8.3 When Flash-Heavy Is Sufficient

Use a 90/10 Flash/Pro mix or Flash-only when:

- The optimization is essentially parameter tuning
- Code changes are small and localized
- High throughput matters more than mutation quality
- The problem is well-understood
- You want faster iteration (Flash is faster and cheaper)

The simple default `gemini-3.5-flash` is a good starting point for most
problems; add Pro for more reasoning power with a 90/10 Flash/Pro mix or 100%
Pro (`global` only).

### 8.4 Model Selection is Per-Call

The model is selected per-call, not per-experiment or per-generation. In a 90/10 mixture, roughly 9 out of 10 LLM calls go to Flash and 1 to Pro. Any single program may have been generated by either model. The evolutionary database does not distinguish programs by generator model -- selection pressure is based purely on scores.

---

## 9. Context and Prompt Configuration

### 9.1 User Context (Problem Description)

The `user_context` (or problem description) is injected into every generation prompt. It provides the LLM with domain knowledge, mathematical formulations, and constraints.

**Token budget: up to 200,000 tokens performs well.** Beyond 200k tokens, the context window becomes polluted -- the LLM's attention is diluted, reducing mutation quality. If your combined context (problem description + code + previous programs) exceeds 200k tokens, reduce it.

**What to include:**

- Precise mathematical formulation of the optimization problem
- Key constraints and their rationale
- Domain-specific terminology and definitions
- Known good approaches or prior art (guides the LLM's search)
- Specific instructions about what NOT to do

**What NOT to include:**

- General programming tutorials
- Standard library documentation (the LLM already knows numpy, sklearn, etc.). However, DO include documentation for niche or domain-specific libraries the LLM may not know well (custom kernel APIs, proprietary SDKs, specialized DSLs).
- Raw arbitrary data, spreadsheets, or data dumps. Data belongs in the evaluator, not in the context.
- Unrelated context that consumes tokens without search signal

Every piece of context included should earn its place by helping the LLM produce better mutations.

### 9.2 Evaluation Feedback (Insights)

After each evaluation, the evaluator can return feedback text alongside scores. This feedback is included in future prompts:

```python
return {
    "score": 0.85,
    "insights": [
        {"label": "performance",
         "text": "Latency improved but accuracy dropped 2%"},
        {"label": "constraint",
         "text": "Memory exceeded 4GB on test case 7"},
    ]
}
```

Good feedback is specific, actionable, and concise. Bad feedback is generic ("evaluation failed") or excessively verbose.

The `extra_evaluation_feedback` field in the API maps to the insights array. These strings are shown to the LLM in subsequent generations, allowing it to learn from failures.

### 9.3 Built-in Prompt Diversification

AlphaEvolve automatically diversifies the prompts it sends to the LLM. This is handled internally and requires no user configuration. The system varies its instructions across generations to encourage diverse mutations and prevent the LLM from falling into repetitive patterns. This is one of the key mechanisms that helps AlphaEvolve explore broadly rather than getting stuck in narrow solution regions.

### 9.4 Code Readability

**Code complexity as an auxiliary metric.** If readability matters for your use case, consider adding code length or cognitive complexity as a secondary metric. AE can achieve up to 50% compression without affecting performance. However, the LLM will exploit any simplicity metric (e.g., removing comments to reduce character count), so use metrics that capture meaningful complexity (cyclomatic complexity, AST node count) rather than raw length.

---

## 10. Experiment Hyperparameters

### 10.1 Recommended Starting Values

| Parameter      | Recommendation               | Notes                       |
| -------------- | ---------------------------- | --------------------------- |
| `max_programs` | 100 (start), up to ~1000 for | Total evaluation budget     |
:                : hard problems                :                             :
| `concurrency`  | 10 (start), adjust per       | Parallel generators         |
:                : Section 7                    :                             :
| `models`       | default `gemini-3.5-flash`;  | See Section 8               |
:                : add a 90/10 Flash/Pro mix or :                             :
:                : 100% Pro for harder problems :                             :
| `max_duration` | Longer for Pro-heavy (slower | Total experiment wall clock |
:                : generation)                  :                             :

### 10.2 Choosing the Right Baseline

**Do not start from a super-optimized baseline.** If your initial program is already near-optimal, AlphaEvolve will have difficulty hill-climbing because there is very little room to improve. It may make minor adjustments around the local optimum but will not explore broadly.

Start with a **reasonable but not maximally optimized** baseline. A good starting point is one that:

- Is functionally correct (passes all verification tests)
- Implements a straightforward approach (not the most clever one)
- Has clear room for algorithmic improvement
- Achieves a score that is meaningfully below the theoretical optimum

This gives AlphaEvolve space to explore and hill-climb. You can always use a coding agent to fix obvious bugs and improve the baseline to a reasonable level (see Section 3.4 in `experiment_design.md`), but don't over-optimize it before handing it to AE.

Starting from a trivial implementation can outperform starting from the best known solution. The AE team confirms: "Starting from best solution = introducing your bias, which could be a good headstart, but could also guide the model down a suboptimal direction." Multiple users and the team recommend **trying both** a trivial and a well-optimized starting point on the same problem and comparing the final results.

### 10.3 Iterating on Experiments

A single run rarely produces the optimal result. Plan for 2-5 iterations:

1. **Run 1 (exploration)**: Broad EVOLVE-BLOCK, 100 programs, concurrency 10. Goal: understand the landscape.
2. **Run 2 (refinement)**: Narrow EVOLVE-BLOCK to the most promising region. Use the best program from Run 1 as the new seed. 200 programs, concurrency 5.
3. **Run 3 (exploitation)**: Further narrow focus. 500 programs, concurrency 3. Zoom in on the global optimum.

Between runs, analyze the score distribution. If many programs score similarly, the search space may be over-constrained or the metric needs more discriminative power.

**Long-running experiments are viable and sometimes necessary.** Documented examples from users:

- 5 hours per evaluation on a single V100, running for ~1 week
- 2+ hours per evaluation on 100 V100s in parallel, running for 1+ month (and this long run was the only way to obtain the best results)
- "Convergence depends on the number of iterations, not time. If you set a 10-minute limit and an iteration takes 20 minutes, you will not converge."

If your problem is valuable enough, running for weeks or months is reasonable. Use two-stage evaluation (Section 5.8 in `evaluator_and_scoring.md`) to keep iteration speed manageable with expensive evaluations.
