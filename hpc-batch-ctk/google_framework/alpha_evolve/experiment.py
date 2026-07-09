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
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .client import AlphaEvolveClient
from .models import AlphaEvolveExperimentState

logger = logging.getLogger(__name__)


class AlphaEvolveExperiment:
    def __init__(
        self,
        ae_client: AlphaEvolveClient,
        evaluator_function: Callable,
        max_programs_evaluated: int,
    ):
        self.stats = {
            "num_programs_generated": 0,
            "num_programs_evaluated": 0,
        }
        self.client = ae_client
        self.evaluator_client = evaluator_function
        self.max_programs_evaluated = max_programs_evaluated
        self.session_name = None
        self.experiment = None
        self.experiment_name = None
        self.metrics_list = None
        self.initial_program = None
        self.initial_program_name = None

    def create_experiment(self, config: Dict[str, Any]):
        logger.info("Creating a new Gemini Enterprise session.")
        self.session_name = self.client.create_session()
        if not self.session_name:
            raise RuntimeError(
                "Failed to create a Gemini Enterprise session (see error logs "
                "above). Check PROJECT_ID, GE_APP_ID, credentials, and that the "
                "Discovery Engine API is enabled."
            )
        logger.info("Created session: " + str(self.session_name))

        logger.info("Creating a new AlphaEvolve experiment")
        self.experiment = self.client.create_experiment(config, self.session_name)
        if self.experiment:
            self.experiment_name = self.experiment["name"]
            logger.info(f"experiment_name: {self.experiment_name}")
        else:
            raise RuntimeError("Failed to create experiment at AlphaEvolve API. Please verify experiment config, that your Engine and Session are correctly configured, and that your GCP project is allow-listed to access AlphaEvolve.")

    def list_programs(self, params: Optional[Dict[str, Any]] = None):
        logger.info(f"Listing programs with params: {params}")
        res = self.client.list_alpha_evolve_programs(self.experiment_name, params)
        return res

    def list_experiments(self, params: Optional[Dict[str, Any]] = None):
        logger.info(f"Listing experiments with params: {params}")
        res = self.client.list_alpha_evolve_experiments(self.session_name, params)
        return res

    def create_initial_program(self, initial_program: Dict[str, Any]):
        logger.info("Creating an initial program")
        
        # Extract metrics for score logging
        scores_data = initial_program.get("evaluation", {}).get("scores", {}).get("scores", [])
        self.metrics_list = [s.get("metric") for s in scores_data if s.get("metric")]
        logger.info("Extracted metrics from initial program: %s", self.metrics_list)

        self.initial_program = self.client.create_initial_program(
            self.experiment_name, initial_program
        )
        if self.initial_program:
            self.initial_program_name = self.initial_program["name"]
            logger.info(self.initial_program_name)

    def start_experiment(self):
        logger.info("Starting an AlphaEvolve experiment")
        experiment = self.client.start_experiment(self.experiment_name)
        logger.info(experiment)
    
    def resume_experiment(self):
        logger.info("Resuming an AlphaEvolve experiment")

        experiment = self.get_experiment()
        if experiment:
            logger.info(f"Experiment state: {experiment.get('state')}")
            self.experiment_name = experiment["name"]
            try:
                # Extract metrics for score logging
                scores_data = self.initial_program.get("evaluation", {}).get("scores", {}).get("scores", [])
                self.metrics_list = [s.get("metric") for s in scores_data if s.get("metric")]
                logger.info("Extracted metrics on resume: %s", self.metrics_list)
            except Exception as e:
                logger.warning("Could not recover initial program metrics: %s", e)

            if experiment.get("state") == AlphaEvolveExperimentState.RUNNING.name:
                logger.info("Experiment is already running")
            elif experiment.get("state") == AlphaEvolveExperimentState.CREATED.name:
                self.start_experiment()
            elif experiment.get("state") == AlphaEvolveExperimentState.PAUSED.name:
                self.client.resume_experiment(self.experiment_name)
                # Poll until the backend is fully RUNNING to prevent FAILED_PRECONDITION
                for attempt in range(10):
                    time.sleep(attempt + 1)
                    experiment = self.get_experiment()
                    if experiment and experiment.get("state") == AlphaEvolveExperimentState.RUNNING.name:
                        logger.info(f"Experiment state successfully transitioned to RUNNING on attempt {attempt + 1}")
                        break
            elif experiment.get("state") == AlphaEvolveExperimentState.COMPLETED.name:
                logger.info("Experiment is completed")
            elif experiment.get("state") == AlphaEvolveExperimentState.FAILED.name:
                logger.info("Experiment is failed. No further action can be taken.")
                raise Exception("Experiment is failed. No further action can be taken to resume it.")
            
        logger.info(experiment)

    def get_experiment(self):
        logger.info("Getting an AlphaEvolve experiment")

        experiment = self.client.get_alpha_evolve_experiment(self.experiment_name)
        if experiment:
            self.experiment_name = experiment["name"]
            
        return experiment

    def evaluator(self):
        result = self.evaluator_client()

        # If result already has the expected structure, return it directly
        if (
            isinstance(result, dict)
            and "scores" in result
            and isinstance(result["scores"], dict)
        ):
            return result

        # Legacy behavior: wrap flat dict into scores list
        evaluation = {
            "scores": {
                "scores": [{"metric": k, "score": v} for (k, v) in result.items()]
            }
        }
        return evaluation

    def acquire_programs(self, desired_programs_count: Optional[int] = 1):
        logger.info("Acquiring programs via Experiment wrapper")
        try:
            experiment = self.get_experiment()
            if experiment:
                if experiment.get("state") == AlphaEvolveExperimentState.PAUSED.name:
                    logger.warning("Experiment is PAUSED. Attempting to automatically resume...")
                    self.resume_experiment()
                elif experiment.get("state") == AlphaEvolveExperimentState.FAILED.name:
                    raise ValueError("Experiment is FAILED. No further action can be taken.")
        except ValueError as e:
            raise e
        except Exception as e:
            logger.warning("Failed to check/resume experiment state before acquisition: %s", e)

        return self.client.acquire_programs(
            self.experiment_name, desired_programs_count
        )

    def submit_program_evaluations(self, evaluation_submissions: List[Dict[str, Any]]):
        logger.info("Submitting program evaluations via Experiment wrapper")
        try:
            return self.client.submit_program_evaluations(
                self.experiment_name, evaluation_submissions
            )
        except Exception as e:
            if "FAILED_PRECONDITION" in str(e) or "Precondition check failed" in str(e):
                try:
                    logger.info("FAILED_PRECONDITION encountered during submission. Checking experiment state...")
                    experiment = self.get_experiment()
                    if experiment and experiment.get("state") == AlphaEvolveExperimentState.PAUSED.name:
                        logger.info("Experiment is PAUSED. Attempting to automatically resume...")
                        self.resume_experiment()
                        logger.info("Retrying submission after auto-resume...")
                        return self.client.submit_program_evaluations(
                            self.experiment_name, evaluation_submissions
                        )
                except Exception as retry_err:
                    logger.error("Auto-resume or retry failed: %s", retry_err)
            raise e

    def stopping_criteria_met(self):
        if self.stats["num_programs_evaluated"] >= self.max_programs_evaluated:
            return True
        experiment = self.get_experiment()
        if experiment:
            if experiment.get("state") == AlphaEvolveExperimentState.COMPLETED.name:
                return True
            elif experiment.get("state") == AlphaEvolveExperimentState.FAILED.name:
                raise Exception("Experiment is FAILED. No further action can be taken.")
        return False