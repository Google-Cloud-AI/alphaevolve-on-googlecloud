# How to Create a New Experiment

## Introduction

This document describes how to create a new experiment for your own optimization problems using the Cluster Toolkit powered AlphaEvolve Solution.

### Assumptions

* We assume that you have understood the best practices for the usage of AlphaEvolve as described in the Best Practices guide provided as part of the package delivered for the private preview.

* We assume that you have acquainted yourself with the basic usage of the AlphaEvolve Solution (see [README.md](README.md)) and are familiar with the general concepts of the AlphaEvolve solution, i.e. there is a base infrastructure that you can reuse for multiple experiments, a software environment step that builds a Docker image for a given experiment, and the Jupyter Notebook that is set up as part of the base infrastructure from where you control the experiment flow.


### Highlevel View

Here is a high-level overview of the project structure and what you should expect to modify:

```text
.
├── alpha-evolve-deployment.yaml <-- [EDITABLE] Shared deployment defaults and variables overrides.
├── alpha-evolve-experiment.yaml <-- [EDITABLE] Blueprint for experiment / software environment execution.
├── alpha-evolve-infra.yaml      <-- [EDITABLE] Blueprint for base infrastructure deployment.
├── google_framework/      <-- [DO NOT MODIFY] Core framework code (controller, workers, clients).
├── infrastructure/        <-- [DO NOT MODIFY] Terraform and build configurations.
├── user_examples/          <-- [EDITABLE] Place your custom experiments here!
│   ├── circle_packing_cloud_batch/
│   ├── llm_fine_tuning_cloud_batch/
│   ├── airfoil_optimization/
│   └── ...
├── README.md                  <-- Overview and getting started guide
├── AGENT.md                   <-- Detailed guide for developers and agents.
└── CREATE_EXPERIMENT.md       <-- This file.
```

> [IMPORTANT]
> It is not intended for you to modify `infrastructure/build/controller.Dockerfile` or any code inside the core infrastructure platforms (`infrastructure/` or `google_framework/`). Your changes should reside entirely inside your `user_examples/<your_experiment>` directory.


### Custom Deployment Variables

The AlphaEvolve deployment configurations are divided across different files in the root directory. Common overrides are defined inside `alpha-evolve-deployment.yaml`, while base infrastructure configuration settings reside in `alpha-evolve-infra.yaml`, and specific experiment parameters are defined in `alpha-evolve-experiment.yaml`.

Here are the most important variables and their locations:

| Variable | Config File Location | Default / Example | Required | Description |
|---|---|---|---|---|
| `project_id` | `alpha-evolve-deployment.yaml` | `## SET GCP PROJECT ID HERE ##` | Yes | GCP Project ID where resources are deployed. |
| `existing_bucket_name` | `alpha-evolve-deployment.yaml` | `"alpha-evolve-existing-bucket"` | Yes | The name of the GCS bucket to use for storing experiment data. |
| `exp_deployment_name` | `alpha-evolve-experiment.yaml` | `alpha-evolve-experiment` | No | Combines with `user_experiment_name` to determine the Artifact Registry repository name and the Cloud Batch jobs namespace. |
| `user_experiment_name` | `alpha-evolve-experiment.yaml` | `experiment-1` | No | Combines with `exp_deployment_name` to determine the Artifact Registry repository name and the Cloud Batch jobs namespace. See **[Managing Multiple Experiments on the same Base Infrastructure](#managing-multiple-experiments-on-the-same-base-infrastructure)** for additional details. |
| `example_dir` | `alpha-evolve-experiment.yaml` | `user_examples/<your_experiment>` | Yes | The workspace repository path of the custom experiment you want to simulate and evaluate. |
| `model` | `alpha-evolve-experiment.yaml` | `GEMINI_V2P5_FLASH` | No | The generation model to use. You can provide standard model name strings (e.g., `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3-flash-preview`, `gemini-3.1-pro-preview`, `gemini-3.5-flash`) or legacy uppercase enum names (`GEMINI_V2P5_FLASH`). Defaults to `gemini-2.5-flash` if unspecified. You can also specify a weighted mixture of up to two models separated by a semicolon (e.g., `--vars="model=gemini-3-flash-preview:0.6;gemini-3.1-pro-preview:0.4"`). Weights must be between 0 and 1, are relative, and are normalized server-side. Note: Certain models like `gemini-3.1-pro-preview` are designated as capped models by the API backend and cannot exceed 50% of the total mixture weight (i.e. they must be paired with another model such that their relative share is $\le 0.5$). |
| `evaluation_machine_type` | `alpha-evolve-experiment.yaml` | `n2-standard-4` | No | Custom VM evaluator machine type for batch mode. |
| `evaluation_provisioning_model` | `alpha-evolve-experiment.yaml` | `SPOT` | No | Custom VM evaluator provisioning model for batch mode. Possible values are `SPOT`, `STANDARD`, and `FLEX_START` (Dynamic Workload Scheduler Flex Start, supported for GPU accelerator-enabled VMs and H4D HPC instances).|
| `evaluation_mode` | `alpha-evolve-experiment.yaml` | `batch` | No | The mode to run the experiment in. The only supported value is `batch` (evaluations are executed on Google Cloud Batch worker VMs).|
| `max_duration` | `alpha-evolve-experiment.yaml` | `6` | No | Absolute maximum wall-clock lifespan of the experiment run in hours (valid range: 1 to 24, default: 6). |
| `idle_timeout` | `alpha-evolve-experiment.yaml` | `5` | No | Maximum inactivity period allowed in hours before the experiment is automatically paused (must be strictly less than `max_duration`, default: 5). |

For a full list of configurable deployment variables, see the **[Agent Guide](AGENT.md)**.


### Organize your own experiment

When creating a custom optimization problem, organize your code inside `user_examples/<your_experiment>` following this file tree layout:

```text
user_examples/<your_experiment>/
├── main.py / main.cpp        # The core implementation to optimize
├── run_experiment.py         # Framework initialization & run
├── evaluator.py              # Python interface providing candidate scoring
├── Makefile                  # Evaluation directory builds entry scripts and compiles code returned from AE if needed
├── evaluator.Dockerfile      # Needed for evaluation on batch
├── eval-batch.yaml           # Optional: Custom Cloud Batch job config override (e.g. for MPI/multi-node synchronization)
├── setup.sh                  # Optional: Additional setup script (e.g., install custom linux packages)
└── requirements.txt          # Optional: Additional Python packages (e.g., custom python packages)
```

## Implementation

### Implementation Setup Step-by-Step

1.  **Create a directory** under `user_examples/` for your experiment (e.g., `user_examples/my_custom_exp`).
2.  **Define your initial program**: Create the file you want to optimize (e.g., `main.py` or `main.cpp`).
3.  **Add Markers**: Wrap the specific lines of code you want AlphaEvolve to optimize with `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` (use `//` for C++). The markers must be on their own lines starting at column 0. Multiple separate `EVOLVE-BLOCK` sections are supported per file to optimize non-contiguous parts of the codebase.
4.  **Implement `evaluator.py`**: Write a Python script that returns a score for the generated candidates. Use the models from `alpha_evolve.models` to return structured results. On failure, populate `insights` with deep contextual instructions for the generating agent.
5.  **Implement `run_experiment.py`**: Write the script that initializes the experiment and calls the controller. 
6.  **Add Makefile and evaluator.Dockerfile**: Both files are required for Cloud Batch mode. Even if your experiment does not require compilation, a `Makefile` is required to generate the `evaluator.sh` script, and the `evaluator.Dockerfile` is needed to build the container image. 
    *   **Note on Makefile**: The `Makefile` is not executed during the Docker image build. Instead, it runs at runtime as part of the task entry point in the evaluation directory (i.e., when evaluating candidates in Cloud Batch mode). Ensure your `Makefile` includes rules to compile any generated candidate code if your experiment requires it.
    *   **Note on evaluator.Dockerfile**: Make sure to customize the base image inside the `evaluator.Dockerfile` to match your experiment's runtime dependencies setup.
7.  **Add an optional `setup.sh`** if other Linux packages need to be installed for your custom environment.
8.  **Add an optional `requirements.txt`** if extra Python packages are needed to be included for your custom environment.
9.  **Update your `evaluator.Dockerfile`** to copy these files into the container and run/install these packages at build time if they exist. (Note: Ensure `evaluator.Dockerfile` installs `infrastructure/requirements.txt` with `--require-hashes`, but installs your custom experiment `requirements.txt` without `--require-hashes`).
10. **Add an optional `eval-batch.yaml`** if your experiment requires a custom Cloud Batch job topology (e.g., multi-node VM synchronization, passwordless SSH between worker nodes, and custom task count overrides for distributed MPI architectures) instead of using the default single-node template.

### How to Safely Start and Test Your Experiment

> **IMPORTANT**
> * Make sure you are executing all commands from the directory containing this README file.
> * Always complete the platform infrastructure deployment (see `README.md`) first to ensure Artifact Registries and storage paths are provisioned.
> * Do not omit the dot `.` at the end of the Docker build command. The `.` denotes the current directory as the build context and is required.

#### Local Sanity Check with Initial Seed Program

To verify that your evaluator container builds correctly, entrypoint hooks operate without errors, and your evaluation method scores your initial seed program properly without deploying to GCP, you can simulate a Cloud Batch evaluation task locally:

1. **Prepare a local test directory structure** in your workspace root:
   ```bash
   mkdir -p local_test_workspace/<YOUR_EXPERIMENT_NAME>/program_candidates/test-job
   ```

2. **Create dummy candidate metadata** named `program_candidate_data.json` inside the leaf directory. This provides the minimal metadata required by the batch worker:
   ```json
   {
     "name": "alphaEvolvePrograms/seed-candidate",
     "lockToken": "dummy-token"
   }
   ```

3. **Copy your initial seed program**: Copy your experiment's initial seed code (e.g., `main.py`, `main.cpp`, and any supporting helper files or headers defined in your initial program) into the same directory:
   ```bash
   cp user_examples/<your_experiment>/main.py local_test_workspace/<YOUR_EXPERIMENT_NAME>/program_candidates/test-job/
   # Note: If your seed program relies on additional modules or headers (e.g., src/*.hpp), copy those preserving their relative paths as well!
   ```

4. **Build the evaluator container** from the repository root:
   ```bash
   docker build -t test-evaluator -f user_examples/<your_experiment>/evaluator.Dockerfile .
   ```

5. **Run the evaluator container with volume mounts**:
   Mount the local test workspace and set the environment variables to point to it:
   ```bash
   docker run -it --rm \
     -v $(pwd)/local_test_workspace:/mnt/disks/share \
     -e _CLOUD_BUCKET_NAME=dummy-bucket \
     -e _USER_EXPERIMENT_NAME=<YOUR_EXPERIMENT_NAME> \
     -e _PROJECT_ID=dummy-project \
     -e _JOB_ID="test-job" \
     -e _PROGRAMS_DIR="program_candidates" \
     -e _MOUNT_PATH="/mnt/disks/share" \
     -e _CANDIDATE_DIR="/mnt/disks/share/<YOUR_EXPERIMENT_NAME>/program_candidates/test-job" \
     -e _CANDIDATE_PROGRAM_ID="seed-candidate" \
     -e _CLIENT_EVALUATOR_SCRIPT="evaluator" \
     -e _CLIENT_EVALUATOR_METHOD="<YOUR_EVALUATION_FUNCTION_NAME>" \
     test-evaluator
   ```
   > **TIP**
   > * If your Python script has a different filename than `evaluator.py`, or if your candidate scoring entry point method is not called `evaluate`, modify the `_CLIENT_EVALUATOR_SCRIPT` and `_CLIENT_EVALUATOR_METHOD` flags in the command above to match your file and function names.

On a successful run, the container will execute your evaluator logic against your seed program and write the results to `local_test_workspace/<YOUR_EXPERIMENT_NAME>/program_candidates/test-job/program_candidate_result.json`. You can inspect this file to verify that your seed program's initial score and insights are computed as expected.

On a successful sanity check run with your seed program, the output traces will resemble this:

```text
[BATCH DEBUG] Container started for Program ID: seed-candidate
[BATCH DEBUG] Found Makefile under directory: /app/experiment
[BATCH DEBUG] Copying generated code from /mnt/disks/share/demo/program_candidates/test-job to /app/experiment...
[BATCH DEBUG] Building C++ library from /app/experiment...
make: Entering directory '/app/experiment'
g++ -std=c++11 -fPIC -O2 -Wall -c libpacking.cpp -o libpacking.o
g++ -shared -o libpacking.so libpacking.o
echo "#!/bin/bash" > evaluator.sh
echo "cd /app/experiment" >> evaluator.sh
echo "mkdir -p \$_MOUNT_PATH/\$_USER_EXPERIMENT_NAME/logs" >> evaluator.sh
echo 'python3 /app/src/alpha_evolve/cloud_evaluator.py 2>&1 | tee $_MOUNT_PATH/$_USER_EXPERIMENT_NAME/logs/evaluator_$_CANDIDATE_PROGRAM_ID.log' >> evaluator.sh
chmod +x evaluator.sh
make: Leaving directory '/app/experiment'
[BATCH DEBUG] Build finished.
[BATCH DEBUG] Running evaluator...
[Evaluator test-job] INFO: Successfully loaded evaluator 'circle_packing_evaluation' from module 'evaluator'
[Evaluator test-job] INFO: Worker started.
[Evaluator test-job] INFO: Attempting to pull candidate program from /mnt/disks/share/demo/program_candidates/test-job/program_candidate_data.json...
[Evaluator test-job] INFO: Successfully loaded program_candidate: candidate-1 (ID: seed-candidate)
[Evaluator test-job] INFO: Evaluating program seed-candidate...
[Evaluator test-job] INFO: STARTING EVALUATION: candidate-1
[Evaluator test-job] INFO: CODE LENGTH: 5025
Loading and configuring libpacking.so
Success loading and configuring libpacking.so
[Evaluator test-job] INFO: Evaling done for seed-candidate: {'scores': {'scores': [{'metric': 'sum_of_radii', 'score': None}]}, 'insights': {'insights': [{'label': 'Invalid Score', 'text': 'The evaluation function returned an invalid score (-infinity or None), suggesting the packing constraints were not met.'}]}}
[Evaluator test-job] INFO: Result for seed-candidate successfully written to /mnt/disks/share/demo/program_candidates/test-job/program_candidate_result.json.
[Evaluator test-job] INFO: Worker finished.
```

#### End-to-End Local Dry Run (Evaluator + Controller Containers)

To verify schema compatibility and data communication between your actual **Evaluator Container** and **Controller Container** locally without calling the external AlphaEvolve API or consuming Cloud Batch quota, you can link them together using a shared Docker volume and the provided verification utility:

1. **Build both actual containers** from the repository root:
   ```bash
   docker build -t test-evaluator -f user_examples/<your_experiment>/evaluator.Dockerfile .
   docker build -t test-controller --build-arg EXAMPLE_DIR="user_examples/<your_experiment>" -f infrastructure/build/controller.Dockerfile .
   ```

2. **Run Step 1 to Step 5 of the Initial Seed Program check above** using `test-evaluator` so that `program_candidate_result.json` is generated inside `local_test_workspace/<YOUR_EXPERIMENT_NAME>/program_candidates/test-job/`.

3. **Run the Controller Container with the shared volume and verification script**:
   Mount your local workspace and `tools/` directory, then execute `tools/test_container_communication.py`:
   ```bash
   docker run --rm --entrypoint python3 \
     -v $(pwd)/local_test_workspace:/mnt/disks/share \
     -v $(pwd)/tools:/app/tools \
     -e _USER_EXPERIMENT_NAME=<YOUR_EXPERIMENT_NAME> \
     test-controller /app/tools/test_container_communication.py
   ```

On a successful run, the controller container will ingest the JSON file written by the evaluator container, validate its Pydantic schema structure against `AlphaEvolveExperiment.submit_program_evaluations`, and confirm 100% data compatibility offline without making any network calls to the AlphaEvolve API.

> **Where to Find Local Dry Run Logs**:
> * **Evaluator Container Logs**: Written automatically to your host filesystem at `local_test_workspace/<YOUR_EXPERIMENT_NAME>/logs/evaluator_seed-candidate.log` (or `evaluator_<ID>.log`). The resulting evaluation JSON is stored at `local_test_workspace/<YOUR_EXPERIMENT_NAME>/program_candidates/test-job/program_candidate_result.json`.
> * **Controller Container Logs**: Streamed directly to your terminal standard output (`stdout`) when executing the verification script above. To save these controller logs to a file on your host machine, append `2>&1 | tee local_test_workspace/<YOUR_EXPERIMENT_NAME>/logs/controller_verification.log` to the `docker run` command.

## Managing Multiple Experiments on the Same Base Infrastructure

To manage and run multiple distinct experiments or different versions of the same experiment on the shared base infrastructure:

1.  **Deploy Each Experiment Separately**: When you run `gcluster deploy experiment` for each of your custom experiments (located under `user_examples/<your_experiment>`), ensure you use a unique `--vars user_experiment_name=<YOUR_EXPERIMENT_NAME>` flag. This isolates each experiment's environment and artifacts.

2.  **Capture Deployment Output**: After a successful `gcluster deploy` command, the output will notify you that your experiment configuration has been natively saved to GCS and registered in GCP project metadata:

    ```text
    [...]
    ==== How to run your experiment in the Notebook ====
    All configurations have been natively saved to GCS under: gs://<bucket_name>/<user_experiment_name>/
    
    Please open the Jupyter Notebook and follow these steps under the 'Show how change experiment run' section:
    
    1. Go to the section: 'Adjust environment variables on the Notebook'.
    2. Run the interactive cell: 'Run this cell to specify the experiment...'.
    3. Select the option corresponding to: '<user_experiment_name>'.
       This will dynamically load all of your GCS environment variables!
    ```

3.  **Configure Jupyter Notebook**: Open your Jupyter Notebook and navigate to the `Select and Load Deployed Experiment Variables` section. Run the interactive discovery cell. The notebook will automatically query GCP project metadata to list all deployed experiments. Enter the number corresponding to your newly deployed experiment, and the notebook will dynamically load all necessary environment variables for that session from GCS!

4.  **Running Experiments Simultaneously**: Because each deployed experiment has an isolated GCS storage path (`gs://<bucket_name>/<user_experiment_name>/`), dedicated Cloud Batch job namespace, and scope-filtered Pub/Sub notifications, you can run multiple experiments **simultaneously / concurrently** on the same shared base infrastructure. Simply open multiple Colab Enterprise notebook tabs or sessions, select a different deployed experiment in each tab, and execute their controller loops concurrently without interference.


## Tips for Hardware & Scalability
*   **Choosing the Right VM Evaluator**: Depending on your evaluators' runtime demand, you can customize the evaluator's machine type via the `gcluster deploy` command by appending `--vars machine_type=<type>` during project setup. Choose a machine type tailored to your evaluation workload:
    *   For simple tasks: Choose general purpose instances (e.g., `n1-standard-4`, `n2-standard-4`, or larger shapes).
    *   For simple memory-demanding tasks: Choose high-memory instances (e.g., `n2-highmem-4`) or larger shapes.
    *   For more complex tasks: Choose compute-optimized instances (e.g., `c2` or `c2d`).
    *   For compute and memory intensive tasks: Choose HPC instances (e.g., `h4d` or `h3`) - whole shapes only.
    *   For GPU-accelerated tasks: Choose GPU instances (e.g., `g2-standard-8`, `a2-highgpu-1g`, or general purpose instances like `n1-standard-8` with standalone GPUs attached via `--vars accelerator_type="..."`).
    *   **Provisioning Model Notes**: For GPU accelerator-enabled VMs and `h4d` HPC instances, you can use the `FLEX_START` provisioning model (`--vars evaluation_provisioning_model=FLEX_START`) for cost-effective dynamic workload scheduling.
    
    **Workspace Isolation & Versioning**: Logs, model artifacts, and generated states are isolated inside your GCS bucket underneath `gs://<bucket-name>/<user_experiment_name>/`.
    *   *Multiple Container Configurations*: You can test different evaluator container base images (e.g., CPU vs GPU setups) by deploying them with unique `user_experiment_name` definitions.  Refer to the `README.md` for step-by-step instructions on rebuilding these isolated Docker containers.
    *   *Switching Job Targeting via Notebook*: Dynamically target alternate evaluator images during testing iterations. To switch target workloads, simply re-run the interactive discovery cell in your Jupyter Notebook and select the number corresponding to the desired experiment from the prompt list.

    For full details matching infrastructure workloads, see the [Google Cloud Compute Resource guidelines](https://docs.cloud.google.com/compute/docs/machine-resource).


## Troubleshooting & Logs

If something goes wrong or you are getting invalid scores, check the following logs:

*   **Experiment and Controller Workspace (Batch mode)**: Go to the Google Cloud Console -> **Cloud Batch**. Select the controller job to inspect standard execution insights and progress metrics inside Cloud Logging. 
*   **Cloud Batch Worker logs**: For Cloud Batch evaluations, container execution logs are available in Cloud Logging by finding the Cloud Batch Job resource in your Google Cloud Console. Many examples also direct evaluation scripts to record output files into a `logs/` directory inside the program workspace, which can be viewed directly from the Jupyter Notebook under the `data/` directory. 
*   **Failure Diagnosis**: If evaluation jobs fail, the cause is typically one of the following:
    *   **Generated Code Failure**: Most of the time, the failure is related to the fact that the program created by AlphaEvolve failed (e.g., compilation errors or runtime errors).
    *   **Infrastructure/Container Issues**: There could also be infrastructure issues if the evaluator container artifact does not exist in the Artifact Registry or did not build properly during VM creation. 
    
    Check the worker logs in Cloud Logging for specific error messages. Note that if an experiment encounters an unrecoverable failure and enters a `FAILED` state, the platform automatically deletes the `current_experiment.json` state file from GCS so that re-running the controller will initiate a fresh restart without getting stuck in a failed state.
*   **Inspecting Results and Artifacts**: All candidate code files and corresponding evaluation results are stored in the GCS bucket under the `archive/` path. You can also view and access these files directly from the Jupyter notebook workspace by checking the `data/` directory.
*   **GCS Bucket Structure**: Understanding the directory structure in your GCS bucket:
    *   `user-experiment-name/program_candidates`: This is the active working directory where candidates are placed during generation and evaluation.
    *   `user-experiment-name/archive/program_candidates`: This is the historical archive where completed candidates and their evaluation results are moved after processing. 
*   **Retaining Job Logs**: By default, successful Cloud Batch jobs are deleted. To prevent them from being cleaned up so you can inspect machine states or validation logs, run your deployment with the `delete_succeeded_jobs` variable set to false: `gcluster deploy ... --vars delete_succeeded_jobs=false`.

For a detailed walkthrough, code templates, and a full technical checklist, please refer to the **[Agent Guide](AGENT.md)**.


## Using an AI Agent to Create Your Experiment

If you want to use an AI Agent to help you create a new experiment or adapt your code to the AlphaEvolve framework, read the [AGENT.md](AGENT.md) file and use it to guide the agent.

Here is a suggested prompt you can give to the Agent:

> "I want to create a new experiment for the AlphaEvolve platform to support my own use case. Here is my program that I want to optimize:
> 
> ```[Paste LANGUAGE here]
> [Paste your initial code here]
> ```
> 
> **Problem Description**: [Describe what the code does and what needs to be optimized]
> **Evaluation Metric**: [Describe how to score the candidates, e.g., execution time, accuracy, or a specific formula]
> 
> Please read the `AGENT.md` guide in the repository and help me:
> 1. Identify the code block to optimize and add `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` markers.
> 2. Create the `evaluator.py` script to score candidates based on the metric.
> 3. Create the `run_experiment.py` script to initialize the experiment with the problem description and metric.
> 4. Guide me on implementing a `Makefile` to generate the runtime scripts and compile my candidate files if applicable. 
> 5. Guide me on implementing an `evaluator.Dockerfile` to configure the base container image and install external package requirements. 
> 6. Guide me on creating a `setup.sh` if other Linux packages need to be installed for my custom environment.
> 7. Guide me on creating a `requirements.txt` if other Python packages need to be installed for my custom environment.
