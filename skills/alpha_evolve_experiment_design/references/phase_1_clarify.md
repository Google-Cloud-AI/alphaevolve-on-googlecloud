# Phase 1 — Clarify

> **This phase is conversation only.** The only file written is
> `experiment_description.json`. No code files.

## Objective

Understand the user's problem and fill the `ExperimentDescription` model
completely. Read `resources/experiment_description_schema.py` for the full
schema — every field must be populated before Phase 1 is complete.

---

## Step 1: Analyze the Request

Identify the problem type:

| Type | Signal | Example |
|---|---|---|
| **New optimization problem** | User describes a problem to solve | "Pack circles in a unit square" |
| **Algorithm discovery** | User wants a better algorithm | "Find a better sorting algorithm" |
| **Function improvement** | User has existing code to optimize | "Make this function faster" |

For **function improvement**, immediately ask the user to provide or point to
the source file(s). If the user points to a single file, extract the function
text into `source_code`. If the user points to a directory or multiple files,
proceed to Step 1b.

---

## Step 1b: Multi-File Scan (if applicable)

> Read `references/multi_file_guide.md` for the full multi-file workflow.

When the user points to a **directory or multiple source files**:

1. **Inventory**: Scan the files. For each, compute size (chars), estimated
   tokens (chars/4), and check for EVOLVE-BLOCK markers.
2. **Select**: Identify which files are optimization targets (have or need
   EVOLVE-BLOCK) and which are context (imported by targets). Exclude tests,
   scripts, and unrelated files.
3. **Budget check**: Sum tokens for included files. If under 200k tokens,
   proceed. If over, discuss the Extract and Isolate fallback with the user.
4. **Present**: Show the inventory table and proposed selection. Get user
   confirmation before proceeding.
5. **Populate `source_files`**: Record the selected files (path, content,
   has_evolve_block) in the `ExperimentDescription`. When `source_files` is
   set, `source_file` and `source_code` are ignored.

---

## Step 2: Propose an ExperimentDescription

**Be autonomous.** Fill in ALL fields with your best-guess defaults. Present
them as a table:

```markdown
| Field | Proposed Value | Notes |
|---|---|---|
| `name` | `circle_packing` | Project slug |
| `title` | `Circle Packing in Unit Square` | |
| `problem_description` | *[draft text]* | Sent to LLM as context |
| `metric_name` | `sum_of_radii` | Primary metric |
| `metric_direction` | `maximize` | |
| `eval_inputs` | `{"n": 26}` | Test case parameters |
| `allowed_imports` | `["numpy"]` | |
| `forbidden_imports` | `[]` | |
| `initial_program_description` | *[draft text]* | What solve() does |
| `evolve_block_description` | *[draft text]* | What goes in EVOLVE-BLOCK |
| `evaluation_strategy` | `FIXED_BENCHMARK` | *[alternatives listed]* |
| `timeout_seconds` | `30` | |
| `dependencies` | `["numpy"]` | |
| `constraints` | `[]` | |
```

### Strategy selection guidance

Read the `EvaluationStrategy` enum values for complete implementation guides.
Pick the best one and explain why:

- **FIXED_BENCHMARK**: Default for most problems. Simple, fast.
- **MULTI_RUNG_LADDER**: When difficulty scales with N. Also populate `rungs`.
- **PARTIAL_CREDIT**: When binary pass/fail would stall evolution.
- **COMPOSITE_MULTI_OBJECTIVE**: When balancing competing goals.

List 1–2 alternatives and briefly explain what they'd change.

### Guidelines

- **Propose, don't ask.** Fill every field. The user confirms or tweaks.
- **Be specific.** Don't write "TBD" or "to be determined" in any field.
- **Draft the `problem_description`.** This is the most important field — it's
  the context the LLM uses to generate code. Write a complete, precise
  description of the problem, including inputs, outputs, and success criteria.
- **Draft the `evolve_block_description`.** Be explicit about what functions
  and logic go inside the EVOLVE-BLOCK.

---

## Step 3: Ask Targeted Questions

Only ask about fields you **cannot** infer. Use the `ask_question` tool for
multiple-choice questions where possible.

Good questions:

- "Should the evolved code be allowed to use scipy, or pure numpy only?"
  → affects `allowed_imports` and `forbidden_imports`
- "The problem scales with N. Should I use a multi-rung ladder (test at
  N=5, 20, 100) or a single fixed benchmark at N=100?"
  → affects `evaluation_strategy` and `rungs`

Bad questions:

- "What should the metric name be?" → You should propose one.
- "What dependencies do you need?" → Infer from the problem.

---

## Step 4: Iterate

Refine based on user feedback. Re-present the table after changes.
Continue until the user approves.

---

## Step 5: Write experiment_description.json

Once approved, write the `ExperimentDescription` as JSON:

```bash
project_dir/.evolve/experiment_description.json
```

Use `ExperimentDescription.model_dump_json(indent=2)` format. This signals
Phase 1 completion.

> [!IMPORTANT]
> **Proceed immediately to Phase 2.** Read `references/phase_2_implement.md`.
