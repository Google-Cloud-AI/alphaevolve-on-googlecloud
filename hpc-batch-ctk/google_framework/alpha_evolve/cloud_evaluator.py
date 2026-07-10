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

"""Cloud evaluator worker for circle packing, using Pub/Sub and Cloud Batch."""

import importlib
import json
import logging
import os
import sys
import time

from utils import create_full_programs_path, get_program_candidate_result_path, sanitize_evaluation_scores


# Configuration from environment variables (set by Cloud Batch)
PROJECT_ID = os.environ.get("_PROJECT_ID")
JOB_ID = os.environ.get("_JOB_ID", "0")  # Default to "0" if not set
CANDIDATE_PROGRAM_ID = os.environ.get("_CANDIDATE_PROGRAM_ID")
PROGRAMS_DIR = os.environ.get("_PROGRAMS_DIR")
MOUNT_PATH = os.environ.get("_MOUNT_PATH")
CLIENT_EVALUATOR_SCRIPT = os.environ.get("_CLIENT_EVALUATOR_SCRIPT")
CLIENT_EVALUATOR_METHOD = os.environ.get("_CLIENT_EVALUATOR_METHOD")
USER_EXPERIMENT_NAME = os.environ.get("_USER_EXPERIMENT_NAME")

# Set up logging
logging.basicConfig(
    level=logging.INFO, format=f"[Evaluator {JOB_ID}] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def run_worker(evaluator):
  """Pulls an evaluation task, runs the evaluation, and stores the results.

  This function checks for a program candidate data file based on the JOB_ID,
  loads the program, executes the circle_packing_evaluation, and writes
  the results back to a JSON file in the same job-specific directory.

  Args:
    evaluator: A callable (synchronous or asynchronous function) that takes
      the program candidate dictionary and returns an evaluation dictionary
  """
  logger.info("Worker started.")

  if not PROJECT_ID or PROJECT_ID == "your-gcp-project-id":
    logger.error("PROJECT_ID environment variable not set. Worker exiting.")
    return
  
  program_dir = create_full_programs_path(os.path.join(MOUNT_PATH, USER_EXPERIMENT_NAME), PROGRAMS_DIR, JOB_ID)
  program_candidate_file_path = os.path.join(program_dir, "program_candidate_data.json")

  logger.info("Attempting to pull candidate program from %s...", program_candidate_file_path)

  if os.path.exists(program_candidate_file_path):
    with open(program_candidate_file_path, "r") as f:
      program_candidate = json.load(f)
    
    program_name = program_candidate.get("name", "unknown")
    logger.info("Successfully loaded program_candidate: %s (ID: %s)", program_name, CANDIDATE_PROGRAM_ID)

    logger.info("Evaluating program %s...", CANDIDATE_PROGRAM_ID)

    try:
      # RUN THE ACTUAL EVALUATION
      start_eval = time.time()
      evaluation = evaluator()
      eval_time = time.time() - start_eval
      status = "SUCCESS"

      logger.info("Evaling done for %s: %s", CANDIDATE_PROGRAM_ID, evaluation)
      evaluation = sanitize_evaluation_scores(evaluation)

      valid_keys = {"scores", "insights"}
      submission_eval = {
          k: v for k, v in evaluation.items() if k in valid_keys
      }
    except Exception as e:
      logger.exception("Exception during evaluation of program %s", CANDIDATE_PROGRAM_ID)
      return

    # Prepare result payload
    payload = {
        "name": program_name,
        "lockToken": program_candidate["lockToken"],
        "evaluation": submission_eval,
        "eval_time": eval_time,
        "task_index": JOB_ID
    }
    result_file_path = get_program_candidate_result_path(program_dir)

    with open(result_file_path, "w") as f:
      json.dump(payload, f, indent=4)
    logger.info(
        "Result for %s successfully written to %s.",
        CANDIDATE_PROGRAM_ID,
        result_file_path,
    )
  
  else:
    logger.info("No program candidate file found at %s.", program_candidate_file_path)
  
  logger.info("Worker finished.")


if __name__ == "__main__":  
  module_name = CLIENT_EVALUATOR_SCRIPT
  evaluator_name = CLIENT_EVALUATOR_METHOD

  try:
    # Add current directory to path to help find the module
    script_path = CLIENT_EVALUATOR_SCRIPT
    module_dir = os.path.dirname(script_path)
    module_name = os.path.basename(script_path)
      
    if module_dir:
      sys.path.insert(0, module_dir)
    else:
      sys.path.insert(0, os.getcwd())
      
    # Add /app/src to path if it exists (container environment)
    container_project_root = "/app/src"
    if os.path.exists(container_project_root) and container_project_root not in sys.path:
        sys.path.append(container_project_root)
        
    module = importlib.import_module(module_name)
    evaluator = getattr(module, evaluator_name)
    logger.info("Successfully loaded evaluator '%s' from module '%s'", evaluator_name, module_name)
  except ImportError:
    logger.exception("Failed to import module '%s'", module_name)
    sys.exit(1)
  except AttributeError:
    logger.exception("Failed to find evaluator function '%s' in module '%s'", evaluator_name, module_name)
    sys.exit(1)

  run_worker(evaluator)

