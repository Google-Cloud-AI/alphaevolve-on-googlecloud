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

"""Seed program for LLM fine-tuning hyperparameter optimization.

This file defines the initial hyperparameter configuration for LoRA fine-tuning
of Gemma 4 E2B on a function-calling dataset. AlphaEvolve will evolve the
get_training_config() function to discover better hyperparameter combinations.
"""


# EVOLVE-BLOCK-START
def get_training_config():
    """Return hyperparameter configuration for LoRA fine-tuning of Gemma 4 E2B.

    This function is evolved by AlphaEvolve. The returned dictionary configures
    LoRA (Low-Rank Adaptation) parameters, optimizer settings, batch sizing,
    and data processing for fine-tuning on function-calling data.

    Returns:
        dict: Training configuration with the following groups:
            - LoRA: rank, alpha scaling, dropout
            - Optimizer: learning rate, scheduler, warmup, weight decay
            - Batch: per-device batch size, gradient accumulation, sequence length
            - Precision: bf16 mixed precision flag
    """
    return {
        # LoRA configuration (target_modules fixed to "all-linear" in trainer)
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,

        # Optimizer and learning rate schedule
        "learning_rate": 5e-5,
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.03,
        "weight_decay": 0.01,
        "optim": "adamw_8bit",
        "max_grad_norm": 1.0,

        # Batch and data configuration — keep batch_size * max_seq_length <= 4096
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 4,
        "max_seq_length": 512,

        # Precision
        "bf16": True,
    }
# EVOLVE-BLOCK-END


def evaluate(inputs):
    """Extract training config for the remote evaluator.

    This function is called by the training worker after exec()-ing
    the evolved code. It returns the hyperparameter configuration dict
    that will be used to configure LoRA fine-tuning.

    Args:
        inputs: Unused. Present for interface compatibility.

    Returns:
        dict: The training configuration from get_training_config().
    """
    config = get_training_config()
    return config
