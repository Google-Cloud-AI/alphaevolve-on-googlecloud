# Troubleshooting (Section 11)

## 11. Common Failure Modes and Troubleshooting

### 11.1 Score Plateau

**Symptom**: Score stops improving after N programs.

**Debugging workflow**:

1. Check the score distribution -- is it a genuine plateau or just slow improvement?
2. Check failure rate -- are most programs failing evaluation?
3. Check the EVOLVE-BLOCK scope -- is it too narrow?

**Fixes**:

- Increase concurrency to explore more broadly
- Widen the EVOLVE-BLOCK to give AE more freedom
- Add auxiliary metrics to provide richer gradient signal
- Consider an island reset (`reset_interval`)
- Check if the metric has a ceiling (e.g., AUC approaching 1.0)
- Try a different LLM mixture (more Pro for harder problems)

**Real-world convergence timelines from users**: experiments can be stuck for **6 days** before a breakthrough. One user documented **3 weeks** of no improvement followed by a sudden jump. "Sometimes it's stuck for a day or two, and then it suddenly improves." Do not assume a plateau means AE has converged -- patience can pay off for hard problems.

**When stuck, users recommend:**

- Restart with the best solution from the current run as the new initial program for a fresh experiment. This effectively re-seeds the database with a strong starting point.
- Add "bad" or "previous best" solutions into the prompt context, then try to re-evolve from baseline.
- The LLM is good at **stochastic recombination** of ideas from its training data and the prompt, but it generally **cannot create entirely new knowledge**. Changing the prompt can unlock different parts of the LLM's training data.

### 11.2 Most Programs Fail Evaluation

**Symptom**: >50% of programs return None scores.

**Debugging workflow**:

1. Check evaluator logs -- what is the most common failure?
2. Is it syntax errors, import errors, or runtime errors?
3. Is the EVOLVE-BLOCK too large?

**Fixes**:

- Return partial scores instead of None (percentage of tests passed)
- Narrow the EVOLVE-BLOCK
- Add missing imports as immutable code
- List available libraries in the problem description
- Add validation tests that return informative feedback

### 11.3 Experiment PAUSED Unexpectedly

**Symptom**: Experiment transitions to PAUSED and stops generating new programs.

**Cause**: The experiment has an idle timeout. If no evaluations are submitted for a sustained period (typically because the evaluation loop crashed, the evaluator is timing out, or more programs are acquired than are being evaluated), the experiment automatically pauses to prevent runaway resource consumption.

**Debugging workflow**:

1. Check if your evaluation loop is still running
2. Check evaluator logs for crashes or timeouts
3. Verify scores are being submitted successfully (check for API errors)
4. Check if evaluations are taking longer than expected (backed up queue)

**Fix via CLI**:

```bash
ae experiment resume <experiment-nickname>
```

**Fix via API**: Call the ResumeExperiment RPC:

```
POST /{name}:resume
```

This returns a long-running operation. Once the operation completes, the experiment returns to RUNNING state and resumes generating programs.

After resuming, ensure the root cause is fixed (evaluator restarted, timeouts increased, etc.) or the experiment will pause again.

### 11.4 Scores Not Monotonically Increasing

**Symptom**: Polling the latest generated program shows a lower score than a previously generated one.

**This is expected behavior.** The generation process creates programs whose scores are unknown before evaluation. Even with concurrency=1, a newly generated program may score worse than its parent -- this is not gradient descent, it is evolutionary search. Many mutations are neutral or harmful; the evolutionary database keeps only the improvements. The best score across all programs should generally trend upward over time, but individual programs will fluctuate.

**Via CLI:**

```bash
ae results best <experiment-nickname> --top 5
```

**Via API:** Use ListAlphaEvolvePrograms with order_by to sort by metric score:

```
GET /{parent}/alphaEvolvePrograms?order_by=<metric_name> desc&page_size=5
```

This returns programs sorted by the specified metric. You can also filter by state:

```
GET /{parent}/alphaEvolvePrograms?state_filter=COMPLETED&order_by=<metric> desc
```

### 11.5 Reward Hacking Detected

**Symptom**: Score increases but manual inspection shows the solution is gaming the metric.

**Fixes**: See Section 5.7 in `evaluator_and_scoring.md` (Reward Hacking Prevention). Adjust weights, add verification tests, add anti-hacking instructions to the problem description.

### 11.6 LLM Throttling

**Symptom**: Generation latency increases; programs take minutes instead of seconds.

**Cause**: Concurrency exceeds 30.

**Fix**: Reduce concurrency below 30. Optimal range is 3-12.

### 11.7 Context Window Pollution

**Symptom**: Mutation quality degrades as the experiment progresses.

**Cause**: Combined program + context + previous programs exceeds ~200k tokens.

**Fix**: Reduce program LOC (move boilerplate to context files). Shorten user context. Consider splitting the problem into smaller sub-problems.
