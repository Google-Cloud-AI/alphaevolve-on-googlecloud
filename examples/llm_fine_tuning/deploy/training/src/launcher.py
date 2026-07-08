# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Ray TorchTrainer orchestration.

Follows the same pattern as docs/raygemma4/src/launcher.py.
Manages the lifecycle of Ray runtime and TorchTrainer for training jobs.
"""

import logging
import math
import os
from typing import Any, Dict

import ray
from ray.train import CheckpointConfig, RunConfig, ScalingConfig
from ray.train.torch import TorchTrainer

from src.model import get_model_source, load_tokenizer, save_merged_model
from src.sft import train_func as sft_train_func

logger = logging.getLogger(__name__)


def build_scaling_config(config: dict) -> ScalingConfig:
    """Build Ray ScalingConfig from training config.

    Currently single-worker (1 GPU). To scale to multi-GPU:
      - Set num_workers > 1
      - Add DeepSpeed config to training args
      - Scale RayCluster worker replicas
    """
    num_workers = config.get("num_workers", 1)
    return ScalingConfig(
        num_workers=num_workers,
        use_gpu=True,
        resources_per_worker={"GPU": 1},
    )


def get_train_func(config: dict):
    """Return the appropriate training function based on task type.

    Currently only SFT is supported. To add DPO:
      1. Create src/dpo.py with a train_func(config) function
      2. Route here based on config.get("task") == "preference_tuning"
    """
    return sft_train_func


def run_training(config: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """Launch training via Ray TorchTrainer and return metrics.

    1. Initializes local Ray runtime
    2. Creates TorchTrainer with SFT training function
    3. Runs training, reads metrics from worker output
    4. Shuts down Ray and returns metrics dict for AlphaEvolve scoring

    Model merging is handled separately by merge_adapter() — call it
    after writing metrics to GCS so results are available even if the
    merge is slow or fails.
    """
    artifacts_path = os.environ.get("ARTIFACTS_PATH", "/mnt/artifacts")
    model_source = get_model_source()
    logger.info(f"Model source: {model_source}")

    train_config = {
        "job_id": job_id,
        "model_source": model_source,
        "hyperparams": config,
    }

    logger.info("Initializing Ray runtime")
    ray.init(ignore_reinit_error=True)

    try:
        train_func = get_train_func(config)
        scaling_config = build_scaling_config(config)

        ray_trainer = TorchTrainer(
            train_func,
            train_loop_config=train_config,
            scaling_config=scaling_config,
            run_config=RunConfig(
                name=f"training-{job_id}",
                storage_path=os.path.join(artifacts_path, "ray_results"),
                checkpoint_config=CheckpointConfig(
                    num_to_keep=1,
                    checkpoint_score_attribute="eval_loss",
                    checkpoint_score_order="min",
                ),
            ),
        )

        logger.info(
            f"Launching Ray TorchTrainer "
            f"({scaling_config.num_workers} worker(s), GPU)"
        )
        result = ray_trainer.fit()
        logger.info("Ray training complete")

        # Read metrics from Ray result — populated by RayTrainReportCallback
        # because checkpoints are enabled (save_strategy="steps").
        raw_metrics = result.metrics or {}
        logger.info(f"Raw metrics from Ray result: {raw_metrics}")

        eval_loss = raw_metrics.get(
            "eval_loss", float("inf")
        )
        train_loss = raw_metrics.get(
            "loss", raw_metrics.get("train_loss", float("inf"))
        )
        eval_perplexity = (
            math.exp(eval_loss) if eval_loss < 100 else float("inf")
        )

        metrics = {
            "neg_eval_loss": -eval_loss,
            "eval_perplexity": eval_perplexity,
            "train_loss": train_loss,
        }
        logger.info(f"Computed metrics: {metrics}")

    finally:
        ray.shutdown()
        logger.info("Ray runtime shut down")

    return metrics


def merge_adapter(job_id: str) -> str | None:
    """Best-effort merge of LoRA adapter into base model.

    Loads the base model on CPU (after Ray shutdown frees GPU memory),
    merges the LoRA adapter from the latest checkpoint, and saves the
    full merged model. Returns the local path on success, None on failure.
    """
    artifacts_bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    artifacts_path = os.environ.get("ARTIFACTS_PATH", "/mnt/artifacts")
    model_source = get_model_source()

    results_dir = os.path.join(artifacts_path, "ray_results", f"training-{job_id}")
    if not os.path.isdir(results_dir):
        logger.warning(f"Results dir not found: {results_dir} — skipping merge")
        return None

    # Find the latest checkpoint directory
    checkpoint_dirs = sorted(
        [d for d in os.listdir(results_dir) if d.startswith("checkpoint_")],
    )
    if not checkpoint_dirs:
        logger.warning("No checkpoint available — skipping model merge")
        return None

    adapter_path = os.path.join(results_dir, checkpoint_dirs[-1], "checkpoint")
    if not os.path.isdir(adapter_path):
        logger.warning(f"Adapter path not found: {adapter_path}")
        return None

    try:
        logger.info(f"Loading adapter from checkpoint: {adapter_path}")
        tokenizer = load_tokenizer(model_source)
        merged_path = os.path.join(
            artifacts_path, "jobs", job_id, "merged_model"
        )
        save_merged_model(
            model_source, adapter_path, tokenizer, merged_path
        )
        logger.info(f"Merged model saved to {merged_path}")
        return f"gs://{artifacts_bucket}/jobs/{job_id}/merged_model"
    except Exception as e:
        logger.warning(f"Merged model save failed (non-fatal): {e}")
        return None
