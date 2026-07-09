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

import subprocess
import os
import re
import math
from alpha_evolve.models import (
    AlphaEvolveProgramEvaluation,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights
)

def evaluate_program() -> dict:
    insights_list = []
    shared_output_file = "/app/experiment/simulation_output.txt"

    if os.path.exists(shared_output_file):
        # We are running in Cloud Batch, and the cluster-wide MPI simulation was already run!
        with open(shared_output_file, "r") as f:
            output = f.read()
        
        # Check if the output contains compilation errors!
        if "error:" in output or "Compilation failed" in output or "make:" in output:
            insights_list.append(AlphaEvolveEvaluationInsight(
                label="COMPILATION_ERROR",
                text=f"Compilation failed during cluster setup:\n{output}"
            ))
            scores = [AlphaEvolveEvaluationScore(metric="simulation_speed_score", score=None)]
            return AlphaEvolveProgramEvaluation(
                scores=AlphaEvolveEvaluationScores(scores=scores),
                insights=AlphaEvolveEvaluationInsights(insights=insights_list)
            ).model_dump()
    else:
        # Standard local fallback: Compile and run locally on 2 tasks (cores) with N=2000 particles
        compile_process = subprocess.run(["make", "nbody_sim"], capture_output=True, text=True)
        if compile_process.returncode != 0:
            insights_list.append(AlphaEvolveEvaluationInsight(
                label="COMPILATION_ERROR",
                text=f"Compilation failed:\n{compile_process.stderr}"
            ))
            scores = [AlphaEvolveEvaluationScore(metric="simulation_speed_score", score=None)]
            return AlphaEvolveProgramEvaluation(
                scores=AlphaEvolveEvaluationScores(scores=scores),
                insights=AlphaEvolveEvaluationInsights(insights=insights_list)
            ).model_dump()

        try:
            run_process = subprocess.run(["mpirun", "--allow-run-as-root", "-np", "2", "./nbody_sim", "2000"], capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            insights_list.append(AlphaEvolveEvaluationInsight(
                label="RUNTIME_TIMEOUT",
                text="Simulation exceeded maximum execution time of 15 seconds."
            ))
            scores = [AlphaEvolveEvaluationScore(metric="simulation_speed_score", score=None)]
            return AlphaEvolveProgramEvaluation(
                scores=AlphaEvolveEvaluationScores(scores=scores),
                insights=AlphaEvolveEvaluationInsights(insights=insights_list)
            ).model_dump()

        if run_process.returncode != 0:
            insights_list.append(AlphaEvolveEvaluationInsight(
                label="RUNTIME_CRASH",
                text=f"Simulation crashed with exit code {run_process.returncode}:\n{run_process.stderr}"
            ))
            scores = [AlphaEvolveEvaluationScore(metric="simulation_speed_score", score=None)]
            return AlphaEvolveProgramEvaluation(
                scores=AlphaEvolveEvaluationScores(scores=scores),
                insights=AlphaEvolveEvaluationInsights(insights=insights_list)
            ).model_dump()
        output = run_process.stdout
    time_match = re.search(r"TIME_MS:\s+([0-9.]+)", output)
    energy_match = re.search(r"ENERGY_DRIFT:\s+([0-9.e+-]+)", output)
    
    if not time_match or not energy_match:
        insights_list.append(AlphaEvolveEvaluationInsight(
            label="PARSING_ERROR",
            text=f"Failed to parse performance metrics from output:\n{output}"
        ))
        scores = [AlphaEvolveEvaluationScore(metric="simulation_speed_score", score=None)]
        return AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(scores=scores),
            insights=AlphaEvolveEvaluationInsights(insights=insights_list)
        ).model_dump()

    execution_time = float(time_match.group(1))
    energy_drift = float(energy_match.group(1))
    
    # 4. Apply Physics Safeguard (Energy conservation must be < 1e-4)
    if energy_drift > 1e-4 or math.isnan(energy_drift):
        insights_list.append(AlphaEvolveEvaluationInsight(
            label="PHYSICS_VIOLATION",
            text=f"Simulation violated energy conservation! Energy Drift: {energy_drift:.6f} (must be < 0.0001)."
        ))
        scores = [AlphaEvolveEvaluationScore(metric="simulation_speed_score", score=None)]
        return AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(scores=scores),
            insights=AlphaEvolveEvaluationInsights(insights=insights_list)
        ).model_dump()

    # 5. Construct structured score and evaluation
    scores = [
        AlphaEvolveEvaluationScore(
            metric="simulation_speed_score",
            score=-execution_time
        )
    ]
    
    if insights_list:
        program_evaluation = AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(scores=scores),
            insights=AlphaEvolveEvaluationInsights(insights=insights_list)
        )
    else:
        program_evaluation = AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(scores=scores)
        )
        
    return program_evaluation.model_dump()

if __name__ == "__main__":
    import json
    print(json.dumps(evaluate_program()))
