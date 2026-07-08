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
import logging
from concurrent.futures import ThreadPoolExecutor

from .experiment import AlphaEvolveExperiment
from .workers import EvaluationWorker, SamplingWorker

logger = logging.getLogger(__name__)

PROGRESS_LOG_INTERVAL_S = 10
DEFAULT_IDLE_TIMEOUT_S = 120


async def run_controller_loop(
    experiment: AlphaEvolveExperiment,
    num_samplers: int = 4,
    num_evaluators: int = 32,
    idle_timeout_s: int = DEFAULT_IDLE_TIMEOUT_S,
):
    """Runs the main control loop for the AlphaEvolve experiment.

    This loop spawns multiple SamplingWorkers to poll for new candidates and
    multiple EvaluationWorkers to process them.

    Args:
        experiment: The experiment instance to run.
        num_samplers: Number of concurrent polling tasks.
        num_evaluators: Number of concurrent evaluation tasks. If
            `experiment.parallel_evaluation` is True, these tasks will
            run in parallel using background threads.
        idle_timeout_s: If no new programs are generated or evaluated for this
            many seconds (and the evaluation queue is empty), the loop exits
            early instead of hanging. This handles the case where the backend
            finishes generating before `max_programs_evaluated` is reached.
            Set to 0 or a negative value to disable.
    """
    evaluation_queue = asyncio.Queue()

    executor = None
    sampler_tasks = []
    evaluator_tasks = []

    try:
        # Create a dedicated ThreadPoolExecutor for the heavy evaluators if parallel mode is enabled.
        # This avoids saturating the default asyncio thread pool and ensures result submissions
        # (which use the default pool) are not delayed.
        if experiment.parallel_evaluation:
            logger.info("Parallel evaluation enabled (concurrency=%d)", num_evaluators)
            executor = ThreadPoolExecutor(max_workers=num_evaluators)

        logger.info(
            "Evolution loop started: %d sampler(s), %d evaluator(s), target=%d programs",
            num_samplers,
            num_evaluators,
            experiment.max_programs_evaluated,
        )
        sampler_tasks = [
            asyncio.create_task(SamplingWorker(experiment, evaluation_queue).run())
            for _ in range(num_samplers)
        ]
        evaluator_tasks = [
            asyncio.create_task(
                EvaluationWorker(experiment, evaluation_queue, executor=executor).run()
            )
            for _ in range(num_evaluators)
        ]

        loop = asyncio.get_running_loop()
        last_report = loop.time()
        last_progress = loop.time()
        last_stats = dict(experiment.stats)
        while True:
            if experiment.stopping_criteria_met():
                logger.info(
                    "Stopping criteria met (%s/%s programs evaluated).",
                    experiment.stats["num_programs_evaluated"],
                    experiment.max_programs_evaluated,
                )
                break

            now = loop.time()
            stats = experiment.stats
            made_progress = stats != last_stats
            if made_progress:
                last_progress = now
                last_stats = dict(stats)

            # Stop early if the backend has gone quiet so post-processing can run.
            if (
                idle_timeout_s > 0
                and evaluation_queue.empty()
                and now - last_progress >= idle_timeout_s
            ):
                logger.warning(
                    "No new candidates for %ds and queue is empty; assuming the "
                    "backend has finished. Stopping at %s/%s programs evaluated.",
                    idle_timeout_s,
                    stats["num_programs_evaluated"],
                    experiment.max_programs_evaluated,
                )
                break

            if now - last_report >= PROGRESS_LOG_INTERVAL_S:
                if made_progress:
                    logger.info(
                        "Progress: generated=%s, evaluated=%s/%s, queued=%s",
                        stats["num_programs_generated"],
                        stats["num_programs_evaluated"],
                        experiment.max_programs_evaluated,
                        evaluation_queue.qsize(),
                    )
                else:
                    idle_for = int(now - last_progress)
                    logger.info(
                        "Waiting for the backend to generate candidates... "
                        "(generated=%s, evaluated=%s/%s, idle=%ss)",
                        stats["num_programs_generated"],
                        stats["num_programs_evaluated"],
                        experiment.max_programs_evaluated,
                        idle_for,
                    )
                last_report = now

            await asyncio.sleep(1)
    finally:
        # Shutdown worker tasks.
        all_tasks = sampler_tasks + evaluator_tasks
        for task in all_tasks:
            task.cancel()

        await asyncio.gather(*all_tasks, return_exceptions=True)
        if executor:
            executor.shutdown(wait=False)
        logger.info("Evolution loop terminated.")
