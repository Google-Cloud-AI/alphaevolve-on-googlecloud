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

"""Shared experiment and program resolution and cache helpers.

Used by both the Typer CLI (`cli.py`) and the stdlib argparse CLI
(`sandbox_cli.py`) so `sessions/-` listing, concrete-session preservation, and
cold-cache raw-ID lookup have a single source of truth.
"""

from __future__ import annotations

import collections.abc
import json
import re
from typing import Any

from . import client as client_module
from . import config
from . import nicknames


def invalidate_cache() -> None:
  """Invalidates the legacy flat experiment list cache files."""
  for name in ("experiments_list.json", "experiments.txt"):
    path = config.CACHE_DIR / name
    if path.exists():
      try:
        path.unlink()
      except OSError:
        pass


def read_cached_experiments(cfg: config.Config) -> list[dict[str, Any]] | None:
  """Reads experiments from disk cache, or returns None if unavailable."""
  cache_file = config.CACHE_DIR / f"experiments_list_{cfg.profile_name}.json"
  if cache_file.exists():
    try:
      cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
      return cache_data.get("data")
    except (json.JSONDecodeError, AttributeError, TypeError):
      pass
  return None


def read_cached_programs(
    cfg: config.Config, exp_id: str
) -> list[dict[str, Any]] | None:
  """Reads programs from disk cache, or returns None if unavailable."""
  cache_file = (
      config.CACHE_DIR / f"programs_list_{cfg.profile_name}_{exp_id}.json"
  )
  if cache_file.exists():
    try:
      cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
      return cache_data.get("data")
    except (json.JSONDecodeError, AttributeError, TypeError):
      pass
  return None


def _engine_sessions_prefix(cfg: config.Config) -> str:
  """Returns the engine-scoped `/sessions/` prefix when project is a string."""
  if isinstance(cfg.project, str) and cfg.project:
    return (
        f"projects/{cfg.project}/locations/{cfg.location}"
        f"/collections/{cfg.collection}/engines/{cfg.engine}/sessions/"
    )
  return ""


def _is_wildcard_mode(
    cfg: config.Config,
    client: client_module.AlphaEvolveClient | None,
) -> bool:
  """Returns True when wildcard `sessions/-` resolution should be used."""
  return cfg.session == "-" or (
      isinstance(client, client_module.AlphaEvolveClient) and client.uses_mcp
  )


def list_experiments_aggregated(
    client: client_module.AlphaEvolveClient,
    cfg: config.Config,
    *,
    page_size: int = 100,
    warn_fn: collections.abc.Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
  """Fetches experiments across sessions and updates the disk cache.

  In MCP mode or when `cfg.session == "-"`, queries `list_experiments(
  session_id="-")` directly and extracts `_session_id` from each returned
  experiment resource name. Otherwise iterates over `list_sessions()`.

  Args:
    client: The API client.
    cfg: Resolved CLI configuration.
    page_size: Number of items per page.
    warn_fn: Optional callback for non-fatal debug warnings.

  Returns:
    A list of experiment dictionaries.
  """
  experiments: list[dict[str, Any]] = []
  if _is_wildcard_mode(cfg, client):
    for exp in client.list_experiments(session_id="-", page_size=page_size):
      exp_name = exp.get("name", "")
      if match := re.search(
          r"/sessions/([^/]+)/alphaEvolveExperiments/", exp_name
      ):
        exp["_session_id"] = match.group(1)
      experiments.append(exp)
  else:
    try:
      sessions = client.list_sessions()
      for s in sessions:
        s_name = s.get("name", "")
        if s_name:
          s_id = s_name.split("/")[-1]
          try:
            for exp in client.list_experiments(
                session_id=s_id, page_size=page_size
            ):
              exp["_session_id"] = s_id
              experiments.append(exp)
          except Exception as e:  # pylint: disable=broad-exception-caught
            if warn_fn is not None:
              warn_fn(f"DEBUG: list_experiments failed for session {s_id}: {e}")
    except client_module.ApiError:
      raise
    except Exception as e:  # pylint: disable=broad-exception-caught
      if warn_fn is not None:
        warn_fn(f"DEBUG: list_sessions failed: {e}")
      return []

  config.save_cache(f"experiments_list_{cfg.profile_name}", experiments)

  try:
    index = nicknames.NicknameIndex.load()
    index.add_many(experiments)
    index.save()
    flat_file = config.CACHE_DIR / f"experiments_{cfg.profile_name}.txt"
    completions = []
    for exp in experiments:
      name = exp.get("name", "")
      if name:
        completions.append(index.get_nickname(name))
        completions.append(name.split("/")[-1])
    flat_file.write_text("\n".join(set(completions)), encoding="utf-8")
  except OSError:
    pass

  return experiments


def resolve_experiment(
    identifier: str,
    client: client_module.AlphaEvolveClient,
    cfg: config.Config,
    *,
    index: nicknames.NicknameIndex | None = None,
    list_fn: collections.abc.Callable[[], list[dict[str, Any]]] | None = None,
    warn_fn: collections.abc.Callable[[str], None] | None = None,
) -> str:
  """Resolves an experiment nickname, short ID, or full resource name.

  In wildcard/MCP mode:
    - Preserves the concrete server-assigned session from `NicknameIndex` hits
      matching the active engine (never rewriting to `sessions/-`).
    - On a cold cache (e.g. after restart), refreshes via
      `list_experiments(session_id="-")` so raw IDs resolve to their concrete
      session resource name, and raises `ApiError(404)` rather than fabricating
      `.../sessions/-/alphaEvolveExperiments/<id>`.

  Args:
    identifier: Experiment nickname, short ID, or full resource name.
    client: The API client.
    cfg: Resolved CLI configuration.
    index: Optional pre-loaded `NicknameIndex` (defaults to loading from disk).
    list_fn: Optional callback returning aggregated experiments on cache miss.
    warn_fn: Optional callback for non-fatal debug warnings.

  Returns:
    The full experiment resource name.

  Raises:
    client_module.ApiError: With status 404 when not found in wildcard mode.
  """
  if "/" in identifier:
    return identifier

  is_wildcard = _is_wildcard_mode(cfg, client)
  engine_prefix = _engine_sessions_prefix(cfg)

  idx = index if index is not None else nicknames.NicknameIndex.load()
  res = idx.resolve(identifier)
  if res:
    if is_wildcard:
      if "/sessions/-/" not in res and (
          not engine_prefix or res.startswith(engine_prefix)
      ):
        return res
    else:
      if not res.startswith(cfg.parent):
        if match := re.search(r"/alphaEvolveExperiments/([^/]+)$", res):
          return cfg.experiment_name(match.group(1))
      return res

  experiments = (
      list_fn()
      if list_fn is not None
      else list_experiments_aggregated(client, cfg, warn_fn=warn_fn)
  )
  idx.add_many(experiments)
  idx.save()

  res = idx.resolve(identifier)
  if res:
    if is_wildcard:
      if "/sessions/-/" not in res and (
          not engine_prefix or res.startswith(engine_prefix)
      ):
        return res
    else:
      if not res.startswith(cfg.parent):
        if match := re.search(r"/alphaEvolveExperiments/([^/]+)$", res):
          return cfg.experiment_name(match.group(1))
      return res

  if is_wildcard:
    raise client_module.ApiError(
        404,
        f"Experiment '{identifier}' not found. Run `ae experiment list` to see"
        " available experiments, or pass the full resource name.",
    )

  return cfg.experiment_name(identifier)


def resolve_program(
    identifier: str,
    experiment: str | None,
    cfg: config.Config,
    *,
    get_client_fn: collections.abc.Callable[
        [], client_module.AlphaEvolveClient
    ],
    resolve_experiment_fn: collections.abc.Callable[[str], str],
    index: nicknames.NicknameIndex | None = None,
    is_mcp: bool = False,
) -> str:
  """Resolves a program nickname, short ID, or full resource name.

  Args:
    identifier: Program nickname, short ID, or full resource name.
    experiment: Optional parent experiment identifier.
    cfg: Resolved CLI configuration.
    get_client_fn: Lazily returns an `AlphaEvolveClient` when a network call is
      needed.
    resolve_experiment_fn: Resolves `experiment` to a full resource name.
    index: Optional pre-loaded `NicknameIndex`.
    is_mcp: Whether MCP mode is active.

  Returns:
    The full program resource name.

  Raises:
    ValueError: If `identifier` is not cached and `experiment` is not provided.
  """
  if "/" in identifier:
    return identifier

  is_wildcard = cfg.session == "-" or is_mcp
  engine_prefix = _engine_sessions_prefix(cfg)

  idx = index if index is not None else nicknames.NicknameIndex.load()
  res = idx.resolve(identifier)
  if res:
    if is_wildcard:
      if "/sessions/-/" not in res and (
          not engine_prefix or res.startswith(engine_prefix)
      ):
        return res
    else:
      if not res.startswith(cfg.parent):
        if match := re.search(
            r"/alphaEvolveExperiments/([^/]+)/alphaEvolvePrograms/([^/]+)$",
            res,
        ):
          return cfg.program_name(match.group(1), match.group(2))
      return res

  if not experiment:
    raise ValueError("Provide --experiment when using a short program ID.")

  exp_name = resolve_experiment_fn(experiment)
  prog_prefix = f"{exp_name}/alphaEvolvePrograms/"
  try:
    client = get_client_fn()
    programs = list(client.list_programs(exp_name))
    if programs:
      idx.add_many(programs)
      idx.save()
      res = idx.resolve(identifier)
      if res and (
          not is_wildcard
          or ("/sessions/-/" not in res and res.startswith(prog_prefix))
      ):
        return res
  except client_module.ApiError:
    pass

  return f"{prog_prefix}{identifier}"


def get_program(
    client: client_module.AlphaEvolveClient,
    cfg: config.Config,
    prog_name: str,
) -> dict[str, Any]:
  """Fetches a program from local cache or via `list_programs`."""
  parts = prog_name.rsplit("/alphaEvolvePrograms/", 1)
  if len(parts) != 2:
    raise client_module.ApiError(400, f"Invalid program name: {prog_name}")

  exp_name = parts[0]
  exp_id = exp_name.split("/")[-1]

  cached = read_cached_programs(cfg, exp_id)
  if cached:
    for p in cached:
      if p.get("name") == prog_name:
        return p

  programs = list(client.list_programs(exp_name))
  config.save_cache(f"programs_list_{cfg.profile_name}_{exp_id}", programs)

  for p in programs:
    if p.get("name") == prog_name:
      return p

  raise client_module.ApiError(404, f"Program not found: {prog_name}")
