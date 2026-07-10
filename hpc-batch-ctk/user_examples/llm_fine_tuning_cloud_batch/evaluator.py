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
"""Evaluator module for testing and scoring LLM Fine-Tuning LoRA programs."""

import json
import logging
import os
import signal
from typing import Any, Mapping
import numpy as np

from alpha_evolve.models import (
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveProgramEvaluation,
)

logger = logging.getLogger(__name__)

LLM_FINE_TUNING_EVALUATION_METRIC = "neg_eval_loss"
LLM_FINE_TUNING_EVALUATION_INPUTS = {}


class TimeoutError(Exception):
  pass


def handler(signum, frame):
  raise TimeoutError("Evaluation timed out")


signal.signal(signal.SIGALRM, handler)


def _load_initial_program():
  with open(os.path.join(os.path.dirname(__file__), "main.py"), "r") as f:
    return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()


def llm_fine_tuning_evaluation(timeout_seconds=3600) -> dict[str, Any]:
  """The evaluation function that runs on Cloud Batch evaluator or local worker.

  Args:
    timeout_seconds: The timeout in seconds.

  Returns:
    A dictionary containing structured evaluation scores and insights.
  """
  metadata_path = "program_candidate_data.json"
  try:
    with open(metadata_path, "r") as f:
      metadata = json.load(f)
    program_name = metadata.get("name", "unknown")
  except Exception as e:
    logger.warning("Failed to read metadata: %s", e)
    program_name = "unknown"

  logger.info("STARTING EVALUATION: %s", program_name)

  main_py_path = "main.py"
  try:
    with open(main_py_path, "r") as f:
      code = f.read()
  except Exception as e:
    logger.error("Failed to read main.py: %s", e)
    raise e
  logger.info("CODE LENGTH: %d", len(code))

  score_value: float | None = None
  insights_list: list[AlphaEvolveEvaluationInsight] = []

  try:
    signal.alarm(timeout_seconds)

    exec_namespace = {"np": np, "Any": Any, "Mapping": Mapping, "os": os, "logging": logging}
    exec(code, exec_namespace)  # pylint: disable=exec-used
    eval_func = exec_namespace.get("evaluate")

    if callable(eval_func):
      result = eval_func(LLM_FINE_TUNING_EVALUATION_INPUTS)
      score = result.get(LLM_FINE_TUNING_EVALUATION_METRIC)
      if score is not None and score > -100.0:
        score_value = float(score)
      else:
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Penalized Configuration",
                text="The evaluation returned a penalized score (-100.0), likely indicating VRAM Out-Of-Memory hazard (batch_size * max_seq_length > 4096) or invalid hyperparameter bounds.",
            )
        )
    else:
      insights_list.append(
          AlphaEvolveEvaluationInsight(
              label="Invalid Program Structure",
              text="The program is missing a callable 'evaluate' function, which is required for evaluation.",
          )
      )

  except TimeoutError:
    error_message = (
        f"The program evaluation exceeded the time limit of {timeout_seconds} seconds and was terminated."
    )
    logger.error(error_message)
    insights_list.append(
        AlphaEvolveEvaluationInsight(label="Execution Timeout", text=error_message)
    )
  except Exception as e:  # pylint: disable=broad-exception-caught
    error_message = f"The program failed during execution with error: {e}"
    logger.exception(error_message)
    insights_list.append(
        AlphaEvolveEvaluationInsight(label="Runtime Error", text=error_message)
    )
  finally:
    signal.alarm(0)

  scores = [
      AlphaEvolveEvaluationScore(
          metric=LLM_FINE_TUNING_EVALUATION_METRIC, score=score_value
      )
  ]

  if insights_list:
    insights = AlphaEvolveEvaluationInsights(insights=insights_list)
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores), insights=insights
    )
  else:
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores)
    )

  return program_evaluation.model_dump()
