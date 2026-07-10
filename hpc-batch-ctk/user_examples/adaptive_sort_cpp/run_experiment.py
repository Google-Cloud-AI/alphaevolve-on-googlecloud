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

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env
from evaluator import adaptive_sort_evaluation

logger = logging.getLogger(__name__)


# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
LOCATION = os.getenv("_LOCATION", "global")
COLLECTION = os.getenv("_COLLECTION", "default_collection")
ENGINE = os.getenv("_ENGINE", "alpha-evolve-experiment-engine")
ASSISTANT = os.getenv("_ASSISTANT", "alpha-evolve-experiment-assistant")
BASE_URL = os.getenv("_BASE_URL", "discoveryengine.googleapis.com")

# Configuration
MODEL = os.getenv("_MODEL", "GEMINI_V2P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED", 10))
CONCURRENCY = int(os.getenv("_CONCURRENCY", 4))

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

    exp_config = {
        "title": "Adaptive Sort C++",
        "problem_description": "Evolve a C++ sorting algorithm to be adaptive to different data patterns (random, sorted, reverse, duplicates).",
        "program_language": "cpp",
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
                    "path": "src/sort.hpp",
                    "content": SORT_HPP_CONTENT,
                },
                {
                    "path": "src/sort_impl.hpp",
                    "content": SORT_IMPL_HPP_CONTENT,
                },
                {
                    "path": "src/benchmark.hpp",
                    "content": BENCHMARK_HPP_CONTENT,
                },
                {
                    "path": "src/benchmark.cpp",
                    "content": BENCHMARK_CPP_CONTENT,
                },
            ]
        },
        "evaluation": {
            "scores": {"scores": [{"metric": EVALUATION_METRIC, "score": 0.0}]}
        },
    }

    # nest_asyncio allows the asyncio event loop to be nested
    nest_asyncio.apply()
    controller = AlphaEvolveController()
    asyncio.run(controller.run_loop(
        evaluator_function=adaptive_sort_evaluation,
        exp_config=exp_config,
        initial_program=initial_program,
    ))

    response = controller.list_programs(params={"order_by": "score desc"})

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
