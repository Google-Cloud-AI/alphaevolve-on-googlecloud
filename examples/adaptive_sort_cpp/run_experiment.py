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
import os
import sys
from pathlib import Path

import nest_asyncio
from dotenv import load_dotenv

load_dotenv()

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment
from alpha_evolve.visualization import get_score

from .evaluator import (
    adaptive_sort_evaluation,
)

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
CONCURRENCY = 4
MAX_PROGRAMS_EVALUATED = 10

THIS_FILE_DIR = Path(os.path.dirname(os.path.realpath(__file__)))


# Load separated C++ files
def _load_file(filename):
    file_path = THIS_FILE_DIR / "src" / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {filename} at {file_path}")
    with open(file_path, "r") as f:
        return f.read()


SORT_HPP_CONTENT = _load_file("sort.hpp")
SORT_IMPL_HPP_CONTENT = _load_file("sort_impl.hpp")
BENCHMARK_HPP_CONTENT = _load_file("benchmark.hpp")
BENCHMARK_CPP_CONTENT = _load_file("benchmark.cpp")

EVALUATION_METRIC = "score"


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

    experiment = AlphaEvolveExperiment(
        client, adaptive_sort_evaluation, MAX_PROGRAMS_EVALUATED
    )

    exp_config = {
        "title": "Adaptive Sort C++",
        "problem_description": "Evolve a C++ sorting algorithm to be adaptive to different data patterns (random, sorted, reverse, duplicates).",
        "program_language": "cpp",
        "run_settings": {
            "max_programs": MAX_PROGRAMS_GENERATED,
            "concurrency": CONCURRENCY,
        },
    }

    try:
        experiment.create_experiment(exp_config)
    except Exception as e:
        logger.error(f"Failed to create experiment (expected if no creds): {e}")
        return

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "sort.hpp",
                    "content": SORT_HPP_CONTENT,
                },
                {
                    "path": "sort_impl.hpp",
                    "content": SORT_IMPL_HPP_CONTENT,
                },
                {
                    "path": "benchmark.hpp",
                    "content": BENCHMARK_HPP_CONTENT,
                },
                {
                    "path": "benchmark.cpp",
                    "content": BENCHMARK_CPP_CONTENT,
                },
            ]
        },
        "evaluation": {
            "scores": {"scores": [{"metric": EVALUATION_METRIC, "score": 0.0}]}
        },
    }

    experiment.create_initial_program(initial_program)
    experiment.start_experiment()

    nest_asyncio.apply()
    asyncio.run(run_controller_loop(experiment))

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
