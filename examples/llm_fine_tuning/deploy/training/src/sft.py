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
"""SFT training function for Ray TorchTrainer workers.

This module defines the training loop that runs inside each Ray worker.
It follows the same pattern as the reference at docs/raygemma4/src/sft.py.
"""

import logging
import os

import torch
from trl import SFTConfig, SFTTrainer

from src.data import load_and_prepare_dataset
from src.model import apply_lora, load_model, load_tokenizer
from src.utils import log_gpu_info

try:
    from ray.train.huggingface.transformers import (
        RayTrainReportCallback,
        prepare_trainer,
    )
except ImportError:
    RayTrainReportCallback = None
    prepare_trainer = None

logger = logging.getLogger(__name__)

# Fixed training parameters (not evolvable)
MAX_STEPS = 100
EVAL_STEPS = 50
SEED = 42
OUTPUT_DIR = "/tmp/lora_output"


def train_func(config: dict):
    """LoRA SFT training loop executed inside a Ray worker with GPU.

    Args:
        config: Dict with keys "job_id", "model_source", "hyperparams".
            hyperparams contains the validated AlphaEvolve hyperparameters.
    """
    hp = config["hyperparams"]
    model_source = config["model_source"]
    job_id = config["job_id"]

    logger.info(f"[{job_id}] Ray worker started — PID: {os.getpid()}")
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
        logger.info(f"[{job_id}] GPU: {gpu_name}, {gpu_mem:.1f}GB")
    else:
        logger.warning(f"[{job_id}] No CUDA device available!")

    # --- Tokenizer + Model + LoRA ---
    logger.info(f"[{job_id}] Loading tokenizer from {model_source}")
    tokenizer = load_tokenizer(model_source)

    logger.info(f"[{job_id}] Loading model (bf16, no quantization)")
    model = load_model(model_source, freeze_non_text=True)
    log_gpu_info(f"[{job_id}] After model load — ")

    logger.info(f"[{job_id}] Applying LoRA (r={hp['lora_r']})")
    model = apply_lora(
        model,
        lora_r=hp["lora_r"],
        lora_alpha=hp["lora_alpha"],
        lora_dropout=hp["lora_dropout"],
    )
    log_gpu_info(f"[{job_id}] After LoRA — ")

    # --- Dataset ---
    logger.info(f"[{job_id}] Loading dataset")
    train_dataset, eval_dataset = load_and_prepare_dataset(
        hp["max_seq_length"], tokenizer
    )
    logger.info(
        f"[{job_id}] Dataset ready — "
        f"train: {len(train_dataset)}, eval: {len(eval_dataset)}"
    )

    # --- SFT Config ---
    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        max_steps=MAX_STEPS,
        per_device_train_batch_size=hp["per_device_train_batch_size"],
        gradient_accumulation_steps=hp["gradient_accumulation_steps"],
        learning_rate=hp["learning_rate"],
        lr_scheduler_type=hp["lr_scheduler_type"],
        warmup_ratio=hp["warmup_ratio"],
        weight_decay=hp["weight_decay"],
        optim=hp["optim"],
        max_grad_norm=hp["max_grad_norm"],
        bf16=hp["bf16"],
        eval_strategy="steps",
        eval_steps=EVAL_STEPS,
        save_strategy="steps",
        save_steps=EVAL_STEPS,
        logging_steps=10,
        seed=SEED,
        report_to="none",
        remove_unused_columns=False,
        max_length=hp["max_seq_length"],
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    logger.info(
        f"[{job_id}] Training config — "
        f"steps: {MAX_STEPS}, "
        f"batch: {hp['per_device_train_batch_size']}, "
        f"grad_accum: {hp['gradient_accumulation_steps']}, "
        f"lr: {hp['learning_rate']}, "
        f"seq_len: {hp['max_seq_length']}, "
        f"optim: {hp['optim']}"
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    # --- Ray integration ---
    if RayTrainReportCallback is not None:
        trainer.add_callback(RayTrainReportCallback())
        logger.info(f"[{job_id}] RayTrainReportCallback added")
    if prepare_trainer is not None:
        trainer = prepare_trainer(trainer)
        logger.info(f"[{job_id}] Trainer prepared for Ray")

    # --- Train ---
    # RayTrainReportCallback handles metrics reporting and checkpoint saves
    # at each save_steps interval. The driver reads metrics and adapter
    # weights from result.metrics and result.checkpoint.
    logger.info(f"[{job_id}] Starting training ({MAX_STEPS} steps)")
    log_gpu_info(f"[{job_id}] Before training — ")
    trainer.train()
    logger.info(f"[{job_id}] Training complete")
    log_gpu_info(f"[{job_id}] After training — ")

    # Free GPU memory
    del model, trainer
    torch.cuda.empty_cache()
