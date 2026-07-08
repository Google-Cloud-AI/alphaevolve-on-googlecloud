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
import inspect
import logging
from typing import Any, Callable, Dict, Optional

from .client import AlphaEvolveClient

logger = logging.getLogger(__name__)


class AlphaEvolveExperiment:
    def __init__(
        self,
        ae_client: AlphaEvolveClient,
        evaluator_function: Callable,
        max_programs_evaluated: int,
        parallel_evaluation: bool = False,
    ):
        """Initializes the AlphaEvolveExperiment.

        Args:
            ae_client: Client for interacting with AlphaEvolve service.
            evaluator_function: A function (sync or async) that takes a program
                candidate (dict) and returns evaluation results (dict).
            max_programs_evaluated: The number of programs to evaluate before
                stopping the experiment.
            parallel_evaluation: If True, synchronous evaluator functions will
                be offloaded to background threads. This allows true parallelism
                when num_evaluators > 1 in the controller. Note that this is
                incompatible with functions using `signal.alarm`.
        """
        self.stats = {
            "num_programs_generated": 0,
            "num_programs_evaluated": 0,
        }
        self.client = ae_client
        self.evaluator_client = evaluator_function
        if inspect.iscoroutinefunction(evaluator_function):
            self.evaluator = self._async_evaluator
        self.max_programs_evaluated = max_programs_evaluated
        self.parallel_evaluation = parallel_evaluation
        self.session_name = None
        self.experiment = None
        self.experiment_name = None
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
        if not self.experiment:
            raise RuntimeError(
                "Failed to create the AlphaEvolve experiment (see error logs "
                "above). Common causes: invalid experiment config, missing "
                "permissions, or the API not being enabled."
            )
        self.experiment_name = self.experiment["name"]
        logger.info(f"experiment_name: {self.experiment_name}")

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
        experiment = self.client.resume_experiment(self.experiment_name)
        logger.info(experiment)

    def _wrap_result(self, result):
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

    async def _async_evaluator(self, program: Dict[str, Any]):
        result = await self.evaluator_client(program)
        return self._wrap_result(result)

    def evaluator(self, program: Dict[str, Any]):
        result = self.evaluator_client(program)
        return self._wrap_result(result)

    def stopping_criteria_met(self):
        return self.stats["num_programs_evaluated"] >= self.max_programs_evaluated
