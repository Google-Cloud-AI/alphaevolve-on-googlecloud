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
"""Entry point for GKE batch training jobs.

Usage: python -m src --job-id <job_id>

Reads evolved hyperparameters from GCS, runs LoRA fine-tuning via Ray
TorchTrainer, and writes evaluation metrics back to GCS.
"""

import argparse
import logging
import os
import sys

import torch

from src.config import extract_config, validate_config
from src.launcher import merge_adapter, run_training
from src.utils import read_input, write_output

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main():
    parser = argparse.ArgumentParser(
        description="AlphaEvolve LLM fine-tuning training job"
    )
    parser.add_argument(
        "--job-id",
        type=str,
        default=os.environ.get("JOB_ID", ""),
        help="Job ID (also read from JOB_ID env var)",
    )
    args = parser.parse_args()

    job_id = args.job_id
    artifacts_bucket = os.environ.get("ARTIFACTS_BUCKET", "")

    if not job_id:
        logger.error("--job-id or JOB_ID environment variable is required.")
        sys.exit(1)
    if not artifacts_bucket:
        logger.error("ARTIFACTS_BUCKET environment variable is required.")
        sys.exit(1)

    logger.info(f"Starting training job: {job_id}")
    logger.info(f"Artifacts bucket: {artifacts_bucket}")
    if torch.cuda.is_available():
        logger.info(f"CUDA device: {torch.cuda.get_device_name(0)}")
    else:
        logger.warning("No CUDA device available — training will fail")

    # Step 1: Read input
    try:
        input_data = read_input(artifacts_bucket, job_id)
        logger.info(
            f"Input read — {len(input_data.get('files', []))} file(s)"
        )
    except Exception as e:
        logger.error(f"Failed to read input from GCS: {e}", exc_info=True)
        write_output(artifacts_bucket, job_id, {
            "metrics": {"neg_eval_loss": -100.0},
            "insights": {"insights": [
                {"label": "Input Error",
                 "text": f"Failed to read input: {e}"}
            ]},
        })
        sys.exit(1)

    files = input_data.get("files", [])

    # Step 2: Extract config
    try:
        config = extract_config(files)
        logger.info(f"Extracted config: {config}")
    except Exception as e:
        logger.error(f"Config extraction failed: {e}", exc_info=True)
        write_output(artifacts_bucket, job_id, {
            "metrics": {"neg_eval_loss": -100.0},
            "insights": {"insights": [
                {"label": "Evaluation Error",
                 "text": f"Failed to extract config: {e}. "
                         f"Ensure get_training_config() returns a valid dict."}
            ]},
        })
        return

    # Step 3: Validate config
    try:
        config = validate_config(config)
        logger.info(f"Validated config: {config}")
    except ValueError as e:
        logger.error(f"Config validation failed: {e}")
        write_output(artifacts_bucket, job_id, {
            "metrics": {"neg_eval_loss": -100.0},
            "insights": {"insights": [
                {"label": "Evaluation Error",
                 "text": f"Invalid hyperparameter configuration: {e}. "
                         f"Check parameter ranges and types."}
            ]},
        })
        return

    # Step 4: Run training via Ray
    try:
        metrics = run_training(config, job_id)
    except Exception as e:
        # Ray wraps worker CUDA OOM in its own exception types, so check
        # the full exception chain and repr for OOM signatures.
        error_parts = [str(e).lower()]
        cause = e.__cause__ or e.__context__
        if cause:
            error_parts.append(str(cause).lower())
        error_str = " ".join(error_parts)

        is_oom = any(
            sig in error_str
            for sig in ("out of memory", "oom", "cuda error", "cudaerrorillegala")
        )

        if is_oom:
            logger.error(
                "CUDA out of memory during training", exc_info=True
            )
            torch.cuda.empty_cache()
            write_output(artifacts_bucket, job_id, {
                "metrics": {"neg_eval_loss": -100.0},
                "insights": {"insights": [
                    {"label": "OOM Error",
                     "text": "CUDA out of memory. Reduce "
                             "per_device_train_batch_size, max_seq_length, "
                             "or lora_r. batch_size * max_seq_length must "
                             "not exceed 4096."}
                ]},
            })
        else:
            logger.error(f"Training failed: {e}", exc_info=True)
            write_output(artifacts_bucket, job_id, {
                "metrics": {"neg_eval_loss": -100.0},
                "insights": {"insights": [
                    {"label": "Evaluation Error",
                     "text": f"Training failed: {e}. Check hyperparameter "
                             f"compatibility and ranges."}
                ]},
            })
        return

    # Step 5: Write results — immediately, before model merge
    if not metrics or "neg_eval_loss" not in metrics:
        logger.error("Training returned no metrics — Ray result may be empty")
        write_output(artifacts_bucket, job_id, {
            "metrics": {"neg_eval_loss": -100.0},
            "insights": {"insights": [
                {"label": "Evaluation Error",
                 "text": "Training completed but no metrics were returned. "
                         "Check Ray worker logs."}
            ]},
        })
        return

    write_output(artifacts_bucket, job_id, {
        "metrics": metrics,
        "artifacts": {"config_used": config},
    })

    logger.info(
        f"Training complete. neg_eval_loss={metrics.get('neg_eval_loss', 'N/A')}"
    )

    # Step 6: Best-effort LoRA merge (runs on CPU after Ray frees GPU)
    merged_gcs = merge_adapter(job_id)
    if merged_gcs:
        metrics["merged_model_gcs"] = merged_gcs
        write_output(artifacts_bucket, job_id, {
            "metrics": metrics,
            "artifacts": {"config_used": config},
        })


if __name__ == "__main__":
    main()
