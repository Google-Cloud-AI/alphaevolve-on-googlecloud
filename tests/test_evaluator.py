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

import pytest
from examples.circle_packing.src.evaluate import circle_packing_evaluation, CIRCLE_PACKING_EVALUATION_METRIC, CIRCLE_PACKING_EVALUATION_INPUTS
import numpy as np
from typing import Any, Mapping

# --- Corrected sample program code ---
SAMPLE_PROGRAM_CODE = '''
# pylint: disable=g-import-not-at-top
# pylint: disable=g-bad-import-order
# pylint: disable=pointless-string-statement
from typing import Any, Mapping

# EVOLVE-BLOCK-START
"""Constructor-based circle packing for n=26 circles"""
import numpy as np


def construct_packing(n, random_seed: int):
  """Construct a specific arrangement of 26 circles in a unit square.

  The goal is to maximize the sum of their radii.

  Args:
      n: Number of circles.
      random_seed: Random seed for reproducibility.

  Returns:
      Tuple of (centers, radii, sum_of_radii)
      centers: np.array of shape (26, 2) with (x, y) coordinates
      radii: np.array of shape (26) with radius of each circle
      sum_of_radii: Sum of all radii
  """

  rng = np.random.default_rng(random_seed)
  centers = np.zeros((n, 2))

  # Place circles in a structured pattern
  # This is a simple pattern - evolution will improve this

  # First, place a large circle in the center
  centers[0] = [0.5, 0.5]

  # Distribute remaining n-1 circles into two rings
  num_remaining = n - 1
  if num_remaining > 0:
    # Aim for roughly a 1:2 ratio for inner:outer rings, adjusting for total n
    num_inner_ring = min(num_remaining, max(1, round(num_remaining / 3)))
    num_outer_ring = num_remaining - num_inner_ring

    start_idx = 1
    if num_inner_ring > 0:
      for i in range(num_inner_ring):
        angle = 2 * np.pi * i / num_inner_ring
        centers[start_idx + i] = [0.5 + 0.3 * np.cos(angle), 0.5 + 0.3 * np.sin(angle)]
      start_idx += num_inner_ring

    if num_outer_ring > 0:
      for i in range(num_outer_ring):
        angle = 2 * np.pi * i / num_outer_ring * rng.uniform(0.9, 1.1)
        centers[start_idx + i] = [0.5 + 0.7 * np.cos(angle), 0.5 + 0.7 * np.sin(angle)]

  # Additional positioning adjustment to make sure all circles
  # are inside the square and don't overlap
  # No clipping; radii will be constrained by compute_max_radii

  # Compute maximum valid radii for this configuration
  radii = compute_max_radii(centers, random_seed)

  # Calculate the sum of radii
  sum_radii = np.sum(radii)

  return centers, radii, sum_radii


def compute_max_radii(centers, random_seed: int):
  """Compute the maximum possible radii for each circle position.

  Make sure that they don't overlap and stay within the unit square.

  Args:
      centers: np.array of shape (n, 2) with (x, y) coordinates
      random_seed: Random seed for reproducibility.

  Returns:
      np.array of shape (n) with radius of each circle
  """
  del random_seed  # Unused.
  n = centers.shape[0]
  radii = np.ones(n)

  # First, limit by distance to square borders
  for i in range(n):
    x, y = centers[i]
    # Distance to borders
    radii[i] = min(x, y, 1 - x, 1 - y)

  # Then, limit by distance to other circles
  # Each pair of circles with centers at distance d can have
  # sum of radii at most d to avoid overlap
  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))

      # If current radii would cause overlap
      if radii[i] + radii[j] > dist:
        # Scale both radii proportionally
        scale = dist / (radii[i] + radii[j] + 1e-7)
        radii[i] *= scale
        radii[j] *= scale

  return radii
# EVOLVE-BLOCK-END


def _circles_overlap(centers, radii):
  """Protected function to compute max radii."""
  n = centers.shape[0]

  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
      if radii[i] + radii[j] > dist:
        return True

  return False


def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
  """Construct a packing and evaluate its score."""
  n = eval_inputs['n']
  if 'random_seed' not in eval_inputs:
    random_seed = 42
  else:
    random_seed = eval_inputs['random_seed']
  centers, radii, _ = construct_packing(
      n, random_seed=random_seed
  )
  if (
      centers.shape != (n, 2)
      or not np.isfinite(centers).all()
      or not (
          (radii[:, None] <= centers) & (centers <= 1 - radii[:, None])
      ).all()
  ):
    return {'sum_of_radii': -np.inf}

  if (
      radii.shape != (n,)
      or not np.isfinite(radii).all()
      or not (0 <= radii).all()
  ):
    return {'sum_of_radii': -np.inf}

  if _circles_overlap(centers, radii):
    return {'sum_of_radii': -np.inf}

  return {'sum_of_radii': float(np.sum(radii))}
'''

SAMPLE_PROGRAM_CANDIDATE = {
    'name': 'projects/862721868538/locations/global/collections/default_collection/engines/alpha-evolve-experiment-engine/sessions/15229354329142304975/alphaEvolveExperiments/3986949617876084635/alphaEvolvePrograms/5933359537960442881',
    'content': {
        'files': [
            {
                'path': 'main.py',
                'content': SAMPLE_PROGRAM_CODE
            }
        ]
    },
    'parentPrograms': ['1'],
    'lockToken': '2872196029638572000'
}

# Calculate the expected score by executing the code once.
_exec_globals = {"np": np, "Any": Any, "Mapping": Mapping}
_exec_locals = _exec_globals # Use same dict for globals and locals
exec(SAMPLE_PROGRAM_CODE, _exec_globals, _exec_locals)
_evaluate_func = _exec_locals.get("evaluate")
_raw_score_from_sample_program = _evaluate_func(CIRCLE_PACKING_EVALUATION_INPUTS)[CIRCLE_PACKING_EVALUATION_METRIC]

# Apply the same conversion logic as circle_packing_evaluation does
if _raw_score_from_sample_program == -np.inf:
    EXPECTED_SCORE_FOR_SAMPLE_PROGRAM = None
else:
    EXPECTED_SCORE_FOR_SAMPLE_PROGRAM = _raw_score_from_sample_program


def test_circle_packing_evaluation_valid_program():
    """Tests that circle_packing_evaluation correctly evaluates a program."""
    result = circle_packing_evaluation(SAMPLE_PROGRAM_CANDIDATE)
    assert "scores" in result
    assert "scores" in result["scores"]
    assert len(result["scores"]["scores"]) == 1
    score_item = result["scores"]["scores"][0]
    assert score_item["metric"] == CIRCLE_PACKING_EVALUATION_METRIC
    
    if EXPECTED_SCORE_FOR_SAMPLE_PROGRAM is not None:
        assert score_item["score"] == pytest.approx(EXPECTED_SCORE_FOR_SAMPLE_PROGRAM)
        assert isinstance(score_item["score"], float)
        assert not np.isinf(score_item["score"])
    else:
        assert score_item["score"] is None


def test_circle_packing_evaluation_missing_evaluate_func():
    """Tests that circle_packing_evaluation handles a program with a missing 'evaluate' function."""
    invalid_program_candidate = {
        'name': 'test_program_missing_eval',
        'content': {
            'files': [
                {
                    'path': 'main.py',
                    'content': 'def some_other_func(): return {}' # Missing evaluate
                }
            ]
        }
    }
    result = circle_packing_evaluation(invalid_program_candidate)
    assert result["scores"]["scores"][0]["score"] is None
    assert "insights" in result
    assert result["insights"]["insights"][0]["label"] == "Invalid Program Structure"
    assert "The program is missing a callable 'evaluate' function" in result["insights"]["insights"][0]["text"]


def test_circle_packing_evaluation_code_raises_exception():
    """Tests that circle_packing_evaluation handles a program where the code raises an exception."""
    error_program_candidate = {
        'name': 'test_program_raises_exception',
        'content': {
            'files': [
                {
                    'path': 'main.py',
                    'content': 'def evaluate(eval_inputs): raise ValueError("Test error")'
                }
            ]
        }
    }
    result = circle_packing_evaluation(error_program_candidate)
    assert result["scores"]["scores"][0]["score"] is None
    assert "insights" in result
    assert result["insights"]["insights"][0]["label"] == "Runtime Error"
    assert "The program failed during execution with the following error: Test error" in result["insights"]["insights"][0]["text"]

def test_circle_packing_evaluation_invalid_score():
    """Tests that circle_packing_evaluation handles a program that returns an invalid score."""
    invalid_score_candidate = {
        'name': 'test_program_invalid_score',
        'content': {
            'files': [
                {
                    'path': 'main.py',
                    'content': 'def evaluate(eval_inputs): return {"sum_of_radii": -float("inf")}'
                }
            ]
        }
    }
    result = circle_packing_evaluation(invalid_score_candidate)
    assert result["scores"]["scores"][0]["score"] is None
    assert "insights" in result
    assert result["insights"]["insights"][0]["label"] == "Invalid Score"
    assert "The evaluation function returned an invalid score" in result["insights"]["insights"][0]["text"]
