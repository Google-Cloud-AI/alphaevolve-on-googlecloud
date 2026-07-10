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

"""Abstract base class for AlphaEvolve execution engines."""

import abc
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
  from .experiment import AlphaEvolveExperiment


class ExecutionEngine(abc.ABC):
  """Abstract interface for program execution backends."""

  @abc.abstractmethod
  async def start(self, experiment: "AlphaEvolveExperiment"):
    """Initialize the engine and any worker tasks.

    Args:
      experiment: The AlphaEvolveExperiment instance.
    """
    pass

  @abc.abstractmethod
  async def dispatch(self, program: Dict[str, Any]):
    """Send a program for evaluation.

    Args:
      program: A dictionary representing the program to be evaluated.
    """
    pass

  @abc.abstractmethod
  async def stop(self):
    """Clean up and stop worker tasks."""
    pass

