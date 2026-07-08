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
"""Config extraction from evolved code and hyperparameter validation."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# OOM guard: batch_size * seq_length must not exceed this.
# Gemma 4 E2B in bf16 uses ~10 GB on A100 (40 GB). With LoRA "all-linear",
# optimizer states, and activations, ~25-28 GB remains for training.
MAX_BATCH_SEQ_PRODUCT = 4096

VALID_SCHEDULERS = {"cosine", "linear", "constant_with_warmup", "constant"}
VALID_OPTIMS = {"adamw_torch", "adamw_8bit", "adafactor"}


def extract_config(files: List[Dict[str, str]]) -> Dict[str, Any]:
    """Execute the evolved code and extract the training config dict."""
    main_file = None
    for f in files:
        if f.get("path", "").endswith("program.py"):
            main_file = f
            break

    if not main_file:
        raise ValueError("No program.py file found in the submitted files.")

    namespace: Dict[str, Any] = {}
    exec(main_file["content"], namespace)

    if "get_training_config" not in namespace:
        raise ValueError(
            "The evolved code must define a get_training_config() function."
        )

    config = namespace["get_training_config"]()
    if not isinstance(config, dict):
        raise ValueError("get_training_config() must return a dict.")

    return config


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize the hyperparameter configuration.

    Returns the validated config dict. Raises ValueError on invalid configs.
    """
    validated = {}

    # LoRA parameters
    lora_r = int(config.get("lora_r", 16))
    if not 4 <= lora_r <= 64:
        raise ValueError(f"lora_r={lora_r} out of range [4, 64].")
    validated["lora_r"] = lora_r

    lora_alpha = int(config.get("lora_alpha", 32))
    if not 8 <= lora_alpha <= 128:
        raise ValueError(f"lora_alpha={lora_alpha} out of range [8, 128].")
    validated["lora_alpha"] = lora_alpha

    lora_dropout = float(config.get("lora_dropout", 0.05))
    if not 0.0 <= lora_dropout <= 0.2:
        raise ValueError(
            f"lora_dropout={lora_dropout} out of range [0.0, 0.2]."
        )
    validated["lora_dropout"] = lora_dropout

    # Optimizer parameters
    lr = float(config.get("learning_rate", 2e-4))
    if not 1e-5 <= lr <= 1e-3:
        raise ValueError(f"learning_rate={lr} out of range [1e-5, 1e-3].")
    validated["learning_rate"] = lr

    scheduler = str(config.get("lr_scheduler_type", "cosine"))
    if scheduler not in VALID_SCHEDULERS:
        raise ValueError(
            f"lr_scheduler_type='{scheduler}' not in {VALID_SCHEDULERS}."
        )
    validated["lr_scheduler_type"] = scheduler

    warmup = float(config.get("warmup_ratio", 0.03))
    if not 0.0 <= warmup <= 0.1:
        raise ValueError(f"warmup_ratio={warmup} out of range [0.0, 0.1].")
    validated["warmup_ratio"] = warmup

    wd = float(config.get("weight_decay", 0.01))
    if not 0.0 <= wd <= 0.1:
        raise ValueError(f"weight_decay={wd} out of range [0.0, 0.1].")
    validated["weight_decay"] = wd

    optim = str(config.get("optim", "adamw_torch"))
    if optim not in VALID_OPTIMS:
        raise ValueError(f"optim='{optim}' not in {VALID_OPTIMS}.")
    validated["optim"] = optim

    max_grad_norm = float(config.get("max_grad_norm", 1.0))
    if not 0.1 <= max_grad_norm <= 5.0:
        raise ValueError(
            f"max_grad_norm={max_grad_norm} out of range [0.1, 5.0]."
        )
    validated["max_grad_norm"] = max_grad_norm

    # Batch parameters
    batch_size = int(config.get("per_device_train_batch_size", 2))
    if not 1 <= batch_size <= 8:
        raise ValueError(
            f"per_device_train_batch_size={batch_size} out of range [1, 8]."
        )
    validated["per_device_train_batch_size"] = batch_size

    grad_accum = int(config.get("gradient_accumulation_steps", 4))
    if not 1 <= grad_accum <= 16:
        raise ValueError(
            f"gradient_accumulation_steps={grad_accum} out of range [1, 16]."
        )
    validated["gradient_accumulation_steps"] = grad_accum

    max_seq = int(config.get("max_seq_length", 512))
    if not 256 <= max_seq <= 1024:
        raise ValueError(
            f"max_seq_length={max_seq} out of range [256, 1024]."
        )
    validated["max_seq_length"] = max_seq

    # OOM guard
    if batch_size * max_seq > MAX_BATCH_SEQ_PRODUCT:
        raise ValueError(
            f"batch_size * max_seq_length = {batch_size * max_seq} exceeds "
            f"OOM guard limit of {MAX_BATCH_SEQ_PRODUCT}. "
            f"Reduce per_device_train_batch_size or max_seq_length."
        )

    # Precision
    validated["bf16"] = bool(config.get("bf16", True))

    return validated
