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

"""Worker classes for sampling and evaluating programs in the AlphaEvolve system."""

import asyncio
import json
import logging
import os
import time
import traceback

from .cloud_batch import BatchClient
from .engine import ExecutionEngine
from .experiment import AlphaEvolveExperiment
from .utils import (
    archive_full_program_dir_gcs,
    create_full_programs_path,
    get_job_id_from_program_name,
    get_program_candidate_file_path,
    get_program_candidate_result_path,
    read_file_from_gcs,
    process_and_log_evaluation,
    check_duplicate_evaluation,
)

logger = logging.getLogger(__name__)


class SamplingWorker:
  """A worker that polls for new programs and dispatches them via an ExecutionEngine.

  Since acquire_programs is sync but fast, we call it directly but
  must sleep if no work is found to yield control to other tasks.

  Attributes:
    experiment: The AlphaEvolveExperiment instance.
    engine: The ExecutionEngine instance.
    poll_interval: The interval to wait between polling for new programs.
  """

  def __init__(
      self,
      experiment: AlphaEvolveExperiment,
      engine: ExecutionEngine,
      poll_interval=4,
  ):
    self.experiment = experiment
    self.ae_client = experiment.client
    self.engine = engine
    self.poll_interval = poll_interval
    # TODO: change to a higher number when ttl issue is fixed.
    # Number of programs to acquire per call to AlphaEvolve API
    self.num_acquired_programs_per_call = 5

  async def run(self):
    try:
      while True:
        # Note: this is a fast sync call.
        logger.info("Trying to acquire programs")
        response = self.experiment.acquire_programs(
            self.num_acquired_programs_per_call
        )
        if response and "programs" in response:
          programs = response["programs"]
          self.experiment.stats["num_programs_generated"] += len(programs)
          for program in programs:
            logger.info("  Program acquired: %s", program['name'])
            # Dispatch via the abstracted engine (could be local queue or Pub/Sub)
            await self.engine.dispatch(program)
        else:
          # No program found: we sleep to pause this loop
          logger.info("  No programs acquired, retrying...")
          await asyncio.sleep(self.poll_interval)

    except asyncio.CancelledError:
      pass
    except Exception as e:
      if any(err in str(e) for err in ["403", "401", "Permission", "Forbidden", "denied"]):
        logger.error("SamplingWorker encountered unrecoverable permission error. Stopping worker: %s", e)
        raise e
      logger.error("SamplingWorker failed: %s", e)
      await asyncio.sleep(self.poll_interval)





class ResultsListener:
  """Listens for results from Pub/Sub and submits them to AlphaEvolve.

  This class subscribes to a Pub/Sub topic where distributed evaluators
  publish their results. It processes these results and uses the
  AlphaEvolveExperiment client to submit the evaluations.

  Attributes:
    experiment: The AlphaEvolveExperiment instance.
    ae_client: The AlphaEvolveExperiment client.
    subscriber: The Pub/Sub subscriber client.
    batch_notification_subscription: The name of the Pub/Sub subscription for batch job state changes.
    bucket_name: GCS bucket name for storing program data.
    programs_dir: The directory to save the programs to.
  """

  def __init__(
      self,
      experiment: AlphaEvolveExperiment,
      subscriber,
      batch_notification_subscription: str,
      bucket_name: str,
      programs_dir: str,
      batch_client: BatchClient,
      user_experiment_name: str,
  ):
    """Initializes the ResultsListener.

    Args:
      experiment: The AlphaEvolveExperiment instance.
      subscriber: The Pub/Sub subscriber client instance.
      batch_notification_subscription: The name of the Pub/Sub subscription for batch job state changes.
      bucket_name: GCS bucket name for storing program data.
      programs_dir: The directory to save the programs to.
      batch_client: The BatchClient instance for managing jobs.
      user_experiment_name: The name of the user experiment.
    """
    self.experiment = experiment
    self.ae_client = experiment.client
    self.subscriber = subscriber
    self.batch_notification_subscription = batch_notification_subscription
    self.bucket_name = bucket_name
    self.programs_dir = programs_dir
    self.batch_client = batch_client
    self.user_experiment_name = user_experiment_name

  def callback(self, message):
    """Callback function to process incoming Pub/Sub messages.

    Args:
      message: The Pub/Sub message received.
    """
    try:
      attributes = message.attributes
      new_state = attributes.get("NewJobState")
      
      if new_state:
        job_name = attributes.get("JobName")
        job_id = job_name.split("/")[-1] 
        
        if new_state not in ["SUCCEEDED", "FAILED"]:
          logger.info(f"Ignoring message for job {job_id} with state {new_state}")
          message.ack()
          return
        
        # Check if this job's program has already been evaluated to prevent duplicate processing
        candidate_program_id = job_id.split("-")[-1]
        if check_duplicate_evaluation(self.bucket_name, self.user_experiment_name, candidate_program_id):
          logger.info(f"[Listener] Program {candidate_program_id} (Job {job_id}) already evaluated in results.csv. Ignoring duplicate message.")
          message.ack()
          return

        blob_path = create_full_programs_path(self.user_experiment_name, self.programs_dir, job_id)
          
        program_name = None
        lock_token = None
        evaluation = None
        eval_time = 0.0
        should_delete_job = False
        result_data = None
        
        if new_state == "SUCCEEDED":
          logger.info(f"✅ Job {job_id} SUCCEEDED. Triggering result collection...")
          program_result_path = get_program_candidate_result_path(blob_path)
          
          for attempt in range(5):
            result_data = read_file_from_gcs(self.bucket_name, program_result_path)
            if result_data is not None:
              break
            time.sleep(attempt + 1)
            
          if result_data is not None:
            program_name = result_data.get("name")
            lock_token = result_data.get("lockToken")
            evaluation = result_data.get("evaluation")
            eval_time = result_data.get("eval_time", 0.0)
            should_delete_job = os.getenv("_DELETE_SUCCEEDED_JOBS", "true").lower() == "true"
          else:
            logger.error(f"Error: Failed to read result data for job {job_id}")
            
        elif new_state == "FAILED":
          logger.error(f"❌ Job {job_id} FAILED.")
          
        # Handle failure or missing results
        if new_state == "FAILED" or (new_state == "SUCCEEDED" and result_data is None):
          program_data_path = get_program_candidate_file_path(blob_path)
          program_data = read_file_from_gcs(self.bucket_name, program_data_path)
          
          if program_data is None:
            logger.error(f"CRITICAL: Could not read program input data from GCS for job {job_id}. Cannot report failure to AlphaEvolve.")
            message.ack()
            return
            
          program_name = program_data["name"]
          lock_token = program_data["lockToken"]
          
          scores_list = [{"metric": m, "score": None} for m in self.experiment.metrics_list] if self.experiment.metrics_list else []
          
          if new_state == "FAILED":
            scores_list.append({"metric": "compile_success", "score": 0.0})
            evaluation = {
                "scores": {"scores": scores_list},
                "insights": {"insights": [{"label": "CRITICAL_ERROR", "text": "Evaluation failed"}]}
            }
          else: # SUCCEEDED but missing results - Uncommon case
            evaluation = {
                "scores": {"scores": scores_list},
                "insights": {"insights": []}
            }
          eval_time = 0.0

        # Common submission logic
        candidate_program_id = program_name.split("/")[-1] if program_name else "unknown"
        
        # Filter evaluation results to only include valid keys
        valid_keys = {"scores", "insights"}
        submission_eval_filtered = {}
        if isinstance(evaluation, dict):
          submission_eval_filtered = {
              k: v for k, v in evaluation.items() if k in valid_keys
          }
        logger.info("Filtered evaluation result: %s", submission_eval_filtered)
        
        submission_eval = {
            "program": program_name,
            "lock_token": lock_token,
            "evaluation": submission_eval_filtered,
        }
        
        logger.info(
            "[Listener] DEBUG payload: program=%s, lock_token=%s",
            program_name,
            lock_token,
        )
        logger.info(
            "[Listener] Submitting result for: %s | Score %s",
            program_name,
            submission_eval_filtered,
        )
        # Verify candidate belongs to the current experiment scope
        # This happends when some experiments are terminated and pub/sub still have messages from the previous experiment
        if self.experiment.experiment_name not in program_name:
            logger.warning(
                "[Listener] Skipping submission: program belongs to a foreign experiment: %s vs %s",
                program_name,
                self.experiment.experiment_name
            )
            message.ack()
            return

        try:    
            self.experiment.submit_program_evaluations(
                [submission_eval]
            )
            self.experiment.stats["num_programs_evaluated"] += 1
            logger.info(
                "[Listener] Submitted results for: %s programs.",
                self.experiment.stats["num_programs_evaluated"],
            )
        except Exception as e:
            if "FAILED_PRECONDITION" in str(e) or "Precondition check failed" in str(e):
                logger.info("[Listener] Unrecoverable precondition error. Acknowledging message.")
                message.ack()
            else:
                # For other unexpected transient errors, trigger redelivery
                message.nack()
        
        # Moved here to log only once if we fail to submit the evaluation to AE and we retry
        process_and_log_evaluation(
            candidate_program_id, evaluation, eval_time, logger, self.bucket_name, self.user_experiment_name, self.experiment.metrics_list
        )
        
        # Move the evaluation data to the old evaluations folder
        archive_full_program_dir_gcs(self.bucket_name, self.user_experiment_name, self.programs_dir, job_id)
        
        if should_delete_job:
          self.batch_client.delete_batch_job(job_name)
        elif new_state == "SUCCEEDED":
          logger.info("Skipping deletion for job %s (_DELETE_SUCCEEDED_JOBS is false)", job_id)
          
      message.ack()
    except Exception as e:
      logger.error("[Listener] Error processing result: %s", e, exc_info=True)
      message.nack()

  def start(self):
    """Starts the Pub/Sub subscriber to listen for messages."""
    logger.info("[Listener] Subscribing to: %s", self.batch_notification_subscription)
    return self.subscriber.subscribe(
        self.batch_notification_subscription, callback=self.callback
    )
