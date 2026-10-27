# API and Infrastructure (Sections 12-16)

## 12. API Reference

### 12.1 Experiment Lifecycle

```
CREATED --> [start] --> RUNNING --> COMPLETED
                            |          |
                            v          v
                         PAUSED    FAILED
                            |
                            v
                     [resume] --> RUNNING
```

### 12.2 Program States

```
INITIALIZED --> GENERATING --> EVALUATING --> COMPLETED
```

Programs are acquired with a lock token for concurrency control. The evaluator must submit scores with the matching lock token.

### 12.3 Key API Fields

**AlphaEvolveExperimentConfig:**

| Field | Type | Description |
| --- | --- | --- |
| `title` | string | Experiment display name |
| `problem_description` | string | Injected into LLM prompt as context |
| `programming_language` | string | Language of the evolved code |

**RunSettings:**

| Field          | Type     | Default  | Description                 |
| -------------- | -------- | -------- | --------------------------- |
| `max_programs` | int      | Required | Total programs to evaluate  |
:                :          :          : (must be > 1)               :
| `concurrency`  | int      | Required | Parallel generators (must   |
:                :          :          : be > 0). See Section 7 in   :
:                :          :          : `runtime_configuration.md`. :
| `max_duration` | Duration | -        | Maximum experiment          |
:                :          :          : wall-clock time             :
| `idle_timeout` | Duration | -        | Pause if no evaluations for |
:                :          :          : this long                   :

**GenerationSettings:**

| Field     | Type                    | Description                            |
| --------- | ----------------------- | -------------------------------------- |
| `context` | string                  | Free-form text inserted into the LLM   |
:           :                         : prompt for candidate generation; use   :
:           :                         : for problem description / custom hints :
:           :                         : / instructions (up to ~200k tokens).   :
| `models`  | repeated ModelConfig    | Per-model configuration: `name`,       |
:           :                         : `weight` (optional, relative; need not :
:           :                         : sum to 1.0), and optional              :
:           :                         : `temperature`. Mutually exclusive with :
:           :                         : `model`.                               :
| `model`   | Model enum (DEPRECATED) | Legacy single-preset selector,         |
:           :                         : superseded by `models`; ignored if     :
:           :                         : `models` is set.                       :

**EvolutionSettings:**

| Field | Type | Description |
| --- | --- | --- |
| `reset_interval` | int | Island reset frequency (in generations) |

**AlphaEvolveProgramContent:**

| Field | Type | Description |
| --- | --- | --- |
| `files` | repeated AlphaEvolveSourceFile | Program files |
| `description` | string | Program description |

**AlphaEvolveSourceFile:**

| Field | Type | Description |
| --- | --- | --- |
| `path` | string | File path (e.g., `initial_program.py`) |
| `content` | string | File content |
| `program_language` | string | Language identifier |
| `description` | string | File description (shown to LLM) |

**AlphaEvolveProgramEvaluation:**

| Field | Type | Description |
| --- | --- | --- |
| `scores` | AlphaEvolveScores | Score values per metric |
| `insights` | repeated AlphaEvolveInsight | Feedback text for LLM |

### 12.4 Score Output Format

Single metric:

```json
{"score": 0.95, "insights": [{"label": "metric", "text": "details"}]}
```

Multiple metrics:

```json
{
  "scores": [
    {"metric": "accuracy", "score": 0.95},
    {"metric": "latency", "score": -42.5}
  ],
  "insights": [
    {"label": "accuracy", "text": "0.9500"},
    {"label": "latency", "text": "42.5ms"}
  ]
}
```

The insights array is passed back to the LLM in future generation prompts. Use it to provide actionable feedback that helps the LLM understand why a score is good or bad.

---

## 13. Evaluator Architecture Patterns

Evaluation runs on your infrastructure. You acquire programs from the API, evaluate them, and submit scores back via SubmitEvaluations.

**Architecture patterns by complexity:**

- **Simple**: Single machine or Cloud Run container running evaluations sequentially. Each candidate runs in its own virtualenv or subprocess.
- **Medium**: Cloud Run with parallel virtualenvs isolating each candidate solution. Validation runs once, then evaluation fans out.
- **Complex**: GKE orchestrator dispatching to multiple Cloud Run evaluator instances. Validation and verification run centrally, performance evaluation is distributed.
- **Edge/hardware**: GKE validator (compile checks) + custom hardware evaluator (load tests on specialized devices, networking cards, etc.)
- **3P SaaS**: Validation on GKE, then dispatch to external SaaS environments for synthesis, simulation, or verification (e.g., Verilog simulators, EDA tools).

**Key principle**: Separate validation (does it compile?) from verification (is it correct?) from evaluation (how well does it perform?). Run validation first to avoid wasting expensive evaluation compute on broken programs.

---

## 14. Language Support

The AlphaEvolve API is language-agnostic. The LLM generates mutations in whatever language the initial program uses. The `programming_language` field in the experiment config tells the LLM which language to expect.

**Via the API**, supported languages include:

- **Python** -- most common, best LLM support
- **Verilog/SystemVerilog** -- hardware design (RTL optimization, custom filter design)
- **C/C++** -- kernel optimization, performance-critical code
- **CUDA** -- GPU kernel optimization
- **Julia** -- scientific computing
- **Any language** the LLM can read and write

**Via the `ae` CLI and agent skills**, only **Python** is currently supported. The CLI's evaluator protocol (`--program-dir`, `initial_program.py`, `uv run pytest`) assumes Python. For non-Python languages, use the API directly with your own evaluation infrastructure.

For Verilog specifically, keep EVOLVE-BLOCK-START inside module definitions to prevent AE from replacing one module with multiple modules:

```verilog
module custom_filter(
    // EVOLVE-BLOCK-START
    // Filter logic here
    // EVOLVE-BLOCK-END
)
endmodule
```

---

## 15. Cost and Quota

### 15.1 Cost Drivers

An AlphaEvolve experiment's cost comes from two sources:

1. **LLM calls**: one call per generated program. Cost depends on the model mixture:
   - Pro calls are more expensive than Flash
   - Token count per call depends on program size + context + previous programs
   - A 100-program experiment with 50/50 mixture = ~50 Pro calls + ~50 Flash calls

2. **Evaluation compute**: your own infrastructure costs. This depends entirely on your evaluator setup (local machine, Cloud Run, GKE, custom hardware, etc.).

### 15.2 Quota Considerations

- **LLM quota**: with concurrency > 30, you will hit rate limits and experience throttling. Stay under 30 for shared quota.
- **API rate limits**: the AlphaEvolve API has per-project rate limits on GeneratePrograms and SubmitEvaluations RPCs.

### 15.3 Budget Planning

| Experiment Size | Programs | Est. LLM Calls | Typical Duration |
| --- | --- | --- | --- |
| Small (exploration) | 100 | 100 | 1-3 hours |
| Medium (refinement) | 500 | 500 | 6-12 hours |
| Large (hard problem) | 1000 | 1000 | 12-48 hours |

Duration depends heavily on evaluation latency and concurrency. Higher concurrency reduces wall-clock time but increases peak LLM load.

---

## 16. Security, Data Privacy, and Compliance

### 16.1 Data Handling

- Candidate program code is sent to the AlphaEvolve API for LLM-based mutation (this means the LLM sees your code)
- Evaluation runs on YOUR infrastructure -- evaluation data never leaves your environment unless you send it
- Scores and feedback text are sent back to the API and included in future LLM prompts

### 16.2 Compliance Considerations

For teams with strong risk and compliance constraints:

- Work with your InfoSec/Platform team to validate that the AlphaEvolve API meets security, data privacy, and data sovereignty requirements
- Review which data flows through the LLM: problem descriptions, program code, scores, and evaluation feedback (insights) are all sent to the LLM ensemble
- Evaluation data stays on your infrastructure -- only scores and feedback text are returned to the API
- Ensure your evaluation infrastructure meets your org's compliance requirements

### 16.3 Code Supply Chain

AlphaEvolve-generated code may import libraries that your organization has not approved. The evaluator's validation tier should check imports against an allowlist. The `allowed_imports` and `forbidden_imports` fields in the experiment description can be used to communicate these constraints to the LLM (though enforcement must happen in the evaluator, not the LLM -- the LLM may ignore these hints).
