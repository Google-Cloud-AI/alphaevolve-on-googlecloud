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
import sys

import nest_asyncio
from dotenv import load_dotenv

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve.controller import AlphaEvolveController
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env
from alpha_evolve.visualization import get_score
from evaluator import signal_processing_evaluation

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
MODEL = os.getenv("_MODEL", "GEMINI_V2P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED", "10"))
CONCURRENCY = int(os.getenv("_CONCURRENCY", "2"))

THIS_FILE_DIR = Path(os.path.dirname(os.path.realpath(__file__)))


# Load file content
def _load_file(filename):
    file_path = THIS_FILE_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {filename} at {file_path}")
    with open(file_path, "r") as f:
        return f.read()


INITIAL_PROGRAM_CODE = _load_file("main.py")

EVALUATION_METRIC = "overall_score"


def main():
    logging.basicConfig(level=logging.INFO)

    controller = AlphaEvolveController()


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
        "generation_settings": {
            "models": parse_models_from_env(MODEL)
        },
    }

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "main.py",
                    "content": INITIAL_PROGRAM_CODE,
                }
            ]
        },
        "evaluation": {"scores": {"scores": [{"metric": EVALUATION_METRIC, "score": 0.0}]}},
    }

    nest_asyncio.apply()
    asyncio.run(
        controller.run_loop(
            exp_config=exp_config,
            initial_program=initial_program,
            num_samplers=CONCURRENCY,
            evaluator_function=signal_processing_evaluation,
        )
    )

    response = controller.experiment.list_programs(params={"order_by": "score desc"})

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
