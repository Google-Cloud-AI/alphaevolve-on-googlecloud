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
"""Dataset loading and formatting for function-calling SFT."""

import logging
import os
from typing import Any, Dict

from datasets import load_dataset

logger = logging.getLogger(__name__)

DATASET_ID = "NousResearch/hermes-function-calling-v1"
TRAIN_SAMPLES = 2000
EVAL_SAMPLES = 500
SEED = 42

# GCS FUSE mount path for pre-cached dataset
ARTIFACTS_PATH = os.environ.get("ARTIFACTS_PATH", "/mnt/artifacts")
DATASET_PATH = os.path.join(ARTIFACTS_PATH, "dataset")


def format_function_calling(example: Dict[str, Any], tokenizer: Any) -> str:
    """Format a function-calling dataset example into a training string."""
    import json as _json
    import re as _re

    messages = []
    for conversation in example.get("conversations", []):
        role_from = conversation.get("from", "")
        value = conversation.get("value", "")
        if role_from == "system":
            messages.append({"role": "system", "content": value})
        elif role_from == "human":
            messages.append({"role": "user", "content": value})
        elif role_from == "gpt":
            matches = _re.findall(
                r"<tool_call>\n(.*?)\n</tool_call>", value, _re.DOTALL
            )
            if matches:
                tool_calls = []
                for match in matches:
                    try:
                        call = _json.loads(match)
                        tool_calls.append({
                            "type": "tool",
                            "function": {
                                "name": call["name"],
                                "arguments": call["arguments"],
                            },
                        })
                    except (_json.JSONDecodeError, KeyError):
                        continue
                messages.append(
                    {"role": "assistant", "tool_calls": tool_calls}
                )
            else:
                messages.append({"role": "assistant", "content": value})

    try:
        tools = _json.loads(example.get("tools", "[]"))
    except (_json.JSONDecodeError, TypeError):
        tools = None

    try:
        return tokenizer.apply_chat_template(
            messages,
            tools=tools,
            add_generation_prompt=False,
            tokenize=False,
        )
    except Exception:
        parts = []
        for msg in messages:
            parts.append(f"<|{msg['role']}|>\n{msg.get('content', '')}")
        return "\n".join(parts)


def load_and_prepare_dataset(max_seq_length: int, tokenizer: Any):
    """Load the function-calling dataset and prepare train/eval splits.

    Tries GCS FUSE mount first, falls back to Hugging Face Hub download.
    Returns (train_dataset, eval_dataset).
    """
    if os.path.isdir(DATASET_PATH):
        logger.info(f"Loading dataset from mounted path: {DATASET_PATH}")
        import shutil
        local_dataset = "/tmp/dataset_cache"
        if not os.path.isdir(local_dataset):
            shutil.copytree(DATASET_PATH, local_dataset)
        from datasets import Dataset
        dataset = Dataset.load_from_disk(local_dataset)
    else:
        logger.info(
            f"Mounted dataset not found, downloading from {DATASET_ID}"
        )
        dataset = load_dataset(
            DATASET_ID, "func_calling_singleturn", split="train"
        )

    dataset = dataset.shuffle(seed=SEED)
    total_needed = TRAIN_SAMPLES + EVAL_SAMPLES
    if len(dataset) > total_needed:
        dataset = dataset.select(range(total_needed))

    logger.info(f"Formatting {len(dataset)} examples for training")
    dataset = dataset.map(
        lambda ex: {"text": format_function_calling(ex, tokenizer)},
        remove_columns=dataset.column_names,
        num_proc=4,
    )

    split = dataset.train_test_split(test_size=EVAL_SAMPLES, seed=SEED)
    return split["train"], split["test"]
