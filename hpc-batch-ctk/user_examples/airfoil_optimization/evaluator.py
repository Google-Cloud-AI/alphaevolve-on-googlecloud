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

import json
import logging
import os
import shutil
import sys
from pathlib import Path
import numpy as np

from typing import Any, Mapping

# Import the local Parameters from the copied src
from third_party.optimization.optimization import Parameters

from alpha_evolve.models import (
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveProgramEvaluation,
)

logger = logging.getLogger(__name__)

AIRFOIL_EVALUATION_METRIC = "lift_to_drag_ratio"

def _load_initial_program():
    with open(os.path.join(os.path.dirname(__file__), "main.py"), "r") as f:
        return f.read()

INITIAL_PROGRAM_CODE = _load_initial_program()

def evaluate(eval_inputs: Mapping[str, Any] = None) -> dict:
    """Scoring interface called by the AlphaEvolve worker harness.
    
    This function loads the candidate 'main.py', runs its 'evaluate' method
    (which runs the evolved optimize_airfoil loop with a budget of 20 simulations),
    and handles all scoring, logging, errors, and physical file cleanups.
    """
    # Read candidate metadata to get a unique ID (program_name)
    metadata_path = "program_candidate_data.json"
    try:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        raw_program_name = metadata.get("name", "unknown")
        program_name = raw_program_name.split("/")[-1]
        logger.info("Parsed program ID: %s (from raw name: %s)", program_name, raw_program_name)
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

    score_value: float | None = None
    insights_list: list[AlphaEvolveEvaluationInsight] = []

    # Configure isolated directories for this worker to prevent parallel crashes
    cases_folder = Path(f"ae_cases/{program_name}")
    csv_path = Path(f"ae_results/{program_name}.csv")
    
    run_parameters = Parameters(
        run_name=f"ae_{program_name}",
        cases_folder=cases_folder,
        template_path=Path("third_party/openfoam_template"), # Local relative path
        is_debug=True,
        csv_path=csv_path,
        fluid_velocity=np.array([99.6194698092, 8.7155742748, 0]), # 5-degree baseline
    )

    try:
        # Execute candidate's code to load evaluate function
        exec_namespace = {
            "np": np, 
            "Parameters": Parameters,
            "sys": sys,
            "Path": Path
        }
        exec(code, exec_namespace)
        
        evaluate_func = exec_namespace.get("evaluate")

        if callable(evaluate_func):
            # Run the candidate's evaluate loop
            best_x, best_score = evaluate_func(run_parameters, max_successful_simulations=10, max_total_simulations=100)
            
            # best_score is -abs(cl/cd). AlphaEvolve maximizes, so we return positive Cl/Cd.
            if best_score != float('inf') and best_score != float('-inf') and best_score is not None:
                score_value = float(-best_score) # convert to positive Cl/Cd
                logger.info(f"Evaluation successful: Best Cl/Cd = {score_value}")
                
                # Save the best CST parameters to GCS share path for polar plotting post-experiment
                try:
                    mount_path = os.environ.get("_MOUNT_PATH")
                    user_exp_name = os.environ.get("_USER_EXPERIMENT_NAME")
                    if mount_path and user_exp_name:
                        gcs_best_x_dir = Path(mount_path) / user_exp_name / "best_x"
                        gcs_best_x_dir.mkdir(parents=True, exist_ok=True)
                        gcs_best_x_path = gcs_best_x_dir / f"{program_name}.json"
                        
                        with open(gcs_best_x_path, "w") as f:
                            json.dump({
                                "program_name": program_name,
                                "score": score_value,
                                "best_x": best_x.tolist()
                            }, f, indent=2)
                        logger.info(f"Saved best CST parameters to {gcs_best_x_path}")
                except Exception as ex:
                    logger.warning(f"Failed to save best CST parameters to GCS: {ex}")
            else:
                score_value = -1e12
                insights_list.append(
                    AlphaEvolveEvaluationInsight(
                        label="No Valid Airfoil Found",
                        text="The optimization algorithm failed to find any airfoil that converged within the 20-simulation budget.",
                    )
                )
        else:
            insights_list.append(
                AlphaEvolveEvaluationInsight(
                    label="Invalid Program Structure",
                    text="The program is missing a callable 'evaluate' function.",
                )
            )

    except Exception as e:
        error_message = f"The program failed during execution with the following error: {e}"
        logger.exception(error_message)
        insights_list.append(
            AlphaEvolveEvaluationInsight(label="Runtime Error", text=error_message)
        )
    finally:
        # CLEANUP: Keep VM/host disk clean by removing intermediate case directories
        if cases_folder.exists():
            logger.info(f"Cleaning up cases directory: {cases_folder}")
            shutil.rmtree(cases_folder)
        if csv_path.exists():
            csv_path.unlink()

    if score_value is not None and (score_value == float('inf') or score_value == float('-inf')):
        score_value = -1e12

    scores = [
        AlphaEvolveEvaluationScore(
            metric=AIRFOIL_EVALUATION_METRIC, score=score_value
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
