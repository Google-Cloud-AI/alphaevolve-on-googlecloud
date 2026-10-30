# Adaptive Sort C++ Example

This example demonstrates how to evolve a C++ sorting algorithm using the `alpha_evolve` library. It uses a remote Google Cloud Function to compile and evaluate the C++ code safely.

> **Note:** unlike the Rust [`adaptive_sort`](../adaptive_sort) example, the current C++ harness
> benchmarks a single data pattern rather than a range of them. See
> [Metrics](#metrics) for what that means when reading results.

## Directory Structure

- `cloud_function/`: Contains the Cloud Function source code for compiling and executing C++.
- `src/`: Initial C++ source files (`sort.hpp`, `sort_impl.hpp`, `benchmark.hpp`, `benchmark.cpp`) used as the starting point for evolution.
- `run_experiment.py`: The main script to run the evolution experiment.
- `evaluator.py`: Contains the client-side evaluation logic.

## Metrics

The harness benchmarks each candidate over **5 datasets of 100 uniformly-random integers**,
drawn from a seeded `std::mt19937(42)` (`src/main.cpp`). Evaluation is therefore deterministic,
but every dataset shares one distribution and one size.

| Metric | Description |
|--------|-------------|
| `score` | **Primary.** `0.6 × performance_score + 0.4 × adaptability_score`, or `0.0` if any case sorted incorrectly. Higher is better. |
| `performance_score` | `1 / (1 + avg_time × 10)`. Higher is faster. |
| `adaptability_score` | `1 / (1 + σ(times))`. Intended to reward consistency across input shapes. |
| `correctness` | `1.0` if all 5 cases sorted correctly, else `0.0`. |
| `compile_success` | `1.0` if the candidate compiled, else `0.0`. |
| `avg_time` | Mean sort time in seconds across the 5 cases. |
| `memory_safe` | Always `1.0` — a placeholder; nothing currently measures memory. |

Failure paths return a subset: a compile failure yields only `score` and `compile_success`, and
a runtime failure adds `correctness`, `performance_score` and `adaptability_score` at `0.0`.

**Build and run output reaches the model.** Compiler stderr, stdout and any error text are
forwarded to AlphaEvolve as insights, so a candidate that fails to compile comes back with the
compiler's own message attached. If the evaluator service itself is unreachable, the candidate
is left unscored rather than penalized — see the
[scoring convention](../../README.md#scoring-convention).

### Known limitations of the current benchmark

Two properties of the harness limit how far these numbers can be trusted:

- **`adaptability_score` does not measure adaptability.** All 5 datasets share a distribution,
  so the variance it scores is timing jitter rather than a response to differing input shapes.
  The Rust example varies shape and size; this one does not.
- **`score` has very little dynamic range.** Sorting 100 integers takes on the order of a
  microsecond, so `performance_score = 1/(1 + avg_time × 10)` sits near `0.99999` for every
  candidate and `score` lands around `0.9999` for all of them — separated mostly by noise.

Widening the benchmark to the shapes and input sizes used by `adaptive_sort`
(`sort_test/src/main.rs`) would address both.

## Prerequisites

1.  **Python Environment**: Ensure you have the `alpha_evolve` package installed or available in your `PYTHONPATH`.
2.  **GCP Project**: You need a Google Cloud Platform project with Cloud Run and Cloud Build enabled to deploy the evaluator.

## Setup

### 1. Deploy the Evaluator

The experiment requires a remote Cloud Function to build and run C++ code. Deploy it using the following command from the repository root:

```bash
gcloud run deploy cpp-evaluator \
  --source ./examples/adaptive_sort_cpp/cloud_function \
  --memory 1Gi \
  --region us-central1 \
  --project your-gcp-project-id
```
*Note: Use `--allow-unauthenticated` for testing or configure IAM properly for secure access. The `--memory 1Gi` flag is added to avoid potential memory limits during compilation.*

### 2. Configure Environment

Create a `.env` file in the repository root or set the following environment variables:

```bash
# Required for the experiment
PROJECT_ID="your-gcp-project-id"
LOCATION="global"  # or your specific location
COLLECTION="default_collection"
GE_APP_ID="your-engine-id"
ASSISTANT="default_assistant"
BASE_URL="discoveryengine.googleapis.com"

# Required for the evaluator
EVALUATOR_URL=$(gcloud run services describe cpp-evaluator \
  --region us-central1 \
  --project your-gcp-project-id \
  --format 'value(status.url)')
```

## Running the Experiment

To start the evolution process:

```bash
python -m examples.adaptive_sort_cpp.run_experiment
```

The script will:
1.  Initialize the `AlphaEvolveClient`.
2.  Create an experiment in the Alpha Evolve backend.
3.  Upload the initial C++ implementation from `src/`.
4.  Start the controller loop to generate and evaluate new variations.
5.  Print the top programs found at the end.
