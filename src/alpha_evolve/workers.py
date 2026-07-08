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
import asyncio
import inspect
import logging

from .experiment import AlphaEvolveExperiment

logger = logging.getLogger(__name__)


def _short_id(resource_name: str) -> str:
    """Returns the trailing ID from a full GCP resource name for readable logs."""
    if not resource_name:
        return "unknown"
    return resource_name.rsplit("/", 1)[-1]


def _scores_summary(evaluation: dict) -> str:
    """Renders an evaluation's scores as a compact 'metric=value' string."""
    try:
        scores = evaluation.get("scores", {}).get("scores", [])
        parts = []
        for s in scores:
            metric = s.get("metric", "?")
            score = s.get("score")
            parts.append(
                f"{metric}={score:.4f}" if isinstance(score, float) else f"{metric}={score}"
            )
        return ", ".join(parts) if parts else "no scores"
    except Exception:
        return str(evaluation)


class SamplingWorker:
    """
    A worker that polls for new programs.
    Since acquire_programs is sync but fast, we call it directly but
    must sleep if no work is found to yield control to other tasks.
    """

    def __init__(
        self,
        experiment: AlphaEvolveExperiment,
        evaluation_queue: asyncio.Queue,
        poll_interval=4,
    ):
        self.experiment = experiment
        self.ae_client = experiment.client
        self.evaluation_queue = evaluation_queue
        self.poll_interval = poll_interval
        # TODO: change to a higher number when ttl issue is fixed.
        self.num_acquired_programs_per_call = 5

    async def run(self):
        try:
            while True:
                try:
                    await self._poll_and_enqueue()
                except Exception:
                    logger.exception("SamplingWorker error in acquire_programs loop")
                    # Pause before retrying to avoid tight-looping on persistent errors.
                    await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("SamplingWorker failed unexpectedly")

    async def _poll_and_enqueue(self):
        """Polls for new programs and puts them in the evaluation queue."""
        # Note: this is a fast sync call.
        logger.debug("Polling for new program candidates")
        response = self.ae_client.acquire_programs(
            self.experiment.experiment_name, self.num_acquired_programs_per_call
        )

        programs = response.get("programs") if response else None
        if programs and isinstance(programs, list):
            self.experiment.stats["num_programs_generated"] += len(programs)
            ids = [_short_id(p.get("name", "")) for p in programs]
            logger.info("Acquired %d new candidate(s): %s", len(programs), ", ".join(ids))
            for program in programs:
                logger.debug("Enqueued candidate payload: %s", program)
                await self.evaluation_queue.put(program)
        else:
            # No program found (either empty, malformed, or missing): pause this worker loop.
            logger.debug("No candidates available yet; retrying in %ss", self.poll_interval)
            await asyncio.sleep(self.poll_interval)


class EvaluationWorker:
    """
    A worker that evaluates program candidates.

    This worker pulls programs from the evaluation_queue and executes the
    experiment's evaluator. To ensure the asyncio event loop remains responsive
    and to support true parallelism:
    1. Synchronous evaluators are offloaded to background threads if
       `experiment.parallel_evaluation` is True.
    2. Blocking network calls (submitting evaluations) are always offloaded
       to background threads.
    """

    def __init__(
        self,
        experiment: AlphaEvolveExperiment,
        evaluation_queue: asyncio.Queue,
        executor=None,
    ):
        self.experiment = experiment
        self.ae_client = experiment.client
        self.evaluator = experiment.evaluator
        self.evaluation_queue = evaluation_queue
        self.executor = executor

    async def run(self):
        try:
            while True:
                # Wait for a program from the queue.
                logger.debug("Evaluation worker waiting for next candidate")
                program = await self.evaluation_queue.get()

                try:
                    await self._process_program(program)
                except Exception:
                    logger.exception(
                        "Error processing program %s", _short_id(program.get("name"))
                    )
                finally:
                    self.evaluation_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("EvaluationWorker failed unexpectedly")

    async def _process_program(self, program):
        """Evaluates a program and submits the result."""
        program_id = _short_id(program["name"])
        logger.info("Evaluating candidate %s", program_id)

        if inspect.iscoroutinefunction(self.evaluator):
            evaluation = await self.evaluator(program)
        elif self.experiment.parallel_evaluation:
            # Offload sync evaluator to a thread if parallel mode is enabled.
            # We use the dedicated executor if provided, otherwise fallback to the default pool.
            loop = asyncio.get_running_loop()
            evaluation = await loop.run_in_executor(
                self.executor, self.evaluator, program
            )
        else:
            evaluation = self.evaluator(program)

        logger.debug("Raw evaluation for %s: %s", program_id, evaluation)

        # Filter evaluation results to only include valid keys
        valid_keys = {"scores", "insights"}
        submission_eval = {k: v for k, v in evaluation.items() if k in valid_keys}

        evaluation_submissions = [
            {
                "program": program["name"],
                "lock_token": program["lockToken"],
                "evaluation": submission_eval,
            }
        ]
        logger.info(
            "Candidate %s evaluated → %s", program_id, _scores_summary(submission_eval)
        )

        # Always offload blocking network call to a thread to keep the event loop responsive.
        response = await asyncio.to_thread(
            self.ae_client.submit_program_evaluations,
            self.experiment.experiment_name,
            evaluation_submissions,
        )

        if response is not None:
            self.experiment.stats["num_programs_evaluated"] += 1
            logger.debug("Submitted evaluation for %s", program_id)
        else:
            logger.warning("Failed to submit evaluation for candidate %s", program_id)
