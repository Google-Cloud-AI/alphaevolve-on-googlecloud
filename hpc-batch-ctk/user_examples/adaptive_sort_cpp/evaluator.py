# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from alpha_evolve.models import (AlphaEvolveEvaluationInsight, AlphaEvolveEvaluationInsights,
                    AlphaEvolveEvaluationScore, AlphaEvolveEvaluationScores,
                    AlphaEvolveProgramEvaluation)
import subprocess
import json
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)

def adaptive_sort_evaluation() -> dict:
  """Evaluates the adaptive sort program candidate."""
  try:
    # Run the compiled benchmark executable
    result = subprocess.run(["./benchmark"], capture_output=True, text=True, check=True)
    output = result.stdout
    logger.info("Benchmark output: %s", output)
    
    data = json.loads(output)
    
    score_value = data.get("performance_score", 0.0)
    
    insights_list = []
    if not data.get("all_correct", False):
      insights_list.append(
          AlphaEvolveEvaluationInsight(
              label="Incorrect Sorting",
              text="The algorithm failed to sort some data correctly."
          )
      )
      score_value = None
      
    scores = [
        AlphaEvolveEvaluationScore(metric="score", score=score_value)
    ]
    
    if insights_list:
      insights = AlphaEvolveEvaluationInsights(insights=insights_list)
      program_evaluation = AlphaEvolveProgramEvaluation(
          scores=AlphaEvolveEvaluationScores(scores=scores), insights=insights)
    else:
      program_evaluation = AlphaEvolveProgramEvaluation(
          scores=AlphaEvolveEvaluationScores(scores=scores))
          
    return program_evaluation.model_dump()
    
  except Exception as e:
    logger.error("Failed to run benchmark: %s", e)
    scores = [
        AlphaEvolveEvaluationScore(metric="score", score=None)
    ]
    insights = AlphaEvolveEvaluationInsights(
        insights=[AlphaEvolveEvaluationInsight(label="Runtime Error", text=str(e))]
    )
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores), insights=insights)
    return program_evaluation.model_dump()
