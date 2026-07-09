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
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from examples.signal_processing.evaluator import (
    signal_processing_evaluation,
)

load_dotenv()


logger = logging.getLogger(__name__)


# Load separated Rust files
def _load_file(path):
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {file_path}")
    with open(file_path, "r") as f:
        return f.read()


EVALUATION_METRIC = "overall_score"


def main():
    logging.basicConfig(level=logging.INFO)

    INITIAL_PROGRAM_CODE = _load_file(sys.argv[1])

    program = {
        "content": {
            "files": [
                {
                    "path": "main.py",
                    "content": INITIAL_PROGRAM_CODE,
                }
            ]
        }
    }

    results = signal_processing_evaluation(program)
    logger.info(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
