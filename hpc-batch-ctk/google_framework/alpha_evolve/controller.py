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
"""Main controller loop for the AlphaEvolve experiment orchestration."""

import asyncio
import inspect
import json
import logging
import os
import re
from typing import Any, Callable, Dict, Optional

from .client import AlphaEvolveClient
from .execution import ExecutionEngine, DistributedEngine
from .experiment import AlphaEvolveExperiment
from .utils import read_file_from_gcs, write_file_to_gcs, delete_file_from_gcs, get_positive_int_env
from .workers import SamplingWorker

logger = logging.getLogger(__name__)


class AlphaEvolveController:
  """Controller for AlphaEvolve experiments, managing client, experiment, and engine.
  
  Attributes:
    client: The AlphaEvolveClient instance.
    experiment: The AlphaEvolveExperiment instance.
    mode: The mode of the controller, either 'dev' or 'batch'.
    bucket_name: The name of the GCS bucket to use for storing experiment data.
  """

  def __init__(self, client: Optional[AlphaEvolveClient] = None):
    self.experiment: Optional[AlphaEvolveExperiment] = None

    self.project_id = os.getenv("_PROJECT_ID")
    if not self.project_id or self.project_id == "gcp-project-id":
        raise ValueError("Project ID not found in environment (_PROJECT_ID).")
    
    # Fallback for Client
    if client:
        self.client = client
    else:
        logger.info("Client not provided, creating from environment.")
        location = os.getenv("_LOCATION", "global")
        collection = os.getenv("_COLLECTION", "default_collection")
        engine_name = os.getenv("_ENGINE", "alpha-evolve-experiment-engine")
        assistant = os.getenv("_ASSISTANT", "alpha-evolve-experiment-assistant")
        base_url = os.getenv("_BASE_URL", "discoveryengine.googleapis.com")
            
        self.client = AlphaEvolveClient(
            project_id=self.project_id,
            location=location,
            collection=collection,
            engine=engine_name,
            assistant=assistant,
            base_url=base_url,
        )
    
    # Create Engine in __init__
    self.evaluation_mode = os.getenv("_EVALUATION_MODE", "batch").lower()
    self.bucket_name = os.getenv("_CLOUD_BUCKET_NAME")
    if not self.bucket_name or self.bucket_name == "my-bucket-name":
        raise ValueError("Bucket name not found in environment (_CLOUD_BUCKET_NAME).")
    programs_dir = os.getenv("_PROGRAMS_DIR", "evaluations")
    self.user_experiment_name = os.getenv("_USER_EXPERIMENT_NAME")

    if self.evaluation_mode == "batch":
        logger.info("ENGINE: Distributed (Pub/Sub + Cloud Batch) created by Controller in __init__")

        # Validate _EVALUATION_PROVISIONING_MODEL
        prov_model = os.environ.get("_EVALUATION_PROVISIONING_MODEL")
        if prov_model not in ["STANDARD", "SPOT", "FLEX_START"]:
            raise ValueError(f"Invalid _EVALUATION_PROVISIONING_MODEL '{prov_model}'. Valid values are 'STANDARD', 'SPOT', 'FLEX_START'.")
        
        # If FLEX_START, validate that the machine type is supported (strictly GPU accelerator or H4D instances)
        if prov_model == "FLEX_START":
            machine_type = os.environ.get("_EVALUATION_MACHINE_TYPE")
            if not machine_type:
                raise ValueError("Machine type not found in environment (_EVALUATION_MACHINE_TYPE).")
            supported_prefixes = ["g2-", "g4-", "a2-", "a3-", "a4-", "a4x-", "n1-", "h4d-"]
            if not any(machine_type.startswith(prefix) for prefix in supported_prefixes):
                raise ValueError(
                    f"Invalid _EVALUATION_MACHINE_TYPE '{machine_type}' for DWS FLEX_START. "
                    f"FLEX_START on Cloud Batch requires GPU accelerator or H4D VM instances. "
                    f"Supported families include: G2, G4, A2, A3, A4, A4x, N1, and H4D."
                )
        
        batch_params = {}
        machine_type = os.environ.get("_EVALUATION_MACHINE_TYPE")
        if machine_type and machine_type.startswith("n1-"):
            accelerator_count = get_positive_int_env("_ACCELERATOR_COUNT", "1")
            accelerator_type = os.getenv("_ACCELERATOR_TYPE", "nvidia-tesla-t4")
            supported_n1_gpus = ["nvidia-tesla-t4", "nvidia-tesla-p4", "nvidia-tesla-v100", "nvidia-tesla-p100"]
            if accelerator_type not in supported_n1_gpus:
                raise ValueError(
                    f"Invalid _ACCELERATOR_TYPE '{accelerator_type}' for N1 machine type. "
                    f"Supported types are: {', '.join(supported_n1_gpus)}."
                )
            batch_params["accelerator_count"] = accelerator_count
            batch_params["accelerator_type"] = accelerator_type
            
        pubsub_sub = os.getenv("_PUBSUB_SUBSCRIPTION")
        self.engine = DistributedEngine(
            project_id=self.project_id,
            batch_notification_sub=pubsub_sub,
            bucket_name=self.bucket_name,
            programs_dir=programs_dir,
            batch_params=batch_params,
            user_experiment_name=self.user_experiment_name
        )
    else:
        raise ValueError(f"Invalid evaluation mode: {self.evaluation_mode}. Must be 'batch'.")

  async def run_loop(
      self,
      evaluator_function: Optional[Callable] = None,
      exp_config: Optional[Dict[str, Any]] = None,
      initial_program: Optional[Dict[str, Any]] = None,
      experiment: Optional[AlphaEvolveExperiment] = None,
      num_samplers: Optional[int] = None
  ):
    """Starts or resumes the experiment and the chosen ExecutionEngine.

    Args:
      evaluator_function: The evaluation function (required if experiment is None).
      exp_config: The experiment configuration (required if experiment is None).
      initial_program: The initial program content (required if experiment is None).
      experiment: Optional AlphaEvolveExperiment instance.
      num_samplers: Optional number of samplers to use.
      
    Returns:
      The AlphaEvolveExperiment instance.
    """
    # Fallback for Experiment (Create or Resume)

    if experiment:
        self.experiment = experiment
    else:
        logger.info("Experiment not provided, resolving create/resume state.")
        if not evaluator_function or not exp_config or not initial_program:
            raise ValueError("Must provide evaluator_function, exp_config, and initial_program if experiment is None")

        # Validate run_settings
        run_settings = exp_config.get("run_settings")
        if run_settings and isinstance(run_settings, dict):
            max_programs = run_settings.get("max_programs")
            concurrency = run_settings.get("concurrency")
            if max_programs is not None:
                try:
                    if int(max_programs) <= 0:
                        raise ValueError(f"run_settings.max_programs must be strictly positive, got {max_programs}")
                except (ValueError, TypeError):
                    raise ValueError(f"run_settings.max_programs must be an integer, got {max_programs}")
            if concurrency is not None:
                try:
                    if int(concurrency) <= 0:
                        raise ValueError(f"run_settings.concurrency must be strictly positive, got {concurrency}")
                except (ValueError, TypeError):
                    raise ValueError(f"run_settings.concurrency must be an integer, got {concurrency}")

            # Validate and translate max_duration
            max_duration = run_settings.get("max_duration")
            max_hours = None
            if max_duration is not None:
                try:
                    max_hours = int(max_duration)
                except (ValueError, TypeError):
                    raise ValueError(f"run_settings.max_duration must be an integer hour (1-24), got {max_duration!r}")
                if max_hours < 1 or max_hours > 24:
                    raise ValueError(f"run_settings.max_duration must be between 1 and 24 hours inclusive, got {max_duration}")
                # Translate to protobuf Duration string (seconds)
                run_settings["max_duration"] = f"{max_hours * 3600}s"

            # Validate and translate idle_timeout
            idle_timeout = run_settings.get("idle_timeout")
            if idle_timeout is not None:
                try:
                    idle_hours = int(idle_timeout)
                except (ValueError, TypeError):
                    raise ValueError(f"run_settings.idle_timeout must be an integer hour, got {idle_timeout!r}")
                if idle_hours < 1:
                    raise ValueError(f"run_settings.idle_timeout must be at least 1 hour, got {idle_timeout}")
                effective_max = max_hours if max_hours is not None else 6
                if idle_hours >= effective_max:
                    raise ValueError(f"run_settings.idle_timeout ({idle_timeout}) must be strictly less than run_settings.max_duration ({effective_max})")
                # Translate to protobuf Duration string (seconds)
                run_settings["idle_timeout"] = f"{idle_hours * 3600}s"

        max_programs_evaluated = get_positive_int_env("_MAX_PROGRAMS_EVALUATED", "10")
        
        # Check for resume state on GCS
        experiment_data = read_file_from_gcs(self.bucket_name, f"{self.user_experiment_name}/current_experiment.json")
            
        self.experiment = AlphaEvolveExperiment(self.client, evaluator_function, max_programs_evaluated)
        
        if experiment_data:
            logger.info("Resuming experiment from GCS state.")
            self.experiment.session_name = experiment_data["session_name"]
            self.experiment.experiment_name = experiment_data["experiment_name"]
            self.experiment.initial_program = experiment_data["initial_program"]
            try:
                self.experiment.resume_experiment()
            except Exception as e:
                if "Experiment is failed" in str(e):
                    logger.info("Deleting failed/unresumable experiment state file from GCS.")
                    delete_file_from_gcs(self.bucket_name, f"{self.user_experiment_name}/current_experiment.json")
                raise e
            
            experiment_state = self.experiment.get_experiment().get("state")
            if experiment_state == "COMPLETED":
                logger.info("Experiment is completed. No further action can be taken to resume it.")
                delete_file_from_gcs(self.bucket_name, f"{self.user_experiment_name}/current_experiment.json")
                return
        else:
            logger.info("Creating new experiment.")
            try:
                self.experiment.create_experiment(exp_config)
            except Exception as e:
                logger.error("Failed to create experiment: %s", e)
                raise Exception(f"Failed to create experiment at AlphaEvolve API. Please verify that your Engine and Session are correctly configured, and that your GCP project is allow-listed to access AlphaEvolve. Details: {e}") from e
            
            try:
                self.experiment.create_initial_program(initial_program)
            except Exception as e:
                if "Unexpected content on the same line as EVOLVE-BLOCK-START" in str(e):
                    error_msg = "EVOLVE-BLOCK-START markers must be on their own lines without leading or trailing text."
                    logger.error("Failed to create initial program: %s", error_msg)
                    raise ValueError(error_msg) from e
                elif "INVALID_ARGUMENT" in str(e):
                    error_msg = (
                        "Failed to create initial program due to INVALID_ARGUMENT at AlphaEvolve API. "
                        "This usually indicates that the initial program payload structure or content is invalid. "
                        "Please verify that all file paths are correct and contents are valid for the specified language."
                    )
                    logger.error("Failed to create initial program: %s", error_msg)
                    raise ValueError(error_msg) from e
                else:
                    error_msg = f"Failed to create initial program: {e}"
                    logger.error(error_msg)
                    raise Exception(error_msg) from e
            self.experiment.start_experiment()
            logger.info("Experiment started: %s", self.experiment.experiment_name)
            
            current_experiment = {
                "session_name": self.experiment.session_name,
                "experiment_name": self.experiment.experiment_name,
                "initial_program": initial_program,
            }
            write_file_to_gcs(self.bucket_name, f"{self.user_experiment_name}/current_experiment.json", json.dumps(current_experiment))
 
    # Now we definitely have an experiment and a client in self.
    
    if num_samplers is None:
        num_samplers = get_positive_int_env("_NUM_SAMPLERS", "4")
    
    poll_interval = get_positive_int_env("_POLL_INTERVAL", "4")
        
    evaluator_func = self.experiment.evaluator_client
    client_evaluator_method = evaluator_func.__name__
    
    try:
        function_file = inspect.getfile(evaluator_func)
        client_evaluator_script = os.path.splitext(function_file)[0]
    except Exception as e:
        logger.warning("Could not determine evaluator script path via inspect: %s", e)
        client_evaluator_script = None

    logger.info("Updating batch_params in run_loop")
    region = os.getenv("_REGION", "us-central1")
    self.engine.batch_params.update({
        "client_evaluator_script": client_evaluator_script,
        "client_evaluator_method": client_evaluator_method,
        "region": region,
    })

    # Initialize the engine
    await self.engine.start(self.experiment)

    # Start the Sampler tasks
    logger.info("Starting %d Sampler (polling) tasks.", num_samplers)
    sampler_tasks = [
        asyncio.create_task(SamplingWorker(self.experiment, self.engine, poll_interval=poll_interval).run())
        for _ in range(num_samplers)
    ]

    try:
      # Main wait loop until experiment criteria are met
      while True:
        # We terminate if experiment state is marked as COMPLETE by AE or we reach the specified max programs evaluated
        try:
          if self.experiment.stopping_criteria_met():
            logger.info("Stopping criteria met.")
            # Delete only when Experiment is marked as COMPLETE by AE
            exp_data = self.experiment.get_experiment()
            if exp_data and exp_data.get("state") == "COMPLETED":
              delete_file_from_gcs(self.bucket_name, f"{self.user_experiment_name}/current_experiment.json")
            break
        except Exception as e:
          if "Experiment is FAILED" in str(e):
            logger.info("Deleting failed experiment state file from GCS.")
            delete_file_from_gcs(self.bucket_name, f"{self.user_experiment_name}/current_experiment.json")
          raise e
        await asyncio.sleep(1)

    finally:
      # Graceful shutdown
      logger.info("Shutting down controller...")

      # Stop samplers
      for task in sampler_tasks:
        task.cancel()

      # Stop the engine
      await self.engine.stop()

      # Clean up tasks
      await asyncio.gather(*sampler_tasks, return_exceptions=True)
      logger.info("All workers and samplers terminated.")

  def list_programs(self, params: Dict[str, Any]):
      if not self.experiment:
          raise ValueError("Experiment has not been initialized.")
      return self.experiment.list_programs(params=params)
