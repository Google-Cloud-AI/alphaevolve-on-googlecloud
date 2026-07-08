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
"""Entry point for the Zillow Prize Kaggle competition experiment.

Uses AlphaEvolve to evolve ML pipelines (feature engineering + model
selection + hyperparameters) for predicting Zillow Zestimate log-error.
Evolved candidates are evaluated remotely on a Cloud Run service.
"""

import asyncio
import logging
import os
from pathlib import Path

import nest_asyncio
from dotenv import load_dotenv

# Load .env from the example directory, then fall back to repo root
_example_env = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".env"
)
load_dotenv(_example_env)
load_dotenv()  # repo-root .env as fallback

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment
from alpha_evolve.visualization import get_score

from .evaluate import METRIC_NAME, zillow_evaluation_function
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
MAX_PROGRAMS_GENERATED = int(os.getenv("MAX_PROGRAMS_GENERATED", "50"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
MAX_PROGRAMS_EVALUATED = int(os.getenv("MAX_PROGRAMS_EVALUATED", "50"))

EVALUATION_METRIC = METRIC_NAME

THIS_FILE_DIR = Path(os.path.dirname(os.path.realpath(__file__)))


def _load_seed_program() -> str:
    """Load the seed program from main.py."""
    seed_path = THIS_FILE_DIR / "program.py"
    with open(seed_path, "r") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Problem description for the LLM
# ---------------------------------------------------------------------------

_instructions_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "instructions.md"
)
with open(_instructions_path, "r") as _f:
    PROBLEM_DESCRIPTION = _f.read()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    logger.info("Setting up AlphaEvolve client for Zillow Prize experiment...")
    client = AlphaEvolveClient(
        project_id=PROJECT_ID,
        location=LOCATION,
        collection=COLLECTION,
        engine=GE_APP_ID,
        assistant=ASSISTANT,
        base_url=BASE_URL,
    )

    experiment = AlphaEvolveExperiment(
        client, zillow_evaluation_function, MAX_PROGRAMS_EVALUATED
    )

    # --- Experiment configuration ---
    exp_config = {
        "title": "Zillow Prize — Zestimate Logerror Prediction",
        "problem_description": PROBLEM_DESCRIPTION,
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

    # --- Seed program (placeholder score — backend evaluates via Cloud Run) ---
    seed_code = _load_seed_program()

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "main.py",
                    "content": seed_code,
                }
            ]
        },
        "evaluation": {
            "scores": {
                "scores": [
                    {"metric": EVALUATION_METRIC, "score": -1e12}
                ]
            }
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
        params={"order_by": f"{EVALUATION_METRIC} desc"},
    )

    programs = response.get("alphaEvolvePrograms", []) if response else []

    if not programs:
        logger.warning("No programs returned.")
        return

    # Use Ridge baseline MAE (~0.066) for report comparison
    seed_score = -0.066
    generate_report(programs, seed_score)


if __name__ == "__main__":
    main()
