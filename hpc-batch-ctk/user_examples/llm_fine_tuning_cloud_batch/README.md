# LLM Fine-Tuning LoRA Hyperparameter Optimization (Cloud Batch GPU Showcase)

This example demonstrates how to use the AlphaEvolve platform to perform hyperparameter optimization for Low-Rank Adaptation (LoRA) fine-tuning of **Gemma 4 E2B** (5.1B effective parameters with embeddings) on a function-calling dataset ([NousResearch/hermes-function-calling-v1](https://huggingface.co/datasets/NousResearch/hermes-function-calling-v1)).

By running this experiment in **Cloud Batch mode** (`evaluation_mode: batch`), AlphaEvolve automatically provisions ephemeral GPU worker VMs (such as NVIDIA L4 or A100 instances), executes candidate evaluations in parallel, and scales the compute cluster back to zero cost between generation cycles.

---

## What Gets Evolved

AlphaEvolve evolves the `get_training_config()` function inside `main.py`. The search explores four critical hyperparameter groups:

| Hyperparameter Group | Evolved Parameters | Search Impact |
| :--- | :--- | :--- |
| **LoRA Adapters** | `lora_r`, `lora_alpha`, `lora_dropout` | Balances adapter expressiveness against GPU VRAM overhead. |
| **Optimizer & LR** | `learning_rate`, `lr_scheduler_type`, `warmup_ratio`, `weight_decay`, `optim`, `max_grad_norm` | `learning_rate` is the single most impactful parameter governing convergence speed and stability. |
| **Batch & Sequence** | `per_device_train_batch_size`, `gradient_accumulation_steps`, `max_seq_length` | Governs effective batch size and memory consumption. |
| **Precision** | `bf16` | Mixed precision flag (kept `True`). |

> [!CAUTION]
> **GPU Memory Constraint**: The evaluation function strictly enforces `per_device_train_batch_size * max_seq_length <= 4096`. Candidates exceeding this threshold receive an automatic penalty (`neg_eval_loss = -100.0`) and emit structured OOM hazard insights back to Gemini to steer future generations away from memory crashes.

---

## Directory Structure

* `main.py`: Initial seed program containing `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` markers around `get_training_config()`, alongside the `evaluate()` entry point.
* `evaluator.py`: Cloud Batch worker interface. Reads `main.py`, executes evaluation logic, and returns structured scores (`neg_eval_loss`) and diagnostic insights using `alpha_evolve.models`.
* `run_experiment.py`: Controller initialization script defining the problem prompt, language, model selection, and concurrency settings.
* `Makefile`: Required for Cloud Batch mode. Generates the runtime `evaluator.sh` script executed inside worker containers.
* `evaluator.Dockerfile`: Container build definition. Extends core platform requirements and installs PyTorch (`cu121` wheel compiled for GCP Compute Engine CUDA 12.4 drivers), Transformers, PEFT, and TRL.
* `eval-batch.yaml`: Custom Cloud Batch topology override explicitly enabling `installGpuDrivers: true` and forwarding training environment variables to NVIDIA L4 (`g2-standard-8`) worker VMs.
* `cache-build.yaml`: Dedicated Cloud Build manifest to download and cache model weights and dataset shards directly into GCS.

---

## Step 1: Pre-Cache Model & Dataset via Cloud Build (One-Time Setup)

Before deploying the experiment container, submit the dedicated Cloud Build caching pipeline to download `google/gemma-4-E2B-it` and `NousResearch/hermes-function-calling-v1` from Hugging Face and permanently cache them inside your GCS bucket (`gs://alpha-evolve/model_cache/`). This allows ephemeral Cloud Batch worker VMs to load weights instantly from local disk without hitting Hugging Face authentication or internet bandwidth limits.

```bash
gcloud builds submit --config user_examples/llm_fine_tuning_cloud_batch/cache-build.yaml \
  --project=<YOUR_PROJECT_ID> \
  --substitutions=_BUCKET_NAME="alpha-evolve",_HF_TOKEN="hf_your_huggingface_token_here" \
  --no-source
```

---

## Step 2: Deployment & Configuration Guide

To deploy this GPU-accelerated experiment on your shared AlphaEvolve base infrastructure, run the following Cluster Toolkit (`gcluster`) deployment command from the **repository root directory**.

### Standard Command (NVIDIA L4 GPU via `g2-standard-8`)

```bash
gcluster deploy alpha-evolve-experiment.yaml -l IGNORE -d alpha-evolve-deployment.yaml -o ../deployment \
  --vars project_id=<YOUR_PROJECT_ID> \
  --vars region=<YOUR_REGION> \
  --vars existing_bucket_name=<YOUR_GCS_BUCKET> \
  --vars example_dir="user_examples/llm_fine_tuning_cloud_batch" \
  --vars user_experiment_name="llm-lora-gpu" \
  --vars evaluation_mode="batch" \
  --vars evaluation_machine_type="g2-standard-8" \
  --vars evaluation_provisioning_model="SPOT" \
  --vars concurrency=4 \
  --vars max_programs_generated=50 \
  --vars max_programs_evaluated=20 \
  -w --auto-approve
```

### Configurable Deployment Variables (`--vars`)

When customizing your hardware shape or execution flow, pass any of the following overrides to `gcluster deploy`:

| Variable | Recommended Value | Description |
| :--- | :--- | :--- |
| `example_dir` | `"user_examples/llm_fine_tuning_cloud_batch"` | Target directory containing this experiment package. |
| `user_experiment_name` | `"llm-lora-gpu"` | Unique name isolating container registries, GCS storage paths, and Cloud Batch job names. |
| `evaluation_mode` | `"batch"` | Must be set to `batch` to dispatch evaluations to Google Cloud Batch VMs. |
| `evaluation_machine_type` | `"g2-standard-8"` | Compute engine machine shape. Use `g2-standard-8` (1x NVIDIA L4 24GB) or `a2-highgpu-1g` (1x NVIDIA A100 40GB) for native GPU shapes. |
| `evaluation_provisioning_model` | `"SPOT"` | Use `SPOT` for up to 60-90% cost savings on batch GPU evaluations, or `STANDARD` for guaranteed execution. |
| `concurrency` | `4` | Number of parallel Cloud Batch evaluation VMs spawned simultaneously per generation. |
| `max_programs_generated` | `50` | Total budget of candidate programs generated by Gemini. |
| `max_programs_evaluated` | `20` | Total number of Cloud Batch evaluations executed before pausing. |
| `max_duration_seconds` | `3600` | Maximum timeout per evaluation job (1 hour). |
| `delete_succeeded_jobs` | `"true"` | Set to `"false"` during debugging if you want worker VMs and Cloud Logging traces preserved after completion. |

### Attaching GPUs to General Purpose VMs (`n1` family)

If your quota requires attaching standalone GPUs to general purpose instances (e.g., attaching NVIDIA T4 or L4 GPUs to `n1-standard-8` nodes), pass the accelerator flags:

```bash
  --vars evaluation_machine_type="n1-standard-8" \
  --vars accelerator_count=1 \
  --vars accelerator_type="nvidia-tesla-t4"
```

### Activating Real GPU Training (`REAL_TRAINING_ENABLED`)

This showcase container comes preconfigured with `ENV REAL_TRAINING_ENABLED=true` inside `evaluator.Dockerfile`. When Cloud Batch boots worker tasks on GPU VMs (`g2-standard-8`), real PyTorch LoRA forward/backward training passes execute automatically and extract actual loss metrics from `SFTTrainer` log history.

#### Toggling Between GPU and CPU Execution
Because `eval-batch.yaml` includes `options: "--gpus all"`, Docker requires host NVIDIA devices at container boot.
* **For GPU Runs (`g2`, `a2`, `n1`+GPU)**: Keep `eval-batch.yaml` exactly as configured.
* **For CPU Runs (`n2`, `e2`)**: If you want to verify pipelines cheaply on CPU instances, comment out or remove `options: "--gpus all"` and `installGpuDrivers: true` inside `eval-batch.yaml`. The container will boot cleanly on CPU, detect missing CUDA, and evaluate candidate configs via our rapid empirical surrogate loss model.

---

## Running the Experiment in Colab Enterprise

After deploying the experiment container:
1. Open your shared Jupyter Notebook (`run_notebook.ipynb`) in Vertex AI Colab Enterprise.
2. Run the interactive discovery cell under **Adjust environment variables on the Notebook**.
3. Select `'llm-lora-gpu'` from the prompt menu to load all GCS metadata and environment settings.
4. Execute the controller run cell to launch the autonomous evolutionary optimization loop!
