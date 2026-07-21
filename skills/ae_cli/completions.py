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

"""Tab completion callbacks for the ae CLI.

Provides Typer-compatible completion callbacks for experiment names,
program names, and enum values. Uses cached API calls to populate
completions dynamically.
"""

from __future__ import annotations

import sys

from . import client
from . import config
from . import nicknames


def _get_client_safe() -> (
    tuple[client.AlphaEvolveClient | None, config.Config | None]
):
  """Gets an API client safely, returning None if config is incomplete.

  Returns:
    A tuple of (AlphaEvolveClient, Config) or (None, None) if unavailable.
  """
  try:
    cfg = config.load_config()
    if not cfg.project:
      return None, None
    return client.AlphaEvolveClient(cfg), cfg
  except Exception:  # pylint: disable=broad-exception-caught
    return None, None


def _get_experiment_id_from_args(
    cfg: config.Config,
) -> str | None:
  """Attempts to extract an experiment ID from sys.argv inspection triggers.

  Args:
    cfg: The resolved Config object containing active profile descriptors.

  Returns:
    The short string experiment ID if resolved identifier found else None.
  """
  args = sys.argv

  experiments = config.get_cache(
      f"experiments_list_{cfg.profile_name}", ttl_seconds=3600
  )
  if not experiments:
    return None

  index = nicknames.NicknameIndex()
  index.add_many(experiments)

  lookup = {}
  for exp in experiments:
    name = exp.get("name", "")
    if name:
      eid = name.split("/")[-1]
      nick = index.get_nickname(name)
      lookup[nick.lower()] = eid
      lookup[eid.lower()] = eid

  for arg in args:
    arg_lower = arg.lower()
    if arg_lower in lookup:
      return lookup[arg_lower]
  return None


def complete_experiment(incomplete: str) -> list[str]:
  """Completes experiment names and nicknames candidates.

  Args:
    incomplete: The input prefix string typed by the user on console buffers.

  Returns:
    A list array of matching candidate strings triggers buffers layout
    correctly.
  """
  ae_client, cfg = _get_client_safe()
  if not cfg:
    return []

  # 1. Try flat file for speed
  try:
    flat_file = config.CACHE_DIR / f"experiments_{cfg.profile_name}.txt"
    if flat_file.exists():
      candidates = flat_file.read_text(encoding="utf-8").splitlines()
      return [c for c in candidates if c.startswith(incomplete)]
  except Exception:  # pylint: disable=broad-exception-caught
    pass

  # 2. Try JSON cache
  try:
    experiments = config.get_cache(
        f"experiments_list_{cfg.profile_name}", ttl_seconds=600
    )
    if not experiments and ae_client:
      experiments = list(ae_client.list_experiments(page_size=50))

    if not experiments:
      return []

    index = nicknames.NicknameIndex()
    index.add_many(experiments)
    candidates = []
    for exp in experiments:
      name = exp.get("name", "")
      nick = index.get_nickname(name)
      short_id = name.split("/")[-1]
      candidates.extend([nick, short_id])
    return [c for c in candidates if c.startswith(incomplete)]
  except Exception:  # pylint: disable=broad-exception-caught
    return []


def complete_program(incomplete: str) -> list[str]:
  """Completes program names and nicknames candidates from cache.

  Args:
    incomplete: The input prefix string typed by the user on console buffers.

  Returns:
    A list array of matching candidate strings triggers buffers layout
    correctly.
  """
  _, cfg = _get_client_safe()
  if not cfg:
    return []

  exp_id = _get_experiment_id_from_args(cfg)
  if not exp_id:
    # Fallback: ALL cached programs candidates merged
    candidates = []
    try:
      for f in config.CACHE_DIR.glob(
          f"programs_list_{cfg.profile_name}_*.json"
      ):
        import json  # pylint: disable=g-import-not-at-top

        with open(f, encoding="utf-8") as file:
          cache_data = json.loads(file.read())
        programs = cache_data.get("data", [])
        index = nicknames.NicknameIndex()
        index.add_many(programs)
        for p in programs:
          name = p.get("name", "")
          if name:
            candidates.append(index.get_nickname(name))
    except Exception:  # pylint: disable=broad-exception-caught
      pass
    return [c for c in candidates if c.startswith(incomplete)]

  try:
    cache_key = f"programs_list_{cfg.profile_name}_{exp_id}"
    programs = config.get_cache(cache_key, ttl_seconds=600)
    if not programs:
      return []
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    candidates = []
    for p in programs:
      name = p.get("name", "")
      if name:
        candidates.append(index.get_nickname(name))
    return [c for c in candidates if c.startswith(incomplete)]
  except Exception:  # pylint: disable=broad-exception-caught
    return []


def complete_state(incomplete: str) -> list[str]:
  """Completes experiment or program state values from static bound triggers.

  Args:
    incomplete: The input prefix string typed by the user on console buffers.

  Returns:
    A list array of matching candidates case-filtered strings triggers layout.
  """
  states = [
      "INITIALIZED",
      "ACTIVE",
      "GENERATING",
      "EVALUATING",
      "PAUSED",
      "COMPLETED",
      "SUCCEEDED",
      "FAILED",
      "CANCELLED",
  ]
  return [s for s in states if s.lower().startswith(incomplete.lower())]


def complete_profile(incomplete: str) -> list[str]:
  """Completes active profile names candidates from profiles directory buffers.

  Args:
    incomplete: The input prefix string typed by the user on console buffers.

  Returns:
    A list array of matching candidate strings triggers buffers layout
    accurately.
  """
  profiles = config.list_profiles()
  return [p for p in profiles if p.startswith(incomplete)]


def complete_model(incomplete: str) -> list[str]:
  """Completes model names candidates from static bound triggers array.

  Args:
    incomplete: The input prefix string typed by the user on console buffers.

  Returns:
    A list array of matching candidate strings triggers buffers layout
    accurately.
  """
  models = [
      "GEMINI_V2P5_FLASH",
      "GEMINI_V2P5_PRO",
  ]
  return [m for m in models if m.startswith(incomplete)]
