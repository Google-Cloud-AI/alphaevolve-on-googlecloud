# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import logging
import asyncio
import nest_asyncio

# Set logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Add Google Framework sources to path
sys.path.append("/app/src")

from alpha_evolve.controller import AlphaEvolveController
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env

from evaluator import evaluate_program

# Configuration environment variables
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
MODEL = os.getenv("_MODEL", "GEMINI_V2P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "10")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")

# Read C++ initial program
with open("main.cpp", "r") as f:
    INITIAL_MAIN_CPP = f.read()

def main():
    exp_config = {
        "title": "N-Body Gravity Simulation",
        "problem_description": (
            "You are optimizing the pairwise gravity force calculation in a C++ N-Body molecular simulation inside main.cpp. "
            "The computational loop is currently O(N^2). Evolve the C++ code inside the EVOLVE-BLOCK using standard C++17 with MPI support. "
            "The headers <immintrin.h> and <x86intrin.h> are already pre-included globally at the top of main.cpp. You MUST NOT write any `#include` statements or `#pragma` target/option directives inside the EVOLVE-BLOCK, as C++ forbids them inside function bodies. "
            "The particle chunk bounds for the current rank process are defined by the variables `start_idx` and `end_idx`. You must ensure all loop index variables (such as `i` or `j`) are fully and properly declared in your block. "
            "You MUST NOT re-declare or duplicate variable names that are already declared elsewhere in the function scope. Use AVX/SIMD compiler intrinsics directly for vectorization. "
            "You must strictly maintain total energy conservation (final ENERGY_DRIFT must remain < 1e-4)."
        ),
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
                    "path": "main.cpp",
                    "content": INITIAL_MAIN_CPP,
                }
            ]
        },
        "evaluation": {
            "scores": {
                "scores": [
                    {
                        "metric": "simulation_speed_score",
                        "score": -4500.0  # Estimated naive baseline running time in ms
                    }
                ]
            }
        },
    }

    # Apply nested loop fix
    nest_asyncio.apply()
    controller = AlphaEvolveController()
    
    # Start evolutionary loop
    asyncio.run(
        controller.run_loop(
            exp_config=exp_config,
            initial_program=initial_program,
            evaluator_function=evaluate_program
        )
    )

if __name__ == "__main__":
    main()
