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

"""Configuration management for ae.

Handles reading/writing of named TOML profiles stored at
~/.config/ae/profiles/*.toml, with layered resolution:
  CLI flags > CWD .env file > active profile > built-in defaults.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import tomllib
import typing

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

CONFIG_DIR = pathlib.Path.home() / ".config" / "ae"
PROFILES_DIR = CONFIG_DIR / "profiles"
ACTIVE_FILE = CONFIG_DIR / "active"
OPERATIONS_FILE = CONFIG_DIR / "operations.json"
CACHE_DIR = CONFIG_DIR / "cache"

BUILT_IN_DEFAULTS: dict[str, typing.Any] = {
    "project": "",
    "location": "global",
    "collection": "default_collection",
    "engine": "alpha-evolve-experiment-engine",
    "session": "[create new]",
    "model": "GEMINI_V2P5_FLASH",
    "base_url": "",
    "output_format": "table",
    "color": True,
}

# Map from .env variable names → config keys (for CWD .env loading).
_ENV_KEY_MAP: dict[str, str] = {
    "PROJECT_ID": "project",
    "LOCATION": "location",
    "COLLECTION": "collection",
    "ENGINE": "engine",
    "SESSION": "session",
    "ASSISTANT": "session",  # Alias for session
    "MODEL": "model",
    "BASE_URL": "base_url",
}


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


# Placeholder values that must never be sent to the API as-is.
_SESSION_PLACEHOLDERS = frozenset({"[create new]", "-", ""})

# A generation-model entry: {"name": str, "weight"?: float, plus any passthrough
# keys forwarded verbatim to the API}. Deliberately a type alias and not a
# TypedDict: we allow arbitrary passthrough keys, which a strict TypedDict would
# make pytype reject when callers add them.
ModelEntry: typing.TypeAlias = dict[str, typing.Any]


@dataclasses.dataclass
class Config:
  """Resolved configuration values."""

  project: str = ""
  location: str = "global"
  collection: str = "default_collection"
  engine: str = "alpha-evolve-experiment-engine"
  session: str = "default_session"
  model: str = "GEMINI_V2P5_FLASH"
  # Structured generation models from the `[[models]]` profile section.
  # Supersedes the scalar `model` enum, which is retained for backward
  # compatibility with legacy `[model]` profiles.
  models: list[ModelEntry] = dataclasses.field(default_factory=list)
  base_url: str = ""
  output_format: str = "table"
  color: bool = True

  # Computed (not stored in TOML).
  profile_name: str = "default"

  def has_valid_session(self) -> bool:
    """Returns True if the session value is a real ID, not a placeholder."""
    return bool(self.session) and self.session not in _SESSION_PLACEHOLDERS

  @property
  def parent(self) -> str:
    """Builds the full parent resource name prefix for the active session.

    Returns:
      The full resource path string.

    Raises:
      ValueError: If the session is a placeholder value like '[create new]'.
    """
    if not self.has_valid_session():
      raise ValueError(
          f"Session is not configured (value: {self.session!r}). "
          "Run `ae config -i` to create a session, or use "
          "`ae config --session=<session_id>`."
      )
    return (
        f"projects/{self.project}"
        f"/locations/{self.location}"
        f"/collections/{self.collection}"
        f"/engines/{self.engine}"
        f"/sessions/{self.session}"
    )

  def experiment_name(self, experiment_id: str) -> str:
    """Builds the full experiment resource name.

    Args:
      experiment_id: The short identifier for the experiment.

    Returns:
      The full resource path string layer target.
    """
    return f"{self.parent}/alphaEvolveExperiments/{experiment_id}"

  def program_name(
      self,
      experiment_id: str,
      program_id: str,
  ) -> str:
    """Builds the full program resource name.

    Args:
      experiment_id: The short identifier for the experiment.
      program_id: The short identifier for the program.

    Returns:
      The full resource path string layer target.
    """
    return (
        f"{self.parent}/alphaEvolveExperiments/{experiment_id}"
        f"/alphaEvolvePrograms/{program_id}"
    )


# ---------------------------------------------------------------------------
# Profile I/O
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
  """Create configuration directories if they do not exist."""
  PROFILES_DIR.mkdir(parents=True, exist_ok=True)
  CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_active_profile_name() -> str:
  """Returns the name of the active configuration profile.

  Returns:
    The string identifier of the active profile (defaulting to 'default').
  """
  if ACTIVE_FILE.exists():
    return ACTIVE_FILE.read_text(encoding="utf-8").strip() or "default"
  return "default"


def set_active_profile(name: str) -> None:
  """Sets the active configuration profile name.

  Args:
    name: The identifier of the profile to make active.
  """
  _ensure_dirs()
  ACTIVE_FILE.write_text(name + "\n", encoding="utf-8")


def list_profiles() -> list[str]:
  """Lists all available profile names.

  Returns:
    A sorted list of profile stem identifiers found in the profiles directory.
  """
  _ensure_dirs()
  return sorted(p.stem for p in PROFILES_DIR.glob("*.toml"))


def profile_path(name: str) -> pathlib.Path:
  """Returns the absolute filesystem path to a profile TOML file.

  Args:
    name: The profile identifier to locate.

  Returns:
    The full Path handle to the profile configuration file.
  """
  return PROFILES_DIR / f"{name}.toml"


def load_profile(name: str) -> dict[str, typing.Any]:
  """Loads a profile TOML file, returning a flat dict of config values.

  Args:
    name: The profile name to load.

  Returns:
    A flattened dictionary containing configuration parameters.
  """
  path = profile_path(name)
  if not path.exists():
    return {}
  with open(path, "rb") as f:
    data = tomllib.load(f)
  # Flatten sections into a single dict.
  flat: dict[str, typing.Any] = {}
  for key, section in data.items():
    if isinstance(section, dict):
      # This is a table section (e.g. "[defaults]"). Flatten it so the key-value
      # pairs are stored directly instead of using the section header (e.g.
      # "defaults") as key to a nested dict.
      flat.update(section)
    elif isinstance(section, list):
      # This is a list of tables section (e.g. "[[models]]"). Here, we keep the
      # section header as key pointing to a list of dicts with the actual
      # key-value pairs (e.g. "name", "weight" and their values).
      flat[key] = section
    else:
      # Top-level scalar (shouldn't happen with our schema, but handle it).
      pass
  return flat


def save_profile(
    name: str,
    values: dict[str, typing.Any],
) -> pathlib.Path:
  """Saves configuration values to a named profile TOML file.

  Args:
    name: The profile name string target.
    values: A flat dictionary containing parameters to store.

  Returns:
    The absolute Path string locating safe saved layout state description
    correctly.
  """
  _ensure_dirs()
  # Structure into sections matching our schema.
  doc: dict[str, typing.Any] = {
      "defaults": {},
      "model": {},
      "output": {},
  }
  _defaults_keys = {
      "project",
      "location",
      "collection",
      "engine",
      "session",
      "base_url",
  }
  _model_keys = {"model"}
  _output_keys = {"output_format", "color"}

  models_section: list[typing.Any] = []
  for k, v in values.items():
    if k == "models":
      # Structured `[[models]]` array-of-tables, emitted as its own section.
      models_section = v or []
    elif k in _defaults_keys:
      doc["defaults"][k] = v
    elif k in _model_keys:
      doc["model"][k] = v
    elif k in _output_keys:
      # Map output_format -> format in TOML for readability.
      key = "format" if k == "output_format" else k
      doc["output"][key] = v
    # Skip unknown keys.

  # Remove empty sections.
  doc = {k: v for k, v in doc.items() if v}
  # Append the array-of-tables last so its `[[models]]` headers never absorb a
  # following flat section's keys.
  if models_section:
    doc["models"] = models_section

  path = profile_path(name)
  with open(path, "w", encoding="utf-8") as f:
    f.write(_dump_toml(doc))
  return path


def save_session(profile_name: str, session_id: str) -> None:
  """Updates the session ID in an existing profile.

  Loads the profile, sets the session value, and saves it back.

  Args:
    profile_name: The profile to update.
    session_id: The new session ID.
  """
  path = profile_path(profile_name)
  values: dict[str, typing.Any] = {}
  if path.exists():
    with open(path, "rb") as f:
      values = tomllib.load(f)
  if "defaults" not in values:
    values["defaults"] = {}
  values["defaults"]["session"] = session_id
  with open(path, "w", encoding="utf-8") as f:
    f.write(_dump_toml(values))


def _toml_scalar(v: typing.Any) -> str:
  """Formats a scalar as a TOML value (bool, int/float unquoted; else string)."""
  if isinstance(v, bool):
    return str(v).lower()
  if isinstance(v, (int, float)):
    return str(v)
  dq = '"'
  escaped = str(v).replace("\\", "\\\\").replace(dq, "\\" + dq)
  return f"{dq}{escaped}{dq}"


def _dump_toml(doc: dict[str, typing.Any]) -> str:
  """Serialises a nested dict to a TOML string.

  Handles the value types our profile schema uses: flat sections of str/bool/
  numeric entries, plus array-of-tables sections (a list of dicts, e.g.
  `[[models]]`) whose entries may carry numeric weights.

  Args:
    doc: A dict whose values are either flat dicts of scalar entries or lists of
      such dicts (array-of-tables).

  Returns:
    A TOML-formatted string suitable for writing to a .toml file.
  """
  lines: list[str] = []
  for section, values in doc.items():
    if isinstance(values, list):
      # Array-of-tables: one `[[section]]` block per entry.
      for entry in values:
        lines.append(f"[[{section}]]")
        for k, v in entry.items():
          lines.append(f"{k} = {_toml_scalar(v)}")
        lines.append("")
      continue
    lines.append(f"[{section}]")
    for k, v in values.items():
      lines.append(f"{k} = {_toml_scalar(v)}")
    lines.append("")
  return "\n".join(lines)


def delete_profile(name: str) -> bool:
  """Deletes a profile configuration file.

  Args:
    name: The identifier of the profile to remove.

  Returns:
    True if the file existed and was safely unlinked; False otherwise.
  """
  path = profile_path(name)
  if path.exists():
    path.unlink()
    return True
  return False


# ---------------------------------------------------------------------------
# .env loading (for per-experiment overrides)
# ---------------------------------------------------------------------------


def _load_dotenv(path: pathlib.Path) -> dict[str, typing.Any]:
  """Parses a simple .env file into a config dictionary.

  Args:
    path: The Path locating the backing file accurately.

  Returns:
    A flat dictionary with resolved mapping variables layout overlays.
  """
  result: dict[str, typing.Any] = {}
  if not path.exists():
    return result
  for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
      continue
    if "=" not in line:
      continue
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    config_key = _ENV_KEY_MAP.get(key)
    if config_key:
      result[config_key] = value
  return result


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def load_config(
    cli_overrides: dict[str, typing.Any] | None = None,
    profile_name: str | None = None,
) -> Config:
  """Loads configuration with layered resolution.

  Priority (highest first):
    1. cli_overrides (from --project, --location, etc.)
    2. CWD .env file
    3. Active profile
    4. Built-in defaults

  Args:
    cli_overrides: Optional dictionary of overrides provided via CLI flags.
    profile_name: Optional name of the profile to load, bypassing active
      default.

  Returns:
    A resolved Config object ready for usage orchestrators binding correctly.
  """
  # Start with defaults.
  merged = dict(BUILT_IN_DEFAULTS)

  # Layer: active profile.
  pname = profile_name or get_active_profile_name()
  profile_vals = load_profile(pname)
  # Handle 'format' -> 'output_format' mapping from TOML.
  if "format" in profile_vals:
    profile_vals["output_format"] = profile_vals.pop("format")
  merged.update({k: v for k, v in profile_vals.items() if v is not None})

  # Layer: CWD .env.
  env_vals = _load_dotenv(pathlib.Path.cwd() / ".env")
  merged.update({k: v for k, v in env_vals.items() if v})

  # Layer: CLI flags.
  if cli_overrides:
    merged.update({k: v for k, v in cli_overrides.items() if v is not None})

  # Resolve project ID → project number.  The Discovery Engine API requires
  # numeric project numbers in resource paths.
  project = merged.get("project", "")
  if project:
    merged["project"] = resolve_project_number(project)

  # Build Config object.
  config_fields = {f.name for f in dataclasses.fields(Config)}
  filtered = {k: v for k, v in merged.items() if k in config_fields}
  cfg = Config(**filtered)
  cfg.profile_name = pname
  return cfg


# ---------------------------------------------------------------------------
# Project auto-detection
# ---------------------------------------------------------------------------


_GCLOUD_RC_PATTERN = re.compile(r"""['"]([^'"]+)/path\.(?:bash|zsh)\.inc['"]""")

# Common gcloud SDK installation paths to check when ``which`` fails
# (e.g. in non-interactive shells where ~/.bashrc PATH additions are skipped).
_GCLOUD_COMMON_PATHS: tuple[pathlib.Path, ...] = (
    pathlib.Path.home() / "google-cloud-sdk" / "bin" / "gcloud",
    pathlib.Path("/usr/lib/google-cloud-sdk/bin/gcloud"),
    pathlib.Path("/snap/google-cloud-sdk/current/bin/gcloud"),
    pathlib.Path("/opt/homebrew/bin/gcloud"),
    pathlib.Path("/usr/local/bin/gcloud"),
)


def _find_gcloud_in_rc_files(
    home: pathlib.Path | None = None,
) -> str | None:
  """Parses shell RC files for the gcloud SDK ``path.*.inc`` source line.

  The gcloud installer adds a line like::

      if [ -f '/path/to/sdk/path.bash.inc' ]; then
          . '/path/to/sdk/path.bash.inc'; fi

  to ``~/.bashrc`` (Linux) or ``~/.bash_profile`` / ``~/.zshrc`` (macOS).
  We extract the SDK root from that line and derive the binary path.

  Args:
    home: Home directory to search.  Defaults to ``pathlib.Path.home()``.

  Returns:
    The absolute path to the ``gcloud`` binary, or ``None`` if not found.
  """
  if home is None:
    home = pathlib.Path.home()
  rc_files = (
      home / ".bashrc",
      home / ".bash_profile",
      home / ".zshrc",
      home / ".profile",
  )
  for rc in rc_files:
    try:
      if not rc.is_file():
        continue
      for line in rc.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _GCLOUD_RC_PATTERN.search(line)
        if m:
          candidate = pathlib.Path(m.group(1)) / "bin" / "gcloud"
          if candidate.is_file():
            return str(candidate)
    except OSError:
      continue
  return None


@functools.lru_cache(maxsize=1)
def gcloud_path() -> str:
  r"""Returns the full path to the ``gcloud`` executable.

  Searches in order:

  1. ``shutil.which`` — finds ``gcloud`` (or ``gcloud.cmd`` on Windows)
     when it is already on ``PATH``.
  2. ``CLOUDSDK_ROOT_DIR`` env var — set inside active gcloud SDK sessions.
  3. Common installation directories on Linux and macOS.
  4. Shell RC files (``~/.bashrc``, ``~/.bash_profile``, ``~/.zshrc``,
     ``~/.profile``) — the gcloud installer adds a ``path.bash.inc`` /
     ``path.zsh.inc`` source line whose path reveals the SDK location.
     This is the primary fallback for non-interactive shells where the
     RC-file ``PATH`` additions are not applied.

  Returns:
    The resolved path string, or ``"gcloud"`` as a last-resort fallback
    (which will surface a clear ``FileNotFoundError`` at call time).
  """
  # 1. Already on PATH.
  found = shutil.which("gcloud")
  if found:
    return found

  # 2. CLOUDSDK_ROOT_DIR (set by the SDK itself in active sessions).
  sdk_root = os.environ.get("CLOUDSDK_ROOT_DIR")
  if sdk_root:
    candidate = os.path.join(sdk_root, "bin", "gcloud")
    if os.path.isfile(candidate):
      return candidate

  # 3. Common installation paths.
  for p in _GCLOUD_COMMON_PATHS:
    if p.is_file():
      return str(p)

  # 4. Parse shell RC files for the SDK path.
  from_rc = _find_gcloud_in_rc_files()
  if from_rc:
    return from_rc

  return "gcloud"


def detect_gcloud_project() -> str | None:
  """Resolves the current gcloud configurations project ID targets setup.

  Returns:
    The string project ID if found, else None correctly triggers.
  """
  try:
    result = subprocess.run(
        [gcloud_path(), "config", "get-value", "project"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    project = result.stdout.strip()
    return project if project and "(unset)" not in project else None
  except (FileNotFoundError, subprocess.TimeoutExpired):
    return None


def resolve_project_number(project: str) -> str:
  """Resolves a GCP project ID to its numeric project number.

  The Discovery Engine API requires numeric project numbers in resource
  paths.  If ``project`` is already numeric it is returned as-is.
  Otherwise we call ``gcloud projects describe`` to look up the number and
  cache the result on disk so subsequent invocations are fast.

  Args:
   project: A GCP project ID (e.g. ``"my-project"``) or project number.

  Returns:
   The numeric project number string, or the original ``project`` value if
   resolution fails (e.g. no network, gcloud unavailable).
  """
  if not project:
    return project

  # Already numeric — nothing to do.
  if project.isdigit():
    return project

  # Check on-disk cache first (no TTL — project numbers never change).
  cache = get_cache("project_number_map", ttl_seconds=None) or {}
  cached_number = cache.get(project)
  if cached_number:
    return cached_number

  # Resolve via gcloud.  We use ``--format=json`` instead of
  # ``--format=value(projectNumber)`` because PowerShell on Windows
  # interprets the parentheses as a sub-expression and breaks the command.
  try:
    result = subprocess.run(
        [
            gcloud_path(),
            "projects",
            "describe",
            project,
            "--format=json",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
      try:
        data = json.loads(result.stdout)
        number = str(data.get("projectNumber", ""))
      except (json.JSONDecodeError, TypeError, AttributeError):
        number = ""
      if number and number.isdigit():
        # Persist to cache atomically.
        cache[project] = number
        save_cache("project_number_map", cache)
        return number
  except (FileNotFoundError, subprocess.TimeoutExpired):
    pass

  # Resolution failed — the project ID is non-numeric and gcloud could not
  # resolve it.  Warn so the user (or agent) knows to provide the numeric
  # project number directly.
  print(
      f"WARNING: Could not resolve project '{project}' to a numeric project"
      " number. The Discovery Engine API requires a numeric project number."
      " Please set the numeric project number directly:\n"
      "  ae config --project=<NUMERIC_PROJECT_NUMBER>",
      file=sys.stderr,
  )
  return project


def list_gcloud_projects() -> list[dict[str, str]]:
  """Lists accessible GCP projects for the authenticated user triggers.

  Returns:
    A list of dictionary targets including 'projectId' and 'name'.
  """
  try:
    result = subprocess.run(
        [
            gcloud_path(),
            "projects",
            "list",
            "--format=json",
            "--limit=50",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
      return []
    projects = json.loads(result.stdout)
    return [
        {"projectId": p.get("projectId", ""), "name": p.get("name", "")}
        for p in projects
    ]
  except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
    return []


# ---------------------------------------------------------------------------
# LRO operations cache
# ---------------------------------------------------------------------------


def save_operation(
    experiment_name: str,
    operation_name: str,
) -> None:
  """Caches an LRO operation name associated with an experiment.

  Args:
    experiment_name: The full resource name of the experiment.
    operation_name: The full resource name of the operation to cache.
  """
  _ensure_dirs()
  ops: dict[str, str] = {}
  if OPERATIONS_FILE.exists():
    ops = json.loads(OPERATIONS_FILE.read_text(encoding="utf-8"))
  ops[experiment_name] = operation_name
  OPERATIONS_FILE.write_text(json.dumps(ops, indent=2), encoding="utf-8")


def get_operation(experiment_name: str) -> str | None:
  """Retrieves the cached LRO operation name for an experiment.

  Args:
    experiment_name: The full resource name of the experiment.

  Returns:
    The cached operation name string if found, else None correctly.
  """
  if not OPERATIONS_FILE.exists():
    return None
  ops = json.loads(OPERATIONS_FILE.read_text(encoding="utf-8"))
  return ops.get(experiment_name)


def remove_operation(experiment_name: str) -> None:
  """Removes a cached LRO operation name from the operations index.

  Args:
    experiment_name: The full resource name of the experiment to purge.
  """
  if not OPERATIONS_FILE.exists():
    return
  ops = json.loads(OPERATIONS_FILE.read_text(encoding="utf-8"))
  ops.pop(experiment_name, None)
  OPERATIONS_FILE.write_text(json.dumps(ops, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Disk Cache
# ---------------------------------------------------------------------------


def save_cache(
    key: str,
    data: typing.Any,
) -> None:
  """Saves data to disk cache using an atomic temp-and-rename pattern.

  Args:
    key: The cache key identifying the item.
    data: The payload to store (must be JSON serializable).
  """
  _ensure_dirs()
  cache_file = CACHE_DIR / f"{key}.json"
  cache_data = {"timestamp": time.time(), "data": data}
  temp_file = cache_file.with_suffix(f".tmp.{os.getpid()}")
  temp_file.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
  temp_file.replace(cache_file)


def get_cache(
    key: str,
    ttl_seconds: int | None = 120,
) -> typing.Any | None:
  """Retrieves data from disk cache if it hasn't expired.

  Args:
    key: The cache key identifying the item.
    ttl_seconds: Maximum age in seconds before the entry is considered stale.
      ``None`` means the cache never expires.

  Returns:
    The cached payload if valid, else None.
  """
  cache_file = CACHE_DIR / f"{key}.json"
  if not cache_file.exists():
    return None
  try:
    cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
    if ttl_seconds is not None:
      ts = cache_data.get("timestamp", 0)
      if time.time() - ts > ttl_seconds:
        return None
    return cache_data.get("data")
  except (json.JSONDecodeError, TypeError):
    return None


def clear_cache() -> None:
  """Clears all cached items from the disk cache directory."""
  if CACHE_DIR.exists():
    for f in CACHE_DIR.glob("*.json"):
      f.unlink()
