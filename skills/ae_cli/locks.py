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

"""Lock cache for AlphaEvolve CLI."""

from __future__ import annotations

from . import config


class LockCache:
  """Caches lock tokens for programs."""

  def __init__(self, profile_name: str):
    self.profile_name = profile_name
    self.cache_key = f"lock_cache_{profile_name}"
    self._locks: dict[str, str] = {}
    self.load()

  def load(self) -> None:
    """Loads locks from disk cache."""
    data = config.get_cache(self.cache_key, ttl_seconds=2**30)
    if data and isinstance(data, dict):
      self._locks = data

  def save(self) -> None:
    """Saves locks to disk cache."""
    config.save_cache(self.cache_key, self._locks)

  def add(self, program_name: str, lock_token: str) -> None:
    """Adds a lock token for a program."""
    self._locks[program_name] = lock_token
    self.save()

  def get(self, program_name: str) -> str | None:
    """Retrieves a lock token for a program."""
    return self._locks.get(program_name)
