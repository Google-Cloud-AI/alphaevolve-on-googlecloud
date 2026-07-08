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

"""Local evaluator for the TSP example.

Executes evolved code in a sandboxed namespace, calls ``evaluate()``, and
returns structured scores + insights for the AlphaEvolve controller loop.
"""

import logging
import os

import numpy as np
from typing import Any, Mapping

logger = logging.getLogger(__name__)

METRIC_NAME = "neg_tour_length"


def _load_initial_program() -> str:
    """Load the seed program source code."""
    main_path = os.path.join(os.path.dirname(__file__), "program.py")
    with open(main_path, "r") as f:
        return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()


def tsp_evaluation_function(program_candidate: dict) -> dict:
    """Evaluate a TSP program candidate.

    Executes the candidate code in a sandboxed namespace and calls its
    ``evaluate()`` function. Returns structured scores and insights.

    Args:
        program_candidate: dict with ``content.files[0].content`` holding
            the Python source code to evaluate.

    Returns:
        Evaluation dict with ``scores`` and optional ``insights``.
    """
    code = program_candidate["content"]["files"][0]["content"]
    score_value = None
    insights_list = []

    try:
        exec_namespace: dict[str, Any] = {
            "np": np,
            "Any": Any,
            "Mapping": Mapping,
        }
        exec(code, exec_namespace)

        eval_func = exec_namespace.get("evaluate")
        if not callable(eval_func):
            insights_list.append({
                "label": "Invalid Program Structure",
                "text": (
                    "The program must define a callable 'evaluate' function. "
                    "Found: " + str(type(exec_namespace.get("evaluate")))
                ),
            })
        else:
            result = eval_func({})
            neg_tour_length = result.get(METRIC_NAME)

            if neg_tour_length is not None and np.isfinite(neg_tour_length):
                score_value = float(neg_tour_length)
            else:
                insights_list.append({
                    "label": "Invalid Score",
                    "text": (
                        f"Score for '{METRIC_NAME}' is None or non-finite. "
                        f"Got: {neg_tour_length}"
                    ),
                })

            # Attach secondary metrics as insights for visibility
            tour_validity = result.get("tour_validity")
            avg_improvement = result.get("avg_improvement_over_random")

            if tour_validity is not None and tour_validity < 1.0:
                insights_list.append({
                    "label": "Invalid Tour",
                    "text": "One or more tours are not valid permutations.",
                })

            if avg_improvement is not None and np.isfinite(avg_improvement):
                insights_list.append({
                    "label": "Improvement vs Random",
                    "text": f"{avg_improvement:.2f}% better than random tours on average.",
                })

    except Exception as e:
        insights_list.append({
            "label": "Runtime Error",
            "text": str(e),
        })

    evaluation: dict[str, Any] = {
        "scores": {
            "scores": [
                {"metric": METRIC_NAME, "score": score_value},
            ],
        },
    }
    if insights_list:
        evaluation["insights"] = {"insights": insights_list}

    return evaluation
