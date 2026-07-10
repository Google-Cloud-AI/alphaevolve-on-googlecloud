#!/usr/bin/env python3

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

"""
Universal local verification script to test schema compatibility and communication
between an Evaluator Container and the Controller Container without calling
the external AlphaEvolve API or spinning up cloud infrastructure.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

# Add framework source path inside the controller container
sys.path.append("/app/src")
try:
    from alpha_evolve.experiment import AlphaEvolveExperiment
    from alpha_evolve.models import AlphaEvolveProgramEvaluation
except ImportError as e:
    print(f"[ERROR] Could not import alpha_evolve modules from /app/src: {e}")
    print("Ensure you are running this script inside the Controller Container.")
    sys.exit(1)

def verify_evaluator_output_in_controller():
    print("==========================================================")
    print("Verifying Evaluator Container Output in Controller Container")
    print("==========================================================")
    
    exp_name = os.environ.get("_USER_EXPERIMENT_NAME", "signal_processing")
    job_id = os.environ.get("_JOB_ID", "test-job")
    result_path = f"/mnt/disks/share/{exp_name}/program_candidates/{job_id}/program_candidate_result.json"

    print(f"Reading Evaluator output from shared volume:\n -> {result_path}")
    
    if not os.path.exists(result_path):
        print(f"[ERROR] File not found at {result_path}!")
        print("Ensure Step 3 (Evaluator Container execution) ran and completed successfully first.")
        sys.exit(1)

    with open(result_path, "r") as f:
        eval_result = json.load(f)
        
    print("\n[SUCCESS] Loaded evaluation JSON from shared volume:")
    print(json.dumps(eval_result, indent=2))

    print("\n----------------------------------------------------------")
    print("Testing Schema Validation against AlphaEvolveProgramEvaluation")
    print("----------------------------------------------------------")
    
    try:
        # Extract the 'evaluation' field if present (matching worker wrapper), or validate root dictionary
        eval_dict = eval_result.get("evaluation", eval_result)
        validated_eval = AlphaEvolveProgramEvaluation.model_validate(eval_dict)
        print("[SUCCESS] Pydantic schema validation PASSED! Structure conforms to AlphaEvolve API specs.")
    except Exception as schema_err:
        print(f"\n[ERROR] Schema Validation Failed! The evaluation JSON structure is malformed or invalid:\n{schema_err}")
        sys.exit(1)

    print("\n----------------------------------------------------------")
    print("Testing Controller Ingestion & Submission Flow")
    print("----------------------------------------------------------")
    
    # Patch AlphaEvolveClient so NO external API requests are made
    with patch("alpha_evolve.experiment.AlphaEvolveClient") as MockClient:
        mock_client = MockClient.return_value
        
        # Initialize the experiment controller inside the container environment
        exp = AlphaEvolveExperiment(
            ae_client=mock_client,
            evaluator_function=lambda x: None,
            max_programs_evaluated=10,
        )
        exp.experiment_name = "test-experiment-scope"
        
        # Simulate payload constructed by ResultsListener worker
        submission_payload = [{
            "program": "test-experiment-scope/seed-candidate",
            "lock_token": "dummy-token",
            "evaluation": eval_dict
        }]
        
        try:
            exp.submit_program_evaluations(submission_payload)
            
            mock_client.submit_program_evaluations.assert_called_once_with(
                "test-experiment-scope", submission_payload
            )
            print("\n[SUCCESS] Controller Container validated and ingested Evaluator Container output!")
            print("Both actual Docker containers communicated successfully without calling the AE API or Cloud Batch.")
        except Exception as e:
            print(f"\n[ERROR] Controller failed to ingest evaluation data: {e}")
            sys.exit(1)

if __name__ == "__main__":
    verify_evaluator_output_in_controller()
