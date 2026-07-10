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

from alpha_evolve import AlphaEvolveController
from evaluator import evaluate, EVALUATION_METRIC
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
MODEL = os.getenv("_MODEL", "GEMINI_V2P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "10")

THIS_FILE_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

def _load_file(filename):
    file_path = THIS_FILE_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {filename} at {file_path}")
    with open(file_path, "r") as f:
        return f.read()

INITIAL_PROGRAM_CODE = _load_file("main.cir")
INITIAL_PROGRAM_LIB = _load_file("CMOS.lib")

def main():
    logging.basicConfig(level=logging.INFO)

    controller = AlphaEvolveController()

    exp_config = {
        "title": "CMOS Op-Amp Topology Exploration v6 (Physics-Aware)",
        "problem_description": (
            "Evolve a CMOS Op-Amp topology in SPICE to maximize Gain while maintaining physical feasibility. "
            "CONSTRAINTS: "
            "1. Maintain nodes 'OUT1' and 'OUT2' as the differential outputs. "
            "2. Avoid 'Clipping': The output signal should not hit the 0V or 5V rails (keep it between 0.5V and 4.5V). "
            "3. Power Efficiency: Minimize current draw from VDD. "
            "4. Topologies: You are encouraged to use Active Loads (PMOS), Current Mirrors, and multi-stage designs."
        ),
        "program_language": "spice",
        "run_settings": {
            "max_programs": MAX_PROGRAMS_GENERATED,
            "concurrency": CONCURRENCY,
        },
        "generation_settings": {
            "models": parse_models_from_env(MODEL)
        }
    }

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "main.cir",
                    "content": INITIAL_PROGRAM_CODE,
                },
                {
                    "path": "CMOS.lib",
                    "content": INITIAL_PROGRAM_LIB,
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
            evaluator_function=evaluate,
        )
    )

if __name__ == "__main__":
    main()
