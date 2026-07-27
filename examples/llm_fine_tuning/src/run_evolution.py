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

"""Run an AlphaEvolve experiment for LLM fine-tuning hyperparameter optimization.

Uses AlphaEvolve to evolve LoRA fine-tuning hyperparameters for Gemma 4 E2B
on a function-calling dataset. The evolved hyperparameter configurations
are evaluated remotely on a GKE gateway backed by a persistent RayCluster with GPU.

Usage:
    python -m examples.llm_fine_tuning.src.run_evolution
"""

import asyncio
import logging
import os

import nest_asyncio
from dotenv import load_dotenv

# Load .env from the example directory, then fall back to repo root
_example_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_example_env)
load_dotenv()

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment
from .evaluate import (
    INITIAL_PROGRAM_CODE,
    METRIC_NAME,
    SEED_BOOTSTRAP_SCORE,
    evaluation_function,
)
from .utils.report import generate_report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------
PROJECT_ID = os.getenv("PROJECT_ID", "gcp-project-id")
LOCATION = os.getenv("LOCATION", "global")
COLLECTION = os.getenv("COLLECTION", "default_collection")
GE_APP_ID = os.getenv("GE_APP_ID", "your-engine-id")
ASSISTANT = os.getenv("ASSISTANT", "default_assistant")
BASE_URL = os.getenv("BASE_URL", "discoveryengine.googleapis.com")
MODEL = os.getenv("MODEL", "gemini-3.5-flash")
MAX_PROGRAMS_GENERATED = int(os.getenv("MAX_PROGRAMS_GENERATED", "20"))
MAX_PROGRAMS_EVALUATED = int(os.getenv("MAX_PROGRAMS_EVALUATED", "20"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
# Remote GPU evaluations take minutes. The controller's idle stop must exceed a
# single evaluation, or it will give up and cancel in-flight jobs while the
# backend is still waiting on scores to evolve the next generation.
IDLE_TIMEOUT_S = int(os.getenv("IDLE_TIMEOUT_S", "1800"))

# SEED_EVAL_LOSS: known eval loss of the seed config, for a "vs seed" report with no extra eval.
SEED_EVAL_LOSS = os.getenv("SEED_EVAL_LOSS")
# BASELINE_SEED=true runs one seed eval for a real "vs seed" baseline (default: skip).
BASELINE_SEED = os.getenv("BASELINE_SEED", "false").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    logger.info("Setting up AlphaEvolve client...")
    client = AlphaEvolveClient(
        project_id=PROJECT_ID,
        location=LOCATION,
        collection=COLLECTION,
        engine=GE_APP_ID,
        assistant=ASSISTANT,
        base_url=BASE_URL,
    )

    experiment = AlphaEvolveExperiment(
        ae_client=client,
        evaluator_function=evaluation_function,
        max_programs_evaluated=MAX_PROGRAMS_EVALUATED,
        parallel_evaluation=True,
    )

    instructions_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "instructions.md"
    )
    with open(instructions_path, "r") as f:
        problem_description = f.read()

    exp_config = {
        "title": "LLM Fine-Tuning Hyperparameter Optimization",
        "problem_description": problem_description,
        "program_language": "python",
        "run_settings": {
            "max_programs": MAX_PROGRAMS_GENERATED,
            "concurrency": CONCURRENCY,
        },
        "generation_settings": {
            "models": [{"name": MODEL}],
        },
    }

    try:
        experiment.create_experiment(exp_config)
    except Exception as e:
        logger.error(f"Failed to create experiment: {e}")
        return

    logger.info("Experiment created: %s", experiment.experiment_name)

    # Seed baseline for the report: a known eval loss if provided, else one seed
    # eval if BASELINE_SEED, else skipped.
    seed_baseline = None
    if SEED_EVAL_LOSS is not None:
        try:
            seed_baseline = -float(SEED_EVAL_LOSS)
            logger.info("Using provided seed baseline: %s = %.4f", METRIC_NAME, seed_baseline)
        except ValueError:
            logger.warning("Invalid SEED_EVAL_LOSS=%r; ignoring.", SEED_EVAL_LOSS)
    if seed_baseline is None and BASELINE_SEED:
        logger.info("Baselining the seed program (one remote GPU eval)...")
        seed_eval = evaluation_function(
            {"name": "seed", "content": {"files": [
                {"path": "program.py", "content": INITIAL_PROGRAM_CODE}]}}
        )
        if METRIC_NAME in seed_eval:
            seed_baseline = float(seed_eval[METRIC_NAME])
        else:
            seed_baseline = next(
                (s["score"] for s in seed_eval.get("scores", {}).get("scores", [])
                 if s.get("metric") == METRIC_NAME),
                None,
            )
        if seed_baseline is None:
            logger.warning(
                "Seed evaluation returned no '%s' score; continuing without a "
                "seed baseline.", METRIC_NAME
            )
        else:
            logger.info("Seed %s = %.4f", METRIC_NAME, seed_baseline)

    bootstrap_score = (
        seed_baseline if seed_baseline is not None else SEED_BOOTSTRAP_SCORE
    )
    initial_program = {
        "content": {
            "files": [{"path": "program.py", "content": INITIAL_PROGRAM_CODE}]
        },
        "evaluation": {
            "scores": {"scores": [{"metric": METRIC_NAME, "score": bootstrap_score}]}
        },
    }

    experiment.create_initial_program(initial_program)
    experiment.start_experiment()
    logger.info("Experiment started. Running evolution loop...")

    nest_asyncio.apply()
    asyncio.run(run_controller_loop(
        experiment,
        num_samplers=2,
        num_evaluators=4,  # match max_gpu_nodes
        idle_timeout_s=IDLE_TIMEOUT_S,
    ))

    # --- Retrieve and display results ---
    logger.info("Evolution complete. Fetching results...")
    response = experiment.list_programs(
        params={"order_by": f"{METRIC_NAME} desc"},
    )

    programs = response.get("alphaEvolvePrograms", []) if response else []

    if not programs:
        logger.warning("No programs returned.")
        return

    generate_report(programs, seed_baseline)


if __name__ == "__main__":
    main()
