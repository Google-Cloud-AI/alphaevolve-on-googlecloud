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
"""Main script for running the LLM Fine-Tuning AlphaEvolve experiment."""
# pylint: disable=g-importing-member

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Mapping

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController
from evaluator import (
    INITIAL_PROGRAM_CODE,
    LLM_FINE_TUNING_EVALUATION_METRIC,
    llm_fine_tuning_evaluation,
)
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env
import nest_asyncio

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
MODEL = os.getenv("_MODEL", "GEMINI_V2P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "20")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")


def main():
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )
  logger = logging.getLogger(__name__)

  exp_config = {
      "title": "LLM Fine-Tuning LoRA Optimization",
      "problem_description": (
          "Evolve LoRA fine-tuning hyperparameters for Gemma 4 E2B on a"
          " function-calling dataset to minimize evaluation loss."
      ),
      "program_language": "python",
      "run_settings": {
          "max_programs": MAX_PROGRAMS_GENERATED,
          "concurrency": CONCURRENCY,
      },
      "generation_settings": {
          "models": parse_models_from_env(MODEL),
      },
  }
  initial_program = {
      "content": {
          "files": [{
              "path": "main.py",
              "content": INITIAL_PROGRAM_CODE,
          }]
      },
      "evaluation": {
          "scores": {
              "scores": [{
                  "metric": LLM_FINE_TUNING_EVALUATION_METRIC,
                  "score": -100.0,
              }]
          }
      },
  }

  # nest_asyncio allows the asyncio event loop to be nested
  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=llm_fine_tuning_evaluation,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )


if __name__ == "__main__":
  if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
    print("Please set the _PROJECT_ID environment variable.")
    sys.exit(1)
  if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
    print("Please set the _CLOUD_BUCKET_NAME environment variable.")
    sys.exit(1)
  main()
