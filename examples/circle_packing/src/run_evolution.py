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
from typing import Any, Mapping

import nest_asyncio
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment
from alpha_evolve.visualization import get_score

from .evaluate import (
    CIRCLE_PACKING_EVALUATION_INPUTS,
    CIRCLE_PACKING_EVALUATION_METRIC,
    INITIAL_PROGRAM_CODE,
    circle_packing_evaluation,
    visualize_packing,
)

# Configuration
PROJECT_ID = os.getenv("PROJECT_ID", "gcp-project-id")
LOCATION = os.getenv("LOCATION", "global")
COLLECTION = os.getenv("COLLECTION", "default_collection")
GE_APP_ID = os.getenv("GE_APP_ID", "your-engine-id")
ASSISTANT = os.getenv("ASSISTANT", "default_assistant")
BASE_URL = os.getenv("BASE_URL", "discoveryengine.googleapis.com")
# Model configurations (demonstrating a weighted mixture of two models)
MODEL_1 = os.getenv("MODEL_1", "gemini-3.5-flash")
MODEL_2 = os.getenv("MODEL_2", "gemini-3.1-pro-preview")
MODEL_1_WEIGHT = float(os.getenv("MODEL_1_WEIGHT", "0.7"))
MODEL_2_WEIGHT = float(os.getenv("MODEL_2_WEIGHT", "0.3"))
PARALLEL_EVALUATION = os.getenv("PARALLEL_EVALUATION", "False").lower() == "true"

# Configuration
MAX_PROGRAMS_GENERATED = int(os.getenv("MAX_PROGRAMS_GENERATED", "10"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))
MAX_PROGRAMS_EVALUATED = int(os.getenv("MAX_PROGRAMS_EVALUATED", "10"))


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
        client,
        circle_packing_evaluation,
        MAX_PROGRAMS_EVALUATED,
        parallel_evaluation=PARALLEL_EVALUATION,
    )

    # Retrieve the model names and their corresponding weights from the environment
    models_raw = [
        (MODEL_1, MODEL_1_WEIGHT),
        (MODEL_2, MODEL_2_WEIGHT),
    ]
    # Deduplicate the models, sum their weights, and format the output
    generation_models = [
        {"name": m, "weight": round(w, 2)}
        for m, w in {
            name: sum(weight for n, weight in models_raw if n == name)
            for name, _ in models_raw
        }.items()
        if m
    ]

    exp_config = {
        "title": "Circle Packing",
        "problem_description": "Evolve a constructor-based algorithm to pack N circles into a unit square, maximizing the sum of their radii.",
        "program_language": "python",
        "run_settings": {
            "max_programs": MAX_PROGRAMS_GENERATED,
            "concurrency": CONCURRENCY,
        },
        "generation_settings": {
            "models": generation_models,
        },
    }

    logging.debug("Experiment config: %s", exp_config)
    # This will fail without real credentials/project, but the structure is correct.
    try:
        experiment.create_experiment(exp_config)
    except Exception as e:
        print(f"Failed to create experiment (expected if no creds): {e}")
        return

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "program.py",
                    "content": INITIAL_PROGRAM_CODE,
                }
            ]
        },
        "evaluation": {
            "scores": {
                "scores": [{"metric": CIRCLE_PACKING_EVALUATION_METRIC, "score": -1e12}]
            }
        },
    }

    experiment.create_initial_program(initial_program)
    experiment.start_experiment()

    # nest_asyncio allows the asyncio event loop to be nested
    nest_asyncio.apply()
    if PARALLEL_EVALUATION:
        # Match the number of evaluation workers to the configured worker concurrency
        asyncio.run(run_controller_loop(experiment, num_evaluators=WORKER_CONCURRENCY))
    else:
        asyncio.run(run_controller_loop(experiment))


    # Visualization
    list_params = {"order_by": "sum_of_radii asc"}
    response = experiment.list_programs(params=list_params)

    if response and "alphaEvolvePrograms" in response:
        top_programs = response["alphaEvolvePrograms"]
        # We use a lambda to pass the metric name to get_score
        top_programs.sort(
            key=lambda p: get_score(p, CIRCLE_PACKING_EVALUATION_METRIC), reverse=True
        )

        for i, prog in enumerate(top_programs):
            score_val = get_score(prog, CIRCLE_PACKING_EVALUATION_METRIC)
            if score_val == -float("inf"):
                print(
                    f"\nSkipping program with no valid score: {prog.get('name', 'Unknown ID')}"
                )
                continue

            print(f"\nVisualizing Rank {i + 1}: {prog.get('name', 'Unknown ID')}")
            try:
                code = prog["content"]["files"][0]["content"]

                exec_namespace = {"np": np, "Any": Any, "Mapping": Mapping}
                exec(code, exec_namespace)
                construct_packing_func = exec_namespace.get("construct_packing")

                if not callable(construct_packing_func):
                    print("ERROR: construct_packing not found or not callable.")
                    continue

                # Use fixed seed for consistent visualization
                n = CIRCLE_PACKING_EVALUATION_INPUTS["n"]
                centers, radii, score = construct_packing_func(n=n, random_seed=42)

                circles = list(zip(centers[:, 0], centers[:, 1], radii))
                title = f"Rank {i + 1} | ID: {prog.get('name', '')[-6:]} | Score: {score:.5f}"
                visualize_packing(circles, title)

            except Exception as e:
                print(f"ERROR visualizing program: {e}")
    else:
        print("No programs found to visualize.")


if __name__ == "__main__":
    main()
