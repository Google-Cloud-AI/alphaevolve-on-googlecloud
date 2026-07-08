# AlphaEvolve on Cloud - Technical Assets

## Overview

AlphaEvolve (AE) is an evolutionary coding agent designed for general-purpose algorithm discovery and optimization. This repository provides the technical assets—including code examples and specialized tools—necessary for customers to evaluate and implement AlphaEvolve within their Google Cloud Platform (GCP) environments.

## Repository Structure

The assets are organized into the following directories to support your implementation journey:

*   **`/examples/`**:

    The AlphaEvolve repository contains the **client-side Python library** (in `src/alpha_evolve/`) and **example experiments** (in `examples/`). Make sure to review each example's `README` before getting started. The following examples have been curated for your exploration.

    *   **Getting Started: Combinatorial Optimization (Circle Packing / TSP, L100)**: Evolve a pure-Python heuristic, packing circles into a unit square or finding the shortest TSP tour, using local `exec()` evaluation with zero cloud infrastructure. Learn the core loop: seed program → EVOLVE-BLOCK markers → evaluator → controller, and watch Gemini iteratively beat the nearest-neighbor baseline.
    *   **Multi-Objective Evaluation: Signal Processing (L200)**: Evolve an adaptive time-series filter judged on 14+ competing metrics (smoothness, lag, false reversals, noise reduction) across 5 non-stationary test signals. Learn how to design weighted composite objectives, return structured insights so the LLM can self-correct, and protect evaluators with timeouts — all still running locally.
    *   **Remote Evaluation at Scale: Kaggle ML Pipeline (L200)**: Evolve a complete scikit-learn pipeline (feature engineering + model selection) for a tabular Kaggle competition, with candidates scored by a containerized evaluator on Cloud Run. Learn the remote-eval pattern: Dockerfile, `cloudbuild.yaml`, Terraform-provisioned Artifact Registry/IAM, and how EvaluationWorkers fan out HTTP requests concurrently.
    *   **Production GPU Infrastructure: LLM Fine-Tuning (L300)**: Evolve LoRA hyperparameters for Gemma 4 on a function-calling dataset, with each candidate trained on autoscaling L4 GPUs via a persistent RayCluster on GKE — orchestrated by a gateway service, fed by GCS FUSE, and observed through Ray Dashboard + Prometheus/Grafana. Learn how to wire AlphaEvolve into real training infra with cost controls and full observability.

*   **`/skills/`**:

    Specialized AlphaEvolve skills for experiment design, execution, and analysis. *(Coming soon.)*

## Getting Started

Before executing experiments, ensure your environment is correctly provisioned by following the [AlphaEvolve on Cloud Get Started](https://docs.cloud.google.com/gemini/enterprise/docs/co-scientist-and-alphaevolve) guide.

## Support

For technical issues, release-specific questions, or to provide feedback, please contact your assigned Google Cloud account team
