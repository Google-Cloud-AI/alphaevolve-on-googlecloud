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
"""Evaluator module for testing and scoring Circle Packing programs."""

import json
import logging
import os
import signal
from typing import Any, Mapping

import matplotlib.patches as patches
import matplotlib.pyplot as plt
from alpha_evolve.models import (AlphaEvolveEvaluationInsight, AlphaEvolveEvaluationInsights,
                    AlphaEvolveEvaluationScore, AlphaEvolveEvaluationScores,
                    AlphaEvolveProgramEvaluation)
import numpy as np

logger = logging.getLogger(__name__)

CIRCLE_PACKING_EVALUATION_METRIC = "sum_of_radii"
CIRCLE_PACKING_EVALUATION_INPUTS = {"n": 26}


class TimeoutError(Exception):
  pass


def handler(signum, frame):
  raise TimeoutError("Evaluation timed out")


signal.signal(signal.SIGALRM, handler)


def _load_initial_program():
  with open(os.path.join(os.path.dirname(__file__), "main.py"), "r") as f:
    return f.read()


def get_initial_lib_helper_content():
  with open(os.path.join(os.path.dirname(__file__), "libpacking.cpp"),
            "r") as f:
    return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()
INITIAL_LIB_HELPER_CONTENT = get_initial_lib_helper_content()


def circle_packing_evaluation(timeout_seconds=30) -> dict[str, Any]:
  """The evaluation function that runs on either a local worker or a Cloud Batch
    evaluator.

  Args:
    timeout_seconds: The timeout in seconds.

  Returns:
    A dictionary containing the evaluation results.
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
  
  # Read code from main.py in the evaluations directory
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

    exec_namespace = {"np": np, "Any": Any, "Mapping": Mapping}
    exec(code, exec_namespace)  # pylint: disable=exec-used
    eval_func = exec_namespace.get("evaluate")

    if callable(eval_func):
      result = eval_func(CIRCLE_PACKING_EVALUATION_INPUTS)
      score = result.get(CIRCLE_PACKING_EVALUATION_METRIC)
      if score != -np.inf and score is not None:
        score_value = float(score)
      else:
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Invalid Score",
                text="The evaluation function returned an invalid score "
                "(-infinity or None), suggesting the packing "
                "constraints were not met.",
            ))
    else:
      insights_list.append(
          AlphaEvolveEvaluationInsight(
              label="Invalid Program Structure",
              text="The program is missing a callable 'evaluate' function, "
              "which is required for evaluation.",
          ))

  except TimeoutError:
    error_message = (
        f"The program evaluation exceeded the time limit of "
        f"{timeout_seconds} seconds and was terminated.")
    logger.error(error_message)
    insights_list.append(
        AlphaEvolveEvaluationInsight(label="Execution Timeout",
                                     text=error_message))
  except Exception as e:  # pylint: disable=broad-exception-caught
    error_message = (
        f"The program failed during execution with the following error: {e}")
    logger.exception(error_message)
    insights_list.append(
        AlphaEvolveEvaluationInsight(label="Runtime Error", text=error_message))
  finally:
    signal.alarm(0)

  scores = [
      AlphaEvolveEvaluationScore(metric=CIRCLE_PACKING_EVALUATION_METRIC,
                                 score=score_value)
  ]

  if insights_list:
    insights = AlphaEvolveEvaluationInsights(insights=insights_list)
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores), insights=insights)
  else:
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores))

  return program_evaluation.model_dump()


def visualize_packing(circles, title, container_size=1.0, output_path=None):
  """Creates a visualization of the circle packing."""
  fig, ax = plt.subplots(1, figsize=(8, 8))
  ax.set_aspect("equal", "box")
  ax.set_xlim(0, container_size)
  ax.set_ylim(0, container_size)
  ax.set_title(title, fontsize=14, pad=15)
  ax.grid(True, linestyle="--", alpha=0.5)

  container = patches.Rectangle(
      (0, 0),
      container_size,
      container_size,
      linewidth=2,
      edgecolor="black",
      facecolor="none",
  )
  ax.add_patch(container)

  colors = plt.cm.get_cmap("viridis", len(circles))
  for i, (x, y, r) in enumerate(circles):
    circle = patches.Circle((x, y),
                            r,
                            facecolor=colors(i),
                            alpha=0.8,
                            edgecolor="black",
                            linewidth=0.5)
    ax.add_patch(circle)

  if output_path:
    plt.savefig(output_path)
  plt.show()
  plt.close(fig)
