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
"""Model and tokenizer loading, LoRA setup, and model merging.

Uses plain LoRA (no QLoRA) to avoid the known PEFT/bitsandbytes tied-weights
bug with Gemma 4's ClippableLinear wrappers.
"""

import logging
import os

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)

MODEL_ID = "google/gemma-4-E2B-it"

# Gemma 4 uses ClippableLinear wrappers — individual module names fail.
# Use PEFT's "all-linear" shorthand instead.
LORA_TARGET_MODULES = "all-linear"

# GCS FUSE mount path for pre-cached model
ARTIFACTS_PATH = os.environ.get("ARTIFACTS_PATH", "/mnt/artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_PATH, "model")


def get_model_source() -> str:
    """Return local FUSE-mounted model path if available, else HF model ID."""
    if os.path.isdir(MODEL_PATH):
        return MODEL_PATH
    return MODEL_ID


def load_tokenizer(model_source: str) -> AutoTokenizer:
    """Load tokenizer and set pad_token if missing."""
    tokenizer = AutoTokenizer.from_pretrained(model_source)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def load_model(
    model_source: str, freeze_non_text: bool = True
) -> AutoModelForCausalLM:
    """Load model in bf16 with SDPA attention.

    Moves to CUDA and optionally freezes vision/audio towers for text-only
    fine-tuning.
    """
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    model = model.to("cuda")

    if freeze_non_text:
        frozen = 0
        for name, param in model.named_parameters():
            if not name.startswith("model.language_model"):
                param.requires_grad = False
                frozen += 1
        if frozen:
            logger.info(f"Froze {frozen} non-text parameters")

    return model


def apply_lora(
    model: AutoModelForCausalLM,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
) -> PeftModel:
    """Apply LoRA adapter to the model.

    Returns the PeftModel with trainable LoRA parameters.
    """
    peft_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=LORA_TARGET_MODULES,
        task_type="CAUSAL_LM",
        bias="none",
    )
    model = get_peft_model(model, peft_config)

    trainable = sum(
        p.numel() for p in model.parameters() if p.requires_grad
    )
    total = sum(p.numel() for p in model.parameters())
    logger.info(
        f"LoRA applied — trainable: {trainable:,} / {total:,} "
        f"({100 * trainable / total:.2f}%)"
    )
    return model


def save_merged_model(
    model_source: str,
    adapter_dir: str,
    tokenizer: AutoTokenizer,
    output_path: str,
) -> str:
    """Merge LoRA adapter into base model and save.

    Loads the base model on CPU (no quantization), merges the LoRA adapter
    weights, and saves the full merged model with tokenizer.
    """
    logger.info("Loading base model for merging (CPU, bf16)...")
    base_model = AutoModelForCausalLM.from_pretrained(
        model_source,
        low_cpu_mem_usage=True,
        dtype=torch.bfloat16,
    )

    logger.info("Merging LoRA adapter into base model...")
    peft_model = PeftModel.from_pretrained(base_model, adapter_dir)
    merged_model = peft_model.merge_and_unload()

    os.makedirs(output_path, exist_ok=True)
    logger.info(f"Saving merged model to {output_path}...")
    merged_model.save_pretrained(
        output_path, safe_serialization=True, max_shard_size="2GB"
    )
    tokenizer.save_pretrained(output_path)

    del merged_model, peft_model, base_model
    return output_path
