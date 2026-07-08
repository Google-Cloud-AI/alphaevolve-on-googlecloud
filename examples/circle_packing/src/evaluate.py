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
import logging
from typing import Any, Mapping

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

from alpha_evolve.models import (
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveProgramEvaluation,
)

logger = logging.getLogger(__name__)

CIRCLE_PACKING_EVALUATION_METRIC = "sum_of_radii"
CIRCLE_PACKING_EVALUATION_INPUTS = {"n": 26}

import os


def _load_initial_program():
    with open(os.path.join(os.path.dirname(__file__), "program.py"), "r") as f:
        return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()


def circle_packing_evaluation(program_candidate) -> dict:
    logger.debug("Starting evaluation: %s", program_candidate)
    code = program_candidate["content"]["files"][0]["content"]
    logger.debug("Code length: %d", len(code))

    # Sentinel used when the program fails to produce a valid score. The API
    # requires a numeric score per metric and `sum_of_radii` is maximized, so a
    # large negative value keeps failed candidates from being selected.
    score_value: float = -1e12
    insights_list: list[AlphaEvolveEvaluationInsight] = []

    try:
        exec_namespace = {"np": np, "Any": Any, "Mapping": Mapping}
        exec(code, exec_namespace)
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
                        text="The evaluation function returned an invalid score (-infinity or None), suggesting the packing constraints were not met.",
                    )
                )
        else:
            insights_list.append(
                AlphaEvolveEvaluationInsight(
                    label="Invalid Program Structure",
                    text="The program is missing a callable 'evaluate' function, which is required for evaluation.",
                )
            )

    except Exception as e:
        error_message = (
            f"The program failed during execution with the following error: {e}"
        )
        logger.exception(error_message)
        insights_list.append(
            AlphaEvolveEvaluationInsight(label="Runtime Error", text=error_message)
        )

    scores = [
        AlphaEvolveEvaluationScore(
            metric=CIRCLE_PACKING_EVALUATION_METRIC, score=score_value
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


def visualize_packing(circles, title, container_size=1.0):
    """Creates and shows a single circle packing visualization."""
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
        circle = patches.Circle(
            (x, y), r, facecolor=colors(i), alpha=0.8, edgecolor="black", linewidth=0.5
        )
        ax.add_patch(circle)
    plt.show()