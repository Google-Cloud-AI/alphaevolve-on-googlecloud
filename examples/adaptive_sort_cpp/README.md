# Adaptive Sort C++ Example

This example demonstrates how to evolve a C++ sorting algorithm that adapts to different data patterns (random, sorted, reverse, duplicates) using the `alpha_evolve` library. It uses a remote Google Cloud Function to compile and evaluate the C++ code safely.

## Directory Structure

- `cloud_function/`: Contains the Cloud Function source code for compiling and executing C++.
- `src/`: Initial C++ source files (`sort.hpp`, `sort_impl.hpp`, `benchmark.hpp`, `benchmark.cpp`) used as the starting point for evolution.
- `run_experiment.py`: The main script to run the evolution experiment.
- `evaluator.py`: Contains the client-side evaluation logic.

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
