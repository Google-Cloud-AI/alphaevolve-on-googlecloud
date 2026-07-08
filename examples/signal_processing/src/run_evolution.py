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
import json
import logging
import os
from pathlib import Path

import nest_asyncio
from dotenv import load_dotenv

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment
from alpha_evolve.visualization import get_score

from .evaluate import (
    signal_processing_evaluation,
)

load_dotenv()

logger = logging.getLogger(__name__)


# Configuration
PROJECT_ID = os.getenv("PROJECT_ID", "gcp-project-id")
LOCATION = os.getenv("LOCATION", "global")
COLLECTION = os.getenv("COLLECTION", "default_collection")
GE_APP_ID = os.getenv("GE_APP_ID", "your-engine-id")
ASSISTANT = os.getenv("ASSISTANT", "default_assistant")
BASE_URL = os.getenv("BASE_URL", "discoveryengine.googleapis.com")


# Run settings
MAX_PROGRAMS_GENERATED = 10
CONCURRENCY = 2
MAX_PROGRAMS_EVALUATED = 10

THIS_FILE_DIR = Path(os.path.dirname(os.path.realpath(__file__)))


# Load file content
def _load_file(filename):
    file_path = THIS_FILE_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {filename} at {file_path}")
    with open(file_path, "r") as f:
        return f.read()


INITIAL_PROGRAM_CODE = _load_file("program.py")

EVALUATION_METRIC = "overall_score"


def main():
    logging.basicConfig(level=logging.INFO)

    client = AlphaEvolveClient(
        project_id=PROJECT_ID,
        location=LOCATION,
        collection=COLLECTION,
        engine=GE_APP_ID,
        assistant=ASSISTANT,
        base_url=BASE_URL,
    )

    experiment = AlphaEvolveExperiment(client, signal_processing_evaluation, MAX_PROGRAMS_EVALUATED)

    exp_config = {
        "title": "Adaptive Signal Processing",
        "problem_description": (
            "Evolve a signal processing algorithm that filters volatile, non-stationary time "
            "series data using a sliding window approach. The algorithm must minimize noise "
            "while preserving signal dynamics with minimal computational latency and phase "
            "delay. Focus on the multi-objective optimization of: (1) Slope change minimization "
            "- reducing spurious directional reversals, (2) Lag error minimization - "
            "maintaining responsiveness, (3) Tracking accuracy - preserving genuine signal "
            "trends, and (4) False reversal penalty - avoiding noise-induced trend changes. "
            "Consider advanced techniques like adaptive filtering (Kalman filters, particle "
            "filters), multi-scale processing (wavelets, EMD), predictive enhancement "
            "(polynomial fitting, neural networks), and trend detection methods."
        ),
        "program_language": "python",
        "run_settings": {
            "max_programs": MAX_PROGRAMS_GENERATED,
            "concurrency": CONCURRENCY,
        },
    }

    try:
        experiment.create_experiment(exp_config)
        logger.info(f"Experiment created: {experiment.experiment_name}")
        logger.info(
            json.dumps(
                client.get_alpha_evolve_experiment(experiment_name=experiment.experiment_name),
                indent=4,
            )
        )

    except Exception as e:
        logger.error(f"Failed to create experiment (expected if no creds): {e}")
        return

    experiment = AlphaEvolveExperiment(client, signal_processing_evaluation, MAX_PROGRAMS_EVALUATED)

    experiment.create_experiment(exp_config)

    EVALUATION_METRIC = "overall_score"

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "program.py",
                    "content": INITIAL_PROGRAM_CODE,
                }
            ]
        },
        "evaluation": {"scores": {"scores": [{"metric": EVALUATION_METRIC, "score": 0.0}]}},
    }

    experiment.create_initial_program(initial_program)
    experiment.start_experiment()

    nest_asyncio.apply()
    asyncio.run(
        run_controller_loop(experiment, num_samplers=CONCURRENCY, num_evaluators=CONCURRENCY)
    )

    response = experiment.list_programs(params={"order_by": "score desc"})

    if response and "alphaEvolvePrograms" in response:
        top_programs = response["alphaEvolvePrograms"]
        top_programs.sort(key=lambda p: get_score(p, EVALUATION_METRIC), reverse=True)

        logger.info("\nTop Programs:")
        for i, prog in enumerate(top_programs[:3]):
            score = get_score(prog, EVALUATION_METRIC)
            logger.info(f"Rank {i + 1}: {prog.get('name', 'Unknown')} | Score: {score}")
    else:
        logger.info("No programs found.")


if __name__ == "__main__":
    main()
