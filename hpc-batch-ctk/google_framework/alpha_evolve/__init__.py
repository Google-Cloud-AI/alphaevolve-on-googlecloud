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

import logging
import sys

# Configure framework logging to stdout instead of stderr
# to avoid Google Cloud Logging misclassifying logs as ERROR.
logger = logging.getLogger("alpha_evolve")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

from .client import AlphaEvolveClient
from .experiment import AlphaEvolveExperiment
from .controller import AlphaEvolveController
from .visualization import get_score
from .execution import DistributedEngine
from .cloud_batch import BatchClient

__all__ = [
    "AlphaEvolveClient",
    "AlphaEvolveExperiment",
    "AlphaEvolveController",
    "get_score",
    "DistributedEngine",
    "BatchClient",
]
