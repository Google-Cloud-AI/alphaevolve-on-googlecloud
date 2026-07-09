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

"""Execution engine implementations for AlphaEvolve."""

import asyncio
import inspect
import json
import logging
import os
from typing import Optional, Callable, Any, Dict

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1
from google.cloud import storage

from .workers import ResultsListener
from .engine import ExecutionEngine
from .experiment import AlphaEvolveExperiment
from .utils import create_full_programs_path, get_program_candidate_file_path, get_job_id_from_program_name, upload_entire_payload_gcs
from .cloud_batch import BatchClient


logger = logging.getLogger(__name__)



class DistributedEngine(ExecutionEngine):
  """Distributed execution using Google Cloud Pub/Sub.

  Supports batch_params dictionary for on-demand worker provisioning
  (e.g., Cloud Batch).

  Attributes:
    project_id: Google Cloud Project ID.
    batch_notification_sub_name: Pub/Sub subscription name for receiving batch job state changes.
    subscriber: The Pub/Sub subscriber client.
    batch_notification_sub_path: The Pub/Sub subscription path.
    listener_future: The future for the results listener.
    bucket_name: GCS bucket name for storing program data.
    programs_dir: The directory to save the programs to.
    batch_params: Arguments passed to the batch job creation block.
    user_experiment_name: The name of the user experiment.
  """

  def __init__(
      self,
      project_id: str,
      batch_notification_sub: str,
      bucket_name: str,
      programs_dir: str,
      batch_params: Dict[str, Any],
      user_experiment_name: str,
  ):
    """Initializes the DistributedEngine.

    Args:
      project_id: Google Cloud Project ID.
      batch_notification_sub: Pub/Sub subscription name for receiving batch job state changes.
      bucket_name: GCS bucket name for storing program data.
      programs_dir: The directory to save the programs to.
      batch_params: Arguments natively mapped explicitly into `create_batch_job`.
      user_experiment_name: The name of the user experiment.
    """
    self.project_id = project_id
    self.batch_notification_sub_name = batch_notification_sub

    self.batch_params = batch_params
    self.batch_client = BatchClient()

    self.subscriber = pubsub_v1.SubscriberClient()

    self.batch_notification_sub_path = self.subscriber.subscription_path(
        project_id, batch_notification_sub
    )

    self.listener_future = None
    self.bucket_name = bucket_name

    self.programs_dir = programs_dir
    self.user_experiment_name = user_experiment_name

  async def start(self, experiment: AlphaEvolveExperiment):
    """Starts the results listener for the distributed engine.

    Args:
      experiment: The AlphaEvolveExperiment instance.
    """
    logger.info("Starting DistributedEngine on project %s.", self.project_id)
    listener = ResultsListener(
        experiment, self.subscriber, self.batch_notification_sub_path, self.bucket_name, self.programs_dir, self.batch_client, self.user_experiment_name
    )
    self.listener_future = listener.start()

  async def dispatch(self, program: Dict[str, Any]):
    """Dispatches a program via Pub/Sub, running pre-dispatch if configured.

    Args:
      program: The program to dispatch.
    """
    candidate_program_id = program.get("name", "unknown").split("/")[-1]
    deployment_name = os.environ.get('_DEPLOYMENT_NAME', 'alpha-evolve')
    job_prefix = f"{deployment_name}-workers"
    job_id = get_job_id_from_program_name(candidate_program_id, job_prefix)
    
    # 1. Execute create_batch_job to provision resources.
    logger.info("Executing create_batch_job for %s", candidate_program_id)
    self.batch_params["job_id"] = job_id
    self.batch_params["candidate_program_id"] = candidate_program_id
    try:
      if inspect.iscoroutinefunction(self.batch_client.create_batch_job):
        await self.batch_client.create_batch_job(**self.batch_params)
      else:
        await asyncio.to_thread(self.batch_client.create_batch_job, **self.batch_params)
    except Exception as e:
      logger.error(
          "PRE-DISPATCH FAILURE: Could not provision worker for %s. Error: %s",
          candidate_program_id,
          e,
          exc_info=True,
      )
      # Re-raise so the SamplingWorker knows this program wasn't dispatched.
      raise
  
    # 2. Publish to the GCS Bucket ONLY if provisioning succeeded.
    try:
      data = json.dumps(program).encode("utf-8")
      upload_entire_payload_gcs(self.bucket_name, self.programs_dir, job_id, candidate_program_id, data, self.user_experiment_name)
      logger.info(
          "Successfully dispatched program %s to GCS Bucket.", candidate_program_id
      )
    except google_exceptions.GoogleAPICallError as e:
      logger.error(
          "GCS BUCKET PUBLISH FAILURE: for program %s. Error: %s", candidate_program_id, e
      )
      raise

  async def stop(self):
    """Stops the results listener."""
    logger.info("Stopping DistributedEngine.")
    if self.listener_future:
      self.listener_future.cancel()
      self.listener_future = None
