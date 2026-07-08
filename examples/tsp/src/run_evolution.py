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

"""Run an AlphaEvolve experiment for the Travelling Salesman Problem.

Usage:
    python -m examples.tsp.src.run_evolution
"""

import asyncio
import logging
import os

import nest_asyncio
from dotenv import load_dotenv

# Load .env from the example directory, then fall back to repo root
_example_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_example_env)
load_dotenv()  # repo-root .env as fallback

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment
from alpha_evolve.visualization import get_score

from .evaluate import INITIAL_PROGRAM_CODE, METRIC_NAME, tsp_evaluation_function
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
PARALLEL_EVALUATION = os.getenv("PARALLEL_EVALUATION", "False").lower() == "true"
MAX_PROGRAMS_GENERATED = int(os.getenv("MAX_PROGRAMS_GENERATED", "100"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
MAX_PROGRAMS_EVALUATED = int(
    os.getenv("MAX_PROGRAMS_EVALUATED", str(MAX_PROGRAMS_GENERATED - 1))
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    logger.info("Setting up AlphaEvolve client for TSP experiment...")
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
        evaluator_function=tsp_evaluation_function,
        max_programs_evaluated=MAX_PROGRAMS_EVALUATED,
        parallel_evaluation=PARALLEL_EVALUATION,
    )

    # --- Experiment configuration ---
    instructions_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "instructions.md"
    )
    with open(instructions_path, "r") as f:
        problem_description = f.read()

    exp_config = {
        "title": "TSP Tour Length Minimization (N=50)",
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

    experiment.create_experiment(exp_config)
    logger.info("Experiment created: %s", experiment.experiment_name)

    # --- Seed program ---
    seed_candidate = {
        "content": {"files": [{"path": "main.py", "content": INITIAL_PROGRAM_CODE}]},
    }
    seed_eval = tsp_evaluation_function(seed_candidate)
    seed_score = seed_eval["scores"]["scores"][0]["score"]
    logger.info("Seed program score (%s): %s", METRIC_NAME, seed_score)

    initial_program = {
        "content": {
            "files": [{"path": "main.py", "content": INITIAL_PROGRAM_CODE}],
        },
        "evaluation": {
            "scores": {
                "scores": [{"metric": METRIC_NAME, "score": seed_score}],
            },
        },
    }

    experiment.create_initial_program(initial_program)
    experiment.start_experiment()
    logger.info("Experiment started. Running controller loop...")

    # --- Run evolution ---
    nest_asyncio.apply()
    asyncio.run(run_controller_loop(experiment))

    # --- Retrieve and display results ---
    logger.info("Experiment complete. Fetching results...")
    response = experiment.list_programs(
        params={"order_by": f"{METRIC_NAME} desc"}
    )

    programs = response.get("alphaEvolvePrograms", []) if response else []
    if programs:
        generate_report(programs, seed_score)
    else:
        logger.warning("No programs returned.")


if __name__ == "__main__":
    main()
