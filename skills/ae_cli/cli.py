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

"""AlphaEvolve CLI — interact with the AlphaEvolve Cloud API."""

from __future__ import annotations

import ast
from collections.abc import Mapping
import datetime
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
from typing import Annotated, Any, NoReturn, Optional, TypedDict

# ---------------------------------------------------------------------------
# Encoding — ensure console I/O uses UTF-8 on all platforms.
#
# On Windows, Python defaults to the system locale encoding (often cp1252)
# for console streams.  Rich's legacy Windows renderer writes Unicode
# characters (✓, ━, ★, …) through sys.stdout's write() method, which
# crashes with UnicodeEncodeError when the codec is cp1252.
#
# This block MUST run before ``import rich`` / ``import typer`` because
# formatting.py (imported below) creates a ``Console()`` at import time
# that captures a reference to sys.stdout.
# ---------------------------------------------------------------------------
os.environ.setdefault("PYTHONUTF8", "1")
for _stream in (
    sys.stdout,
    sys.stderr,
    sys.stdin,
    getattr(sys, "__stdout__", None),
    getattr(sys, "__stderr__", None),
    getattr(sys, "__stdin__", None),
):
  if _stream is not None and hasattr(_stream, "reconfigure"):
    try:
      _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
      pass
del _stream

import immutabledict  # pylint: disable=g-import-not-at-top
import rich
import typer
from typer import _completion_classes
from typer import _completion_shared

from . import client as client_module
from . import config
from . import controller as controller_module
from . import dashboard
from . import evaluator as evaluator_module
from . import formatting
from . import locks
from . import nicknames
from . import skills_install
from . import version as ae_version
from . import visualization

# Initialize completion classes explicitly since add_completion=False disables
# it.
_completion_classes.completion_init()

# Typer (and Click) uses sys.argv[0] to derive the program name and completion
# variable. When running from a .par archive, sys.argv[0] resolves to 'ae.par'.
# To avoid forming completion variables with dots (e.g., _AE.PAR_COMPLETE),
# which shells like Bash prohibit, we sanitize it to 'ae'.
if sys.argv[0].endswith(".par"):
  sys.argv[0] = sys.argv[0][:-4]
elif os.path.basename(sys.argv[0]) == "ae.par":
  sys.argv[0] = "ae"

app = typer.Typer(
    name="ae",
    help="CLI for the AlphaEvolve Cloud API.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)

experiment_app = typer.Typer(
    help="Manage experiments.",
    no_args_is_help=True,
)
program_app = typer.Typer(
    help="Manage programs.",
    no_args_is_help=True,
)
results_app = typer.Typer(
    help="View results.",
    no_args_is_help=True,
)
config_app = typer.Typer(
    help="Manage CLI configuration.",
    no_args_is_help=False,
)
completion_app = typer.Typer(
    help="Manage shell completion.",
    no_args_is_help=True,
)
engine_app = typer.Typer(
    help="Manage Discovery Engine engines.",
    no_args_is_help=True,
)

app.add_typer(experiment_app, name="experiment")
app.add_typer(program_app, name="program")
app.add_typer(results_app, name="results")
app.add_typer(config_app, name="config")
app.add_typer(completion_app, name="completion")
app.add_typer(engine_app, name="engine")
app.add_typer(skills_install.skills_app, name="skills")


class _ModelConfig(TypedDict):
  """A single entry (model name + relative weight) in a `models` mixture."""

  name: str
  weight: float


# Maps each `--model` CLI value to the AlphaEvolve API's generation `models`
# field. The API selects generation models via the repeated `models` field,
# which replaced an earlier single-`model` setting; the `--model` flag is kept
# stable for existing users and expanded here into the equivalent entries.
# `gemini_v3p1_pro` is deprecated and maps to no entries, so the API applies
# its default model.
_MODEL_TO_MODELS: Mapping[str, tuple[_ModelConfig, ...]] = (
    immutabledict.immutabledict({
        "gemini_v2p5_flash": (
            _ModelConfig(name="gemini-2.5-flash", weight=1.0),
        ),
        "gemini_v2p5_mixture": (
            _ModelConfig(name="gemini-2.5-flash", weight=0.9),
            _ModelConfig(name="gemini-2.5-pro", weight=0.1),
        ),
        "gemini_v3p0_mixture": (
            _ModelConfig(name="gemini-3-flash-preview", weight=1.0),
        ),
        "gemini_v3p1_mixture": (
            _ModelConfig(name="gemini-3-flash-preview", weight=0.9),
            _ModelConfig(name="gemini-3.1-pro-preview", weight=0.1),
        ),
        "gemini_v3p1_fifty_fifty_mixture": (
            _ModelConfig(name="gemini-3-flash-preview", weight=0.5),
            _ModelConfig(name="gemini-3.1-pro-preview", weight=0.5),
        ),
        "gemini_v3p1_pro": (),
    })
)


# Maps enum-form profile `[model]` values (e.g. `GEMINI_V2P5_FLASH`) back to the
# lowercase `_MODEL_TO_MODELS` preset keys so a legacy `[model]` profile can
# still select a model for `experiment create`.
_ENUM_TO_PRESET: Mapping[str, str] = immutabledict.immutabledict(
    {preset.upper(): preset for preset in _MODEL_TO_MODELS}
)


def _warn(message: str) -> None:
  """Writes a non-fatal notice to stderr (keeps --json stdout parseable)."""
  typer.echo(message, err=True)


def _err(message: str) -> NoReturn:
  """Writes an error to stderr and exits with a non-zero status."""
  typer.echo(f"Error: {message}", err=True)
  raise typer.Exit(code=1)


def _parse_models_flag(tokens: list[str]) -> list[config.ModelEntry]:
  """Parses repeatable `--models` tokens into normalized model entries.

  Each token is either a bare model name (``gemini-3.5-flash``) or a
  comma-separated list of ``key=value`` fields (``name=...,weight=...``). `name`
  is required and non-empty; `weight`, when present, must parse as a float. Any
  other key is passed through verbatim (as a string) with a non-fatal stderr
  warning, so the surface needs no change when `ModelConfig` gains fields. Only
  structural validation is done; model-name/weight semantics are left to the
  API.

  Args:
    tokens: The raw `--models` option values.

  Returns:
    A list of dicts shaped like ``{"name": str, "weight"?: float, ...}``.

  Raises:
    typer.Exit: If a token is empty/unparseable, lacks a `name`, or carries a
      non-float `weight`.
  """
  parsed: list[config.ModelEntry] = []
  for raw in tokens:
    token = raw.strip()
    if not token:
      _err("empty --models entry")
    if "=" not in token:
      parsed.append({"name": token})  # bare-name shorthand
      continue
    entry: config.ModelEntry = {}
    for field in token.split(","):
      field = field.strip()
      if not field:
        continue
      key, sep, value = field.partition("=")
      key = key.strip()
      value = value.strip()
      if not sep or not key:
        _err(f"invalid --models field {field!r}; expected key=value")
      if key == "name":
        entry["name"] = value
      elif key == "weight":
        try:
          entry["weight"] = float(value)
        except ValueError:
          _err(f"invalid weight {value!r} in --models; must be a number")
      else:
        entry[key] = value
        _warn(f"unrecognized model field '{key}', sending as-is")
    if not entry.get("name"):
      _err(f"--models entry {token!r} is missing a non-empty name")
    parsed.append(entry)
  return parsed


def _legacy_model_to_models(preset: str) -> list[config.ModelEntry]:
  """Expands a legacy `--model`/`[model]` preset into `models` entries.

  Args:
    preset: A legacy preset key (e.g. `gemini_v2p5_flash`); see
      `_MODEL_TO_MODELS`.

  Returns:
    Freshly copied `{"name", "weight"}` dicts (so the immutable
    `_MODEL_TO_MODELS` constant is never aliased into a request body). An
    unknown preset yields an empty list; callers that must reject unknown
    presets check `_MODEL_TO_MODELS` membership first.
  """
  return [dict(entry) for entry in _MODEL_TO_MODELS.get(preset, ())]


def _resolve_models(
    models_flag: list[config.ModelEntry] | None,
    model_flag: str,
    cfg_models: list[config.ModelEntry] | None,
    cfg_model: str | None,
) -> list[config.ModelEntry]:
  """Resolves the effective `models` list from all sources by precedence.

  Highest priority first: the `--models` flag, the legacy `--model` flag, the
  config `[[models]]` section, and the legacy config `[model]` section. Every
  source is normalized to the single ``list[dict]`` shape, so the CLI
  structurally can only ever emit `models` (and never the mutually exclusive
  `model`/`model_mixture`). The result is empty when nothing is set, or when the
  winning source expands to no entries (e.g. ``gemini_v3p1_pro``); an empty
  result leaves `generationSettings.models` unset so the API applies its own
  default.

  Deprecation/migration notices go to stderr and fire only when a legacy source
  is actually used.

  Args:
    models_flag: Parsed `--models` entries, or None when the flag was absent.
    model_flag: The legacy `--model` value, or "" when absent.
    cfg_models: The config `[[models]]` carrier (may be empty).
    cfg_model: The config `[model]` preset (already mapped to a
      `_MODEL_TO_MODELS` key), or None when it should not contribute.

  Returns:
    The normalized `models` list (possibly empty).

  Raises:
    typer.Exit: If the legacy `--model` flag value is not an allowed preset.
  """
  # Tier 1: --models flag.
  if models_flag:
    if model_flag:
      _warn("both --model and --models supplied; using --models")
    return models_flag
  # Tier 2: legacy --model flag (keeps its allowlist + byte-identical output).
  if model_flag:
    _warn("--model is deprecated; use --models")
    if model_flag not in _MODEL_TO_MODELS:
      valid_models = list(_MODEL_TO_MODELS)
      _err(f"Invalid model: {model_flag}. Must be one of {valid_models}")
    return _legacy_model_to_models(model_flag)
  # Tier 3: config [[models]].
  if cfg_models:
    return [dict(entry) for entry in cfg_models]
  # Tier 4: legacy config [model].
  if cfg_model:
    _warn(
        "profile [model] is deprecated; migrate to [[models]] via"
        " `ae config --models`"
    )
    return _legacy_model_to_models(cfg_model)
  # Tier 5: nothing specified anywhere. Return empty so `experiment create`
  # leaves `generationSettings.models` unset and the API applies its default.
  return []


def _config_model_preset(cfg: config.Config) -> str | None:
  """Maps a profile `[model]` enum to a preset key for `_resolve_models`.

  Args:
    cfg: The resolved CLI configuration whose `[model]` profile value is mapped.

  Returns:
    The matching `_MODEL_TO_MODELS` preset key, or None when the profile
    model is just the built-in default (so the resolver's default tier applies
    silently) or cannot be mapped to a known preset (warned, then treated as
    the default; never crashes legacy profiles).
  """
  if not cfg.model or cfg.model == config.BUILT_IN_DEFAULTS["model"]:
    return None
  preset = _ENUM_TO_PRESET.get(cfg.model)
  if preset is None:
    _warn(
        f"profile [model] {cfg.model!r} is not a known preset; using the"
        " default model"
    )
  return preset


@engine_app.command("list")
def engine_list() -> None:
  """List available engines in the configured project."""
  try:
    client = _state.get_client()
    engines = list(client.list_engines())
    if not engines:
      if _state.json_output:
        print(json.dumps([]))
      else:
        rich.print("[dim]No engines found.[/dim]")
      return

    if _state.json_output:
      print(json.dumps(engines, indent=2, default=str))
    else:
      cfg = _state.resolve_config()
      formatting.console.print(
          formatting.format_engine_table(engines, active_engine=cfg.engine)
      )
  except client_module.ApiError as e:
    _handle_api_error(e)


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------


class GlobalState:
  """Container for global options passed to all commands."""

  def __init__(self) -> None:
    self.project: str | None = None
    self.location: str | None = None
    self.json_output: bool = False
    self.compact: bool = False
    self.verbose: bool = False
    self.interactive: bool = False

  def resolve_config(self) -> config.Config:
    """Resolve config with CLI overrides applied."""
    overrides: dict[str, Any] = {}
    if self.project:
      overrides["project"] = self.project
    if self.location:
      overrides["location"] = self.location
    return config.load_config(cli_overrides=overrides)

  def get_client(self) -> client_module.AlphaEvolveClient:
    """Create an API client from resolved config.

    If the session is a placeholder (e.g., '[create new]'), auto-creates
    a new session and saves it to the active profile.

    Returns:
      An initialized AlphaEvolveClient.
    """
    cfg = self.resolve_config()
    if not cfg.project:
      rich.print(
          "[red]Error:[/red] No project configured. "
          "Run [bold]ae config -i[/bold] or pass --project=<id>."
      )
      raise typer.Exit(1)

    # Auto-create a session if the config has a placeholder value.
    # The client can be constructed with a placeholder — only
    # config.parent raises ValueError when accessed. create_session()
    # builds its own parent URL without the session component.
    if not cfg.has_valid_session():
      if not _state.json_output:
        rich.print(
            "[dim]Session not configured. Creating a new session...[/dim]"
        )
      try:
        client = client_module.AlphaEvolveClient(cfg, verbose=self.verbose)
        new_session_id = client.create_session()
        cfg.session = new_session_id
        # Persist the new session ID to the active profile.
        config.save_session(cfg.profile_name, new_session_id)
        if not _state.json_output:
          rich.print(
              f"[green]✓[/green] Created session: [bold]{new_session_id}[/bold]"
          )
      except ValueError as e:
        # Config error (e.g. non-numeric project) — print without the
        # misleading "Error creating session" prefix.
        rich.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
      except Exception as e:
        rich.print(f"[red]Error creating session:[/red] {e}")
        rich.print(
            "Run [bold]ae config -i[/bold] to configure a session manually."
        )
        raise typer.Exit(1)

    try:
      return client_module.AlphaEvolveClient(cfg, verbose=self.verbose)
    except ValueError as e:
      rich.print(f"[red]Error:[/red] {e}")
      raise typer.Exit(1)

  def output(
      self,
      data: Any,
      *,
      index: nicknames.NicknameIndex | None = None,
      table_fn: Any = None,
  ) -> None:
    """Print data in the configured format."""
    if self.json_output:
      print(formatting.to_json(data, nickname_field="nickname", index=index))
      return
    if self.compact:
      if isinstance(data, list):
        for item in data:
          if isinstance(item, dict):
            print("\t".join(str(v) for v in item.values()))
          else:
            print(item)
      elif isinstance(data, dict):
        print("\t".join(str(v) for v in data.values()))
      else:
        print(data)
      return
    # Rich table output.
    if table_fn:
      formatting.console.print(table_fn)
    elif isinstance(data, dict):
      for k, v in data.items():
        rich.print(f"  [bold]{k}:[/bold] {v}")
    else:
      print(data)


_state = GlobalState()

# pylint: disable=bad-whitespace


@app.callback()
def main(
    project: Annotated[
        Optional[str], typer.Option("--project", help="GCP project ID.")
    ] = None,
    location: Annotated[
        Optional[str], typer.Option("--location", help="API location.")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="JSON output mode.")
    ] = False,
    compact: Annotated[
        bool, typer.Option("--compact", help="Compact output mode.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Debug logging.")
    ] = False,
) -> None:
  """AlphaEvolve CLI — interact with the AlphaEvolve Cloud API."""
  # pylint: enable=bad-whitespace
  _state.project = project
  _state.location = location
  _state.json_output = json_output
  _state.compact = compact
  _state.verbose = verbose


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _handle_api_error(e: client_module.ApiError) -> None:
  """Display a formatted API error and exit."""
  if _state.json_output:
    print(
        json.dumps({"error": {"status": e.status_code, "message": e.message}})
    )
  else:
    formatting.console.print(
        formatting.format_error(e.status_code, e.message, e.details)
    )
  raise typer.Exit(1)


def _prepare_program_files_payload(
    file_paths: list[str],
) -> list[dict[str, str]]:
  """Reads file contents and sanitizes paths (keeps only basename)."""
  payload = []
  for fpath in file_paths:
    with open(fpath, encoding="utf-8") as f:
      payload.append({
          "path": os.path.basename(fpath),
          "content": f.read(),
      })
  return payload


def _prepare_program_dir_payload(
    dir_path: str,
) -> list[dict[str, str]]:
  """Reads all .py files from a directory into a program files payload.

  Excludes evaluator.py, test files, and __pycache__ to avoid bundling
  non-program files. The evaluator is provided separately via --evaluator.

  Args:
    dir_path: Path to the directory containing program files.

  Returns:
    List of dicts with 'path' and 'content' keys.

  Raises:
    typer.Exit: If the directory doesn't exist or contains no .py files.
  """
  p_dir = pathlib.Path(dir_path)
  if not p_dir.is_dir():
    rich.print(f"[red]Error:[/red] Not a directory: {dir_path}")
    raise typer.Exit(1)

  # Exclude evaluator, tests, and config files -- only bundle program files.
  exclude_prefixes = ("test_",)
  exclude_names = {"evaluator.py", "setup.py", "conftest.py"}

  py_files = sorted(p_dir.glob("*.py"))
  py_files = [
      f
      for f in py_files
      if f.name not in exclude_names
      and not any(f.name.startswith(p) for p in exclude_prefixes)
  ]

  if not py_files:
    rich.print(
        f"[red]Error:[/red] No program .py files found in {dir_path}"
        " (evaluator.py and test files are excluded)."
    )
    raise typer.Exit(1)

  if not (p_dir / "initial_program.py").is_file():
    rich.print(
        f"[red]Error:[/red] {dir_path} does not contain"
        " initial_program.py. The main program file must be named"
        " initial_program.py."
    )
    raise typer.Exit(1)

  payload = []
  total_chars = 0
  for fp in py_files:
    content = fp.read_text(encoding="utf-8")
    total_chars += len(content)
    payload.append({"path": fp.name, "content": content})

  # Warn if total content is large (may degrade LLM quality).
  estimated_tokens = total_chars // 4
  if estimated_tokens > 200_000 and not _state.json_output:
    rich.print(
        "[yellow]Warning:[/yellow] Total program content is"
        f" ~{estimated_tokens:,} tokens. Context quality may degrade above"
        " ~200k tokens. Consider reducing the number of files or extracting"
        " only the optimization target."
    )

  return payload


def _run_with_spinner(
    msg: str,
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
  """Run a function with a rich status spinner."""
  with rich.get_console().status(msg):
    return func(*args, **kwargs)


def _invalidate_cache() -> None:
  """Invalidate the experiments list cache files."""
  cache_file = config.CACHE_DIR / "experiments_list.json"
  flat_file = config.CACHE_DIR / "experiments.txt"
  for f in [cache_file, flat_file]:
    if f.exists():
      try:
        f.unlink()
      except OSError:
        pass


def _read_cached_experiments() -> list[dict[str, Any]] | None:
  """Read experiments from cache, or None if unavailable."""
  cfg = _state.resolve_config()
  cache_file = config.CACHE_DIR / f"experiments_list_{cfg.profile_name}.json"
  if cache_file.exists():
    try:
      cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
      return cache_data.get("data")
    except (json.JSONDecodeError, AttributeError, TypeError):
      pass
  return None


def _read_cached_programs(exp_id: str) -> list[dict[str, Any]] | None:
  """Read programs from cache, or None if unavailable."""
  cfg = _state.resolve_config()
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


def _list_experiments_aggregated(
    client: client_module.AlphaEvolveClient,
    page_size: int = 100,
) -> list[dict[str, Any]]:
  """Fetch experiments from the API and update the cache.

  This function ALWAYS hits the API — it never reads from cache.
  Cache is only consumed by tab-completion and TUI initial population.

  Args:
    client: The AlphaEvolveClient instance to use.
    page_size: Number of items to fetch per page.

  Returns:
    A list of experiment dictionaries aggregated from all sessions.
  """
  cfg = _state.resolve_config()
  experiments = []

  # Always aggregate experiments across all sessions to ensure comprehensive
  # listing.
  with rich.get_console().status("Querying AlphaEvolve..."):
    try:
      sessions = client.list_sessions()
      for s in sessions:
        s_name = s.get("name", "")
        if s_name:
          s_id = s_name.split("/")[-1]
          try:
            exp_gen = client.list_experiments(
                session_id=s_id, page_size=page_size
            )
            for exp in exp_gen:
              exp["_session_id"] = s_id
              experiments.append(exp)
          except Exception as e:  # pylint: disable=broad-exception-caught
            rich.print(
                f"[dim]DEBUG: list_experiments failed for session {s_id}:"
                f" {e}[/dim]"
            )
            continue
    except client_module.ApiError:
      raise
    except Exception as e:  # pylint: disable=broad-exception-caught
      rich.print(f"[dim]DEBUG: list_sessions failed: {e}[/dim]")
      return []

  # Write to cache (consumed by tab-completion and TUI).
  config.save_cache(f"experiments_list_{cfg.profile_name}", experiments)

  # Save flat completion file for instant shell completions.
  try:
    index = nicknames.NicknameIndex.load()
    index.add_many(experiments)
    index.save()

    flat_file = config.CACHE_DIR / f"experiments_{cfg.profile_name}.txt"
    completions = []
    for exp in experiments:
      name = exp.get("name", "")
      if name:
        nickname = index.get_nickname(name)
        exp_id = name.split("/")[-1]
        completions.append(nickname)
        completions.append(exp_id)
    flat_file.write_text("\n".join(set(completions)), encoding="utf-8")
  except OSError:
    pass

  return experiments


def _autocomplete_experiment(incomplete: str) -> list[str]:
  """Autocompletion resolver for experiment nicknames and IDs."""
  cfg = _state.resolve_config()
  experiments = (
      config.get_cache(
          f"experiments_list_{cfg.profile_name}", ttl_seconds=2**30
      )
      or []
  )

  if not experiments:
    try:
      client = _state.get_client()
      experiments = _list_experiments_aggregated(client)
    except Exception:  # pylint: disable=broad-exception-caught
      return []

  try:
    index = nicknames.NicknameIndex.load()
  except Exception:  # pylint: disable=broad-exception-caught
    index = nicknames.NicknameIndex()
    index.add_many(experiments)

  results = []
  for exp in experiments:
    name = exp.get("name", "")
    if not name:
      continue
    nickname = index.get_nickname(name)
    exp_id = name.split("/")[-1]

    if nickname and nickname.startswith(incomplete):
      results.append(nickname)
    elif exp_id.startswith(incomplete):
      results.append(exp_id)

  return list(set(results))


def _resolve_experiment(
    identifier: str,
    client: client_module.AlphaEvolveClient | None = None,
) -> str:
  """Resolve an experiment identifier to full name."""
  cfg = _state.resolve_config()
  if "/" in identifier:
    return identifier

  if not client:
    client = _state.get_client()

  # Check the persistent index first to avoid a network round-trip.
  index = nicknames.NicknameIndex.load()
  res = index.resolve(identifier)
  if res:
    if not res.startswith(cfg.parent):
      if match := re.search(r"/alphaEvolveExperiments/([^/]+)$", res):
        return cfg.experiment_name(match.group(1))
    return res

  experiments = _list_experiments_aggregated(client)
  index.add_many(experiments)
  index.save()

  res = index.resolve(identifier)
  if res:
    if not res.startswith(cfg.parent):
      if match := re.search(r"/alphaEvolveExperiments/([^/]+)$", res):
        return cfg.experiment_name(match.group(1))
    return res

  return cfg.experiment_name(identifier)


def _resolve_program(
    identifier: str,
    experiment: str | None = None,
) -> str:
  """Resolve a program identifier to full name.

  Resolution order:
    1. Full resource name (passthrough).
    2. Persistent NicknameIndex lookup (fast, no network).
    3. If --experiment is provided: list programs from that experiment,
       rebuild the index, and resolve the nickname.
    4. If the identifier looks like a raw program ID (not a nickname),
       construct the resource name directly.

  Args:
    identifier: Nickname, short ID, or full resource name.
    experiment: Optional parent experiment (nickname, short ID, or full name).

  Returns:
    Full resource name string.

  Raises:
    typer.Exit: If resolution fails.
  """
  if "/" in identifier:
    return identifier

  cfg = _state.resolve_config()

  # Check the persistent index first to avoid a network round-trip.
  index = nicknames.NicknameIndex.load()
  res = index.resolve(identifier)
  if res:
    if not res.startswith(cfg.parent):
      # Session mismatch. Rebuild with current session.
      if match := re.search(
          r"/alphaEvolveExperiments/([^/]+)/alphaEvolvePrograms/([^/]+)$",
          res,
      ):
        return cfg.program_name(match.group(1), match.group(2))
    return res

  if not experiment:
    rich.print(
        "[red]Error:[/red] Provide --experiment when using a short program ID."
    )
    raise typer.Exit(1)

  # The identifier was not in the index. If --experiment is given, list
  # programs from that experiment to rebuild the nickname index and try
  # resolving again. This handles the case where `results best` or
  # `experiment run` populated nicknames in a previous session but the
  # index was lost, or when the identifier is a nickname not yet indexed.
  exp_name = _resolve_experiment(experiment)
  try:
    client = _state.get_client()
    programs = list(client.list_programs(exp_name))
    if programs:
      index.add_many(programs)
      index.save()
      res = index.resolve(identifier)
      if res:
        return res
  except client_module.ApiError:
    pass  # Fall through to raw ID construction below.

  # Last resort: treat identifier as a raw program ID.
  return cfg.program_name(
      exp_name.rsplit("/alphaEvolveExperiments/", 1)[-1],
      identifier,
  )


def _get_program(
    client: client_module.AlphaEvolveClient,
    prog_name: str,
) -> dict[str, Any]:
  """Fetch a program, checking the local cache first.

  If `ae program list` was previously called for the parent experiment,
  the result is cached on disk.  We check that cache before falling back
  to a (potentially expensive) list+filter call via the client.

  Args:
    client: The API client.
    prog_name: Full resource name of the program.

  Returns:
    The program dictionary.

  Raises:
    client_module.ApiError: If the program cannot be found.
  """
  # Try the on-disk programs cache.
  parts = prog_name.rsplit("/alphaEvolvePrograms/", 1)
  if len(parts) != 2:
    raise client_module.ApiError(400, f"Invalid program name: {prog_name}")

  exp_name = parts[0]
  exp_id = exp_name.split("/")[-1]

  # Try the on-disk programs cache.
  cached = _read_cached_programs(exp_id)
  if cached:
    for p in cached:
      if p.get("name") == prog_name:
        return p

  # Cache miss — fall back to list+filter via the client.
  cfg = _state.resolve_config()
  programs = list(client.list_programs(exp_name))

  # Save to on-disk cache for subsequent fast lookups.
  config.save_cache(f"programs_list_{cfg.profile_name}_{exp_id}", programs)

  for p in programs:
    if p.get("name") == prog_name:
      return p

  raise client_module.ApiError(404, f"Program not found: {prog_name}")


# ---------------------------------------------------------------------------
# Version command
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
  """Show the CLI version."""
  print(f"ae {ae_version.__version__}")


# ---------------------------------------------------------------------------
# Completion commands
# ---------------------------------------------------------------------------


@completion_app.command("install")
def completion_install(
    shell: Optional[str] = typer.Argument(
        None, help="The shell to install completion for (e.g. fish, bash, zsh)."
    ),
) -> None:
  """Install completion for your shell."""
  try:
    shell_installed, path = _completion_shared.install(shell=shell)
    rich.print(
        "[green]✓[/green] Completion installed for"
        f" [bold]{shell_installed}[/bold]"
    )
    rich.print(f"  Location: {path}")
    rich.print(
        "\n[yellow]Note:[/yellow] If using an alias outside PATH, you must"
        " update the script with the absolute binary path."
    )
  except Exception as e:
    rich.print(f"[red]Error:[/red] Failed to install completion: {e}")
    raise typer.Exit(1)


@completion_app.command("show")
def completion_show(
    shell: Optional[str] = typer.Argument(
        None, help="The shell to show completion for (e.g. fish, bash, zsh)."
    ),
) -> None:
  """Show completion script for your shell."""
  if shell is None:
    shell = os.environ.get("SHELL")
    if shell:
      shell = os.path.basename(shell)
    if not shell:
      rich.print(
          "[red]Error:[/red] Could not detect shell automatically. Specify"
          " shell as argument."
      )
      raise typer.Exit(1)

  prog_name = "ae"
  complete_var = "_AE_COMPLETE"

  try:
    script = _completion_shared.get_completion_script(
        prog_name=prog_name, complete_var=complete_var, shell=shell
    )
    print(script)
  except Exception as e:
    rich.print(f"[red]Error:[/red] Failed to generate script: {e}")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Config commands
# ---------------------------------------------------------------------------


@config_app.callback(invoke_without_command=True)
def config_default(
    ctx: typer.Context,
    name: Annotated[
        str, typer.Option("--name", help="Profile name.")
    ] = "default",
    project: Annotated[
        Optional[str],
        typer.Option("--project", help="Google Cloud project ID."),
    ] = None,
    location: Annotated[
        Optional[str],
        typer.Option(
            "--location", help="Discovery Engine location (e.g., global)."
        ),
    ] = None,
    collection: Annotated[
        Optional[str],
        typer.Option("--collection", help="Discovery Engine collection ID."),
    ] = None,
    engine: Annotated[
        Optional[str],
        typer.Option("--engine", help="Discovery Engine app/engine ID."),
    ] = None,
    session: Annotated[
        Optional[str],
        typer.Option("--session", help="Optional session ID for tracking."),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            help=(
                "[DEPRECATED: use --models] Base model enum to back the engine."
            ),
        ),
    ] = None,
    models: Annotated[
        Optional[list[str]],
        typer.Option(
            "--models",
            help=(
                "Generation model spec; repeat per model (bare name or"
                " name=...,weight=...). Replaces --model."
            ),
        ),
    ] = None,
    base_url: Annotated[
        Optional[str],
        typer.Option(
            "--base-url", help="API base URL to override the default."
        ),
    ] = None,
) -> None:
  """Set configuration values."""
  if ctx.invoked_subcommand is not None:
    return

  if model is not None:
    _warn("--model is deprecated; use --models")

  # Non-interactive: set provided values.
  updates: dict[str, Any] = {}
  for key, val in [
      ("project", project),
      ("location", location),
      ("collection", collection),
      ("engine", engine),
      ("session", session),
      ("model", model),
      ("base_url", base_url),
  ]:
    if val is not None:
      updates[key] = val
  if models is not None:
    updates["models"] = _parse_models_flag(models)

  # If no updates were provided via flags, run the interactive setup.
  if not updates:
    _config_interactive(name)
    raise typer.Exit(0)

  existing = config.load_profile(name)
  existing.update(updates)
  path = config.save_profile(name, existing)
  rich.print(f"[green]✓[/green] Updated profile [bold]{name}[/bold] → {path}")


def _config_interactive(name: str) -> None:
  """Run the interactive guided config setup."""
  rich.print(f"\n[bold]AlphaEvolve CLI Setup[/bold] (profile: {name})")
  rich.print("━" * 40)

  existing = config.load_profile(name)
  values: dict[str, Any] = {}

  # --- Project ---
  rich.print("\n[dim]Detecting available projects...[/dim]")
  current_project = config.detect_gcloud_project()
  projects = config.list_gcloud_projects()

  if projects:
    default_val = (
        existing.get("project") or current_project or projects[0]["projectId"]
    )

    rich.print(f"\nFound [bold]{len(projects)}[/bold] accessible projects.")
    if current_project:
      rich.print(
          f"Current active profile: [bold green]{current_project}[/bold green]"
      )

    show_all = typer.confirm("List all accessible projects?", default=False)

    if show_all:
      default_idx = 0
      for i, p in enumerate(projects):
        marker = (
            " [bold green](current)[/bold green]"
            if p["projectId"] == current_project
            else ""
        )
        rich.print(f"  {i + 1}. {p['projectId']} ({p['name']}){marker}")
        if p["projectId"] == current_project:
          default_idx = i
      choice = typer.prompt("Select project", default=str(default_idx + 1))
      try:
        idx = int(choice) - 1
        values["project"] = projects[idx]["projectId"]
      except (ValueError, IndexError):
        values["project"] = choice
    else:
      values["project"] = typer.prompt("GCP Project ID", default=default_val)
  else:
    default = existing.get("project") or current_project or ""
    values["project"] = typer.prompt("GCP Project ID", default=default)

  rich.print(f"[green]✓[/green] Project: {values['project']}")

  # --- Simple fields with defaults ---
  for field_name, builtin_default, label, help_text in [
      (
          "location",
          "global",
          "Location",
          "GCP region where AlphaEvolve service is running.",
      ),
      (
          "collection",
          "default_collection",
          "Collection",
          "Discovery Engine collection (usually 'default_collection').",
      ),
      (
          "engine",
          "alpha-evolve-experiment-engine",
          "Engine",
          "Experiment Engine name (usually 'alpha-evolve-experiment-engine').",
      ),
      (
          "session",
          "[create new]",
          "Session",
          (
              "User workspace session (leave as '[create new]' to"
              " auto-resolve a server ID)."
          ),
      ),
      (
          "model",
          "GEMINI_V2P5_FLASH",
          "Model",
          "Gemini model used for program generation.",
      ),
  ]:
    if field_name == "session":
      if typer.confirm("\nCreate new session?", default=False):
        rich.print("Creating new session...")
        try:
          # Instantiate a client with partial config.
          cfg = _state.resolve_config()
          cfg.project = values["project"]
          cfg.location = values.get("location", "global")
          cfg.collection = values.get("collection", "default_collection")
          cfg.engine = values["engine"]

          client = client_module.AlphaEvolveClient(cfg)
          new_id = client.create_session()
          rich.print(f"New session ID: [bold green]{new_id}[/bold green]")
          values["session"] = new_id
        except Exception as e:  # pylint: disable=broad-exception-caught
          rich.print(f"[red]Failed to create session eager: {e}[/red]")
          values["session"] = typer.prompt(
              label, default=existing.get(field_name, builtin_default)
          )
      else:
        values["session"] = typer.prompt(
            label, default=existing.get(field_name, builtin_default)
        )
    else:
      rich.print(f"\n[dim]{help_text}[/dim]")
      default = existing.get(field_name, builtin_default)
      values[field_name] = typer.prompt(label, default=default)
      rich.print(f"[green]✓[/green] {label}: {values[field_name]}")

  # --- Base URL ---
  default_url = existing.get("base_url") or client_module.build_base_url(
      values.get("location", "global")
  )
  rich.print(
      "\n[dim]The Base URL is the API endpoint for Discovery Engine. Typical"
      " URL is https://discoveryengine.googleapis.com[/dim]"
  )
  values["base_url"] = typer.prompt("Base URL", default=default_url)
  rich.print(f"[green]✓[/green] base_url: {values['base_url']}")

  path = config.save_profile(name, values)
  if name != config.get_active_profile_name():
    config.set_active_profile(name)

  rich.print(f"\n[green]✓[/green] Config saved to [bold]{path}[/bold]")
  rich.print(
      "\n[dim]Tip: Verify connectivity setup by running[/dim] [bold]ae config"
      " test[/bold]"
  )
  rich.print(
      "[dim]     Create named profiles with[/dim] [bold]ae config -i --name"
      " <name>[/bold]"
  )
  rich.print(
      "[dim]     Switch profiles with[/dim] [bold]ae config switch"
      " <name>[/bold]"
  )


@config_app.command("test")
def config_test() -> None:
  """Test API connectivity with the current configuration."""
  cfg = _state.resolve_config()

  account = "(unknown)"
  try:
    account = subprocess.check_output(
        [config.gcloud_path(), "config", "get-value", "account"],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
  except (subprocess.CalledProcessError, FileNotFoundError):
    pass

  rich.print("\n[bold]Testing AlphaEvolve Setup[/bold]")
  rich.print("━" * 40)
  rich.print(f"Account:    [magenta]{account}[/magenta]")
  rich.print(f"Project:    [magenta]{cfg.project or '(unset)'}[/magenta]")
  rich.print(f"Location:   [magenta]{cfg.location}[/magenta]")
  rich.print(
      "Session:   "
      f" [magenta]{rich.markup.escape(cfg.session or '(unset)')}[/magenta]"
  )
  rich.print(
      "Base URL:  "
      f" [magenta]{cfg.base_url or client_module.build_base_url(cfg.location)}[/magenta]\n"
  )

  if not cfg.project:
    rich.print("[red]Error:[/red] No project configured. Run `ae config -i`.")
    raise typer.Exit(1)

  rich.print("[dim]Testing API connection...[/dim]")
  try:
    client = client_module.AlphaEvolveClient(cfg, verbose=_state.verbose)
    # Lighter weight request to test auth and connectivity.
    if cfg.session and cfg.session not in ("-", "[create new]"):
      next(client.list_experiments(page_size=1), None)
    else:
      next(client.list_sessions(page_size=1), None)
    rich.print(
        "\n[green]✓ Success![/green] Connected to AlphaEvolve Cloud API."
    )
  except Exception as e:
    rich.print("\n[red]✗ Connection Failed[/red]")
    rich.print(f"[red]Error:[/red] {e}")

    if "403" in str(e) or "401" in str(e):
      if "Session is not owned" in str(e) or "Assistant not found" in str(e):
        rich.print(
            "\n[yellow]Tip:[/yellow] Resource access denied or mismatched."
        )
        rich.print(
            "  1) Verify your profile via `ae config` correctly maps Assistant"
            " vs Session."
        )
        rich.print(
            "  2) Verify your Account has correct permissions under the Engine."
        )
      else:
        rich.print("\n[yellow]Tip:[/yellow] Verify you have run:")
        rich.print("  gcloud auth application-default login")
    raise typer.Exit(1)


@config_app.command("switch")
def config_switch(
    profile: Annotated[str, typer.Argument(help="Profile name to switch to.")],
) -> None:
  """Switch the active profile."""
  if not config.profile_path(profile).exists():
    rich.print(f"[red]Error:[/red] Profile [bold]{profile}[/bold] not found.")
    rich.print(f"Available: {', '.join(config.list_profiles()) or '(none)'}")
    raise typer.Exit(1)
  config.set_active_profile(profile)
  _invalidate_cache()
  rich.print(f"[green]✓[/green] Active profile: [bold]{profile}[/bold]")


@config_app.command("show")
def config_show() -> None:
  """Show the active profile's resolved config."""
  cfg = _state.resolve_config()
  if cfg.models:
    models_summary = ", ".join(
        f"{m.get('name', '?')}" + (f"@{m['weight']}" if "weight" in m else "")
        for m in cfg.models
    )
  else:
    models_summary = "(not set)"
  data = {
      "Profile": cfg.profile_name,
      "Project": cfg.project or "(not set)",
      "Location": cfg.location,
      "Collection": cfg.collection,
      "Engine": cfg.engine,
      "Session": cfg.session,
      "Model": cfg.model,
      "Models": models_summary,
      "Base URL": cfg.base_url or client_module.build_base_url(cfg.location),
      "Output Format": cfg.output_format,
  }
  if _state.json_output:
    print(json.dumps(data, indent=2))
  else:
    rich.print("\n[bold]Active Configuration[/bold]")
    rich.print("━" * 40)
    for k, v in data.items():
      rich.print(f"  [bold]{k}:[/bold] {v}")
    rich.print()


@config_app.command("list")
def config_list() -> None:
  """List all configuration profiles."""
  profiles = config.list_profiles()
  active = config.get_active_profile_name()
  if not profiles:
    rich.print(
        "No profiles found. Run [bold]ae config -i[/bold] to create one."
    )
    return
  if _state.json_output:
    print(json.dumps([{"name": p, "active": p == active} for p in profiles]))
  else:
    for p in profiles:
      marker = " [green]← active[/green]" if p == active else ""
      rich.print(f"  {p}{marker}")


@config_app.command("discover")
def config_discover() -> None:
  """Discover ambient GCP configuration from the gcloud CLI.

  Non-interactive command that detects the current gcloud project and
  available projects without modifying any ae configuration.  Useful for
  agents that need to auto-discover GCP settings before running
  ``ae config``.
  """
  resolved = config.gcloud_path()
  gcloud_found = resolved != "gcloud"
  project = config.detect_gcloud_project() if gcloud_found else None
  projects = config.list_gcloud_projects() if gcloud_found else []
  data = {
      "gcloud_found": gcloud_found,
      "gcloud_path": resolved if gcloud_found else None,
      "project": project,
      "projects": projects,
  }
  if _state.json_output:
    print(json.dumps(data, indent=2))
  else:
    if gcloud_found:
      rich.print(f"  [bold]gcloud:[/bold] {resolved}")
      rich.print(f"  [bold]project:[/bold] {project or '(not set)'}")
      if projects:
        rich.print(f"  [bold]available projects:[/bold] {len(projects)}")
    else:
      rich.print("[yellow]gcloud not found[/yellow]")


# ---------------------------------------------------------------------------
# Experiment commands
# ---------------------------------------------------------------------------


@experiment_app.command("create")
def experiment_create(
    max_programs: Annotated[
        int, typer.Option("--max-programs", help="Max programs to generate.")
    ],
    concurrency: Annotated[
        int, typer.Option("--concurrency", help="Concurrency limit.")
    ] = 4,
    title: Annotated[
        str, typer.Option("--title", help="Experiment title.")
    ] = "",
    problem_description: Annotated[
        str, typer.Option("--problem", help="Problem description.")
    ] = "",
    problem_file: Annotated[
        str,
        typer.Option(
            "--problem-file", help="File containing the problem description."
        ),
    ] = "",
    language: Annotated[
        str, typer.Option("--language", help="Programming language.")
    ] = "python",
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help=(
                "[DEPRECATED: use --models] LLM model preset. One of:"
                " gemini_v2p5_flash, gemini_v2p5_mixture, gemini_v3p0_mixture,"
                " gemini_v3p1_mixture, gemini_v3p1_fifty_fifty_mixture,"
                " gemini_v3p1_pro."
            ),
        ),
    ] = "",
    models: Annotated[
        Optional[list[str]],
        typer.Option(
            "--models",
            help=(
                "Generation model spec; repeat per model. Each value is a bare"
                " name (gemini-3.5-flash) or name=...,weight=... . Replaces"
                " --model."
            ),
        ),
    ] = None,
) -> None:
  """Create a new experiment."""
  try:
    # Resolve the generation models from all sources by precedence:
    # --models > --model > config [[models]] > config [model] > API default.
    # Done before get_client() so bad input fails fast.
    cfg = _state.resolve_config()
    parsed = _parse_models_flag(models) if models else None
    resolved = _resolve_models(
        parsed,
        model,
        cfg_models=cfg.models,
        cfg_model=_config_model_preset(cfg),
    )

    if problem_description and problem_file:
      rich.print(
          "[red]Error:[/red] Cannot specify both --problem and --problem-file"
      )
      raise typer.Exit(1)

    if problem_file:
      p_path = pathlib.Path(problem_file)
      if not p_path.exists():
        rich.print(f"[red]Error:[/red] Problem file {problem_file} not found")
        raise typer.Exit(1)
      problem_description = p_path.read_text(encoding="utf-8")

    client = _state.get_client()

    generation_settings: dict[str, Any] = {}
    # The CLI only ever emits the structured `models` field, never the legacy
    # (mutually exclusive) `model`/`model_mixture`. An empty result (e.g.
    # gemini_v3p1_pro) leaves `models` unset so the API applies its default.
    if resolved:
      generation_settings["models"] = resolved
    exp_config: dict[str, Any] = {
        "runSettings": {
            "maxPrograms": max_programs,
            "concurrency": concurrency,
        },
        "generationSettings": generation_settings,
    }
    if title:
      exp_config["title"] = title
    if problem_description:
      exp_config["problemDescription"] = problem_description
    if language:
      exp_config["programLanguage"] = language

    body = {"config": exp_config}
    result = client.create_experiment(body)
    name = result.get("name", "")
    if name:
      nick, index = nicknames.NicknameIndex.get_nickname_synchronized(name)
    else:
      nick = ""
      index = nicknames.NicknameIndex()
    if _state.json_output:
      print(formatting.to_json(result, "nickname", index))
    else:
      rich.print(f"[green]✓[/green] Created experiment [bold]{nick}[/bold]")
      formatting.console.print(
          formatting.format_experiment_detail(result, index)
      )
  except client_module.ApiError as e:
    _handle_api_error(e)


@experiment_app.command("describe")
def experiment_describe(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name, ID, or nickname.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
) -> None:
  """Show details of an experiment."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    result = client.get_experiment(exp_name)
    index = nicknames.NicknameIndex()
    if _state.json_output:
      print(formatting.to_json(result, "nickname", index))
    else:
      formatting.console.print(
          formatting.format_experiment_detail(result, index)
      )
  except client_module.ApiError as e:
    _handle_api_error(e)


@experiment_app.command("list")
def experiment_list(
    page_size: Annotated[
        int, typer.Option("--page-size", help="Results per page.")
    ] = 100,
    cached: Annotated[
        bool,
        typer.Option("-c", "--cached", help="Use cached results if available."),
    ] = False,
) -> None:
  """List experiments."""
  try:
    if cached:
      experiments = _read_cached_experiments()
      if experiments is not None:
        pass  # use cached
      else:
        rich.print("[dim]No cache available, fetching…[/dim]")
        client = _state.get_client()
        experiments = _list_experiments_aggregated(client, page_size=page_size)
    else:
      client = _state.get_client()
      experiments = _list_experiments_aggregated(client, page_size=page_size)

    if not experiments:
      rich.print("[dim]No experiments found.[/dim]")
      return

    index = nicknames.NicknameIndex()
    index.add_many(experiments)
    if _state.json_output:
      print(formatting.to_json(experiments, "nickname", index))
    else:
      # Sort by createTime descending for better viewing
      try:
        experiments.sort(key=lambda x: x.get("createTime", ""), reverse=True)
      except (TypeError, AttributeError):
        pass
      formatting.console.print(
          formatting.format_experiment_table(experiments, index)
      )
  except client_module.ApiError as e:
    _handle_api_error(e)


@experiment_app.command("start")
def experiment_start(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    program_dir: Annotated[
        str,
        typer.Option(
            "--program-dir",
            help=(
                "Directory containing program .py files. All .py files"
                " (except evaluator.py and tests) are bundled as the"
                " initial program."
            ),
        ),
    ],
    score: Annotated[
        float,
        typer.Option("--score", help="Initial program evaluation score."),
    ],
) -> None:
  """Start an experiment (returns LRO).

  Uploads the initial program file(s) and baseline score, then activates
  the experiment on the backend.

  The --program-dir should point to the experiment directory created by the
  design skill, containing only the selected program files. All .py files
  in the directory are bundled (excluding evaluator.py and test files).

  Args:
    experiment: Experiment name or ID.
    program_dir: Directory containing program .py files.
    score: Initial program evaluation score.
  """
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)

    # Check experiment state before attempting to start.
    exp_data = client.get_experiment(exp_name)
    state = exp_data.get("state", "")
    # Strip EXPERIMENT_STATE_ prefix if present.
    state = state.removeprefix("EXPERIMENT_STATE_")
    if state not in ("CREATED", "INITIALIZED", ""):
      rich.print(
          "[red]Error:[/red] Cannot start experiment in state"
          f" [bold]{state}[/bold]. Only CREATED experiments can be"
          " started."
      )
      if state in ("ACTIVE", "RUNNING"):
        rich.print(
            "[dim]Hint: This experiment is already running. Use"
            " `ae experiment run` to start the evaluation loop.[/dim]"
        )
      raise typer.Exit(1)

    # Build program files payload from the experiment directory.
    files_payload = _prepare_program_dir_payload(program_dir)
    file_count = len(files_payload)
    if not _state.json_output:
      rich.print(
          f"[dim]Bundling {file_count} program file(s) from"
          f" {program_dir}…[/dim]"
      )

    program_body: dict[str, Any] = {
        "content": {"files": files_payload},
        "evaluation": {
            "scores": {"scores": [{"metric": "score", "score": score}]}
        },
    }

    rich.print("[dim]Creating initial program…[/dim]")
    created = _run_with_spinner(
        "Creating initial program…",
        client.create_program,
        exp_name,
        program_body,
    )
    initial_program_name = created.get("name")
    if initial_program_name and not _state.json_output:
      rich.print(
          "[green]✓[/green] Initial program created:"
          f" [bold]{initial_program_name.split('/')[-1]}[/bold]"
      )

    result = _run_with_spinner(
        "Starting experiment…",
        client.start_experiment,
        exp_name,
    )
    op_name = result.get("name", "")
    if not _state.json_output:
      rich.print(
          "[green]✓[/green] Experiment started. Operation:"
          f" [bold]{op_name}[/bold]"
      )

    if op_name:
      config.save_operation(exp_name, op_name)

    _invalidate_cache()
    _state.output(result)
  except client_module.ApiError as e:
    _handle_api_error(e)


@experiment_app.command("resume")
def experiment_resume(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
) -> None:
  """Resume a paused experiment."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    result = client.resume_experiment(exp_name)
    op_name = result.get("name", "")
    if not _state.json_output:
      rich.print(
          "[green]✓[/green] Experiment resumed. Operation:"
          f" [bold]{op_name}[/bold]"
      )
    if op_name:
      config.save_operation(exp_name, op_name)
    _invalidate_cache()
    _state.output(result)
  except client_module.ApiError as e:
    _handle_api_error(e)


@experiment_app.command("delete")
def experiment_delete(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    force: Annotated[
        bool, typer.Option("--force", help="Skip confirmation.")
    ] = False,
) -> None:
  """Delete an experiment and all its programs."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)

    if not force:
      typer.confirm(
          f"Delete experiment {experiment}? This cannot be undone.",
          abort=True,
      )

    client.delete_experiment(exp_name)
    _invalidate_cache()
    if not _state.json_output:
      rich.print(f"[green]✓[/green] Deleted: [bold]{experiment}[/bold]")
  except client_module.ApiError as e:
    _handle_api_error(e)


@experiment_app.command("run")
def experiment_run(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    evaluator: Annotated[
        str,
        typer.Option("--evaluator", help="Path to the evaluator script."),
    ],
    max_iterations: Annotated[
        int,
        typer.Option(
            "--max-iterations",
            help="Max evaluation iterations (0 = unlimited).",
        ),
    ] = 0,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Evaluation timeout in seconds."),
    ] = evaluator_module.DEFAULT_TIMEOUT_SECONDS,
    backend: Annotated[
        str,
        typer.Option("--backend", help="Evaluation backend: local or podman."),
    ] = "local",
    dashboard_path: Annotated[
        Optional[str],
        typer.Option(
            "--dashboard",
            help=(
                "Path to a markdown dashboard file. Updated after each"
                " evaluation with a score chart and leaderboard."
            ),
        ),
    ] = None,
    extra_evaluator_args: Annotated[
        Optional[str],
        typer.Option(
            "--extra-evaluator-args",
            help=(
                "Extra arguments to pass to the evaluator script as a single"
                " string (e.g., --extra-evaluator-args='--arg1 val1 --arg2')."
            ),
        ),
    ] = None,
) -> None:
  """Run the acquire + evaluate + submit controller loop."""
  evaluator_path = pathlib.Path(evaluator)
  if not evaluator_path.exists():
    rich.print(f"[red]Error:[/red] Evaluator not found: {evaluator}")
    raise typer.Exit(1)
  if extra_evaluator_args:
    try:
      shlex.split(extra_evaluator_args, posix=(os.name != "nt"))
    except ValueError as e:
      rich.print(f"[red]Error:[/red] Invalid extra-evaluator-args: {e}")
      raise typer.Exit(1)

  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    dash_path = pathlib.Path(dashboard_path) if dashboard_path else None
    index = nicknames.NicknameIndex.load()
    exp_nick = index.get_nickname(exp_name) or experiment

    class _CliCallbacks(controller_module.ControllerCallbacks):
      """Rich console callbacks for the controller loop."""

      def __init__(self) -> None:
        self.score_history: list[tuple[int, float]] = []
        self.leaderboard: list[dict[str, Any]] = []
        self._last_eval_count: int = 0
        self._nick_scores: list[tuple[str, float]] = []

      def on_acquire(self, program_name: str, nickname: str) -> None:
        rich.print(f"  [dim]Acquired:[/dim] {nickname}")

      def on_evaluate(
          self,
          program_name: str,
          nickname: str,
          result: evaluator_module.EvaluationResult,
      ) -> None:
        if result.success:
          rich.print(
              f"  [green]\u2713[/green] {nickname} score={result.score:.6f}"
          )
          self._nick_scores.append((nickname, result.score))
        else:
          rich.print(f"  [red]\u2717[/red] {nickname} failed: {result.error}")

      def on_submit(
          self, program_name: str, nickname: str, score: float
      ) -> None:
        rich.print(f"  [dim]Submitted:[/dim] {nickname}")

      def on_new_best(
          self, program_name: str, nickname: str, score: float
      ) -> None:
        rich.print(
            f"  [bold green]\u2605 New best:[/bold green] {nickname}"
            f" score={score:.6f}"
        )

      def on_no_programs(self) -> None:
        rich.print("  [dim]No programs available, waiting\u2026[/dim]")

      def on_experiment_terminal(self, state: str) -> None:
        rich.print(f"  [bold]Experiment reached terminal state: {state}[/bold]")
        rich.print(f"  [bold]Experiment reached terminal state: {state}[/bold]")

      def on_error(self, stage: str, error: Exception) -> None:
        rich.print(f"  [red]Error ({stage}):[/red] {error}")

      def on_progress(
          self,
          stats: controller_module.ControllerStats,
          iteration: int,
          max_iterations: int,
      ) -> None:
        progress = (
            f"{iteration}/{max_iterations}"
            if max_iterations
            else str(iteration)
        )
        rich.print(
            f"  [dim]Progress: {progress} |"
            f" succeeded={stats.total_succeeded}"
            f" failed={stats.total_failed}[/dim]"
        )

        # Track score history (deduplicate: only append on new evals).
        if stats.scores and stats.total_evaluated > self._last_eval_count:
          self.score_history.append((stats.total_evaluated, stats.scores[-1]))
          self._last_eval_count = stats.total_evaluated

        # Update leaderboard with real program nicknames.
        top = sorted(self._nick_scores, key=lambda x: x[1], reverse=True)
        self.leaderboard = [{"nickname": n, "score": s} for n, s in top[:10]]

        # Write dashboard if requested.
        if dash_path is not None:
          self.write_dashboard(stats, "RUNNING")

      def write_dashboard(
          self, stats: controller_module.ControllerStats, state: str
      ) -> None:
        """Writes the dashboard, catching I/O errors."""
        if dash_path is None:
          return
        try:
          # Fetch all programs from backend to make it global
          all_progs = list(client.list_programs(exp_name))

          # Recompute stats and leaderboard from all programs
          total_evaluated = len(all_progs)
          succeeded = []
          failed = []
          scored_progs = []

          for p in all_progs:
            eval_data = p.get("evaluation", {})
            scores = eval_data.get("scores", {}).get("scores", [])
            if scores:
              try:
                score_val = float(scores[0].get("score", 0.0))
                if score_val != evaluator_module.FAILURE_SCORE:
                  succeeded.append(p)
                  nick = index.get_nickname(p.get("name")) or p.get(  # pyrefly: ignore[bad-argument-type]
                      "nickname", ""
                  )
                  scored_progs.append((nick, score_val))
                else:
                  failed.append(p)
              except (ValueError, TypeError):
                pass

          total_succeeded = len(succeeded)
          total_failed = len(failed)

          scored_progs.sort(key=lambda x: x[1], reverse=True)
          global_leaderboard = [
              {"nickname": n, "score": s} for n, s in scored_progs[:10]
          ]

          best_score = scored_progs[0][1] if scored_progs else None
          best_nick = scored_progs[0][0] if scored_progs else None

          # Reconstruct history by creation time
          succeeded.sort(key=lambda p: p.get("createTime", ""))
          global_history = []
          for i, p in enumerate(succeeded, 1):
            eval_data = p.get("evaluation", {})
            scores = eval_data.get("scores", {}).get("scores", [])
            if scores:
              try:
                global_history.append((i, float(scores[0].get("score", 0.0))))
              except (ValueError, TypeError):
                pass

          dashboard.write_dashboard(
              path=dash_path,
              nickname=exp_nick,
              state=state,
              total_evaluated=total_evaluated,
              total_succeeded=total_succeeded,
              total_failed=total_failed,
              best_score=best_score,
              best_nickname=best_nick,
              score_history=global_history,
              leaderboard=global_leaderboard,
          )
        except OSError as e:
          rich.print(f"  [yellow]Dashboard write failed: {e!r}[/yellow]")
        # Catch all exceptions to prevent crashing the long-running experiment.
        except Exception as e:  # pylint: disable=broad-exception-caught
          rich.print(
              f"  [yellow]Failed to update global dashboard: {e!r}[/yellow]"
          )

    rich.print(f"[bold]Running controller loop for {experiment}[/bold]")
    cb = _CliCallbacks()
    stats = controller_module.run_controller_loop(
        client=client,
        experiment_name=exp_name,
        evaluator_path=evaluator_path,
        max_iterations=max_iterations,
        timeout=timeout,
        backend=backend,
        callbacks=cb,
        extra_evaluator_args=extra_evaluator_args,
    )

    # Write final dashboard snapshot.
    if dash_path is not None:
      try:
        exp_data = client.get_experiment(exp_name)
        final_state = exp_data.get("state", "UNKNOWN")
      except client_module.ApiError:
        final_state = "UNKNOWN"
      cb.write_dashboard(stats, final_state)
      rich.print(f"  [dim]Dashboard written to {dash_path}[/dim]")

    rich.print("\n[bold]Controller finished.[/bold]")
    if _state.json_output:
      print(json.dumps(stats.to_dict(), indent=2))
    else:
      rich.print(f"  Total evaluated: {stats.total_evaluated}")
      rich.print(f"  Succeeded: {stats.total_succeeded}")
      rich.print(f"  Failed: {stats.total_failed}")
      if stats.best_score is not None:
        rich.print(f"  Best score: {stats.best_score:.6f}")
  except client_module.ApiError as e:
    _handle_api_error(e)


# ---------------------------------------------------------------------------
# Program commands
# Maximum characters to display for a single insight text.
_MAX_INSIGHT_CHARS = 2000
# Maximum lines of evolved code to display inline.
_MAX_EVOLVE_BLOCK_LINES = 20


def _get_eval_insights(
    prog_data: dict[str, Any],
) -> list[dict[str, str]]:
  """Extracts evaluation insights from a program's data dict."""
  return prog_data.get("evaluation", {}).get("insights", {}).get("insights", [])


# ---------------------------------------------------------------------------


@program_app.command("show")
def program_show(
    program: Annotated[str, typer.Argument(help="Program name or ID.")],
    experiment: Annotated[
        Optional[str], typer.Option("--experiment", help="Parent experiment.")
    ] = None,
    code: Annotated[
        bool, typer.Option("--code", help="Show program source code.")
    ] = False,
    insights: Annotated[
        bool,
        typer.Option(
            "--insights",
            help="Show evaluation insights (errors, tracebacks, stdout).",
        ),
    ] = False,
    output_file: Annotated[
        str | None,
        typer.Option("--output-file", help="Save program code to file."),
    ] = None,
) -> None:
  """Show details of a program."""
  try:
    client = _state.get_client()
    prog_name = _resolve_program(program, experiment)
    prog_data = _get_program(client, prog_name)
    content = prog_data.get("content")
    if isinstance(content, str):
      try:
        prog_data["content"] = ast.literal_eval(content)
      except (ValueError, SyntaxError):
        try:
          prog_data["content"] = json.loads(content)
        except json.JSONDecodeError:
          pass
    index = nicknames.NicknameIndex()

    if output_file:
      files = prog_data.get("content", {}).get("files", [])
      if files:
        if len(files) == 1:
          content = files[0].get("content", "")
          with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
          rich.print(f"[green]Saved program code to {output_file}[/green]")
        else:
          rich.print(
              "[yellow]Warning: Program has multiple files. Saving the first"
              " one.[/yellow]"
          )
          content = files[0].get("content", "")
          with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
          rich.print(f"[green]Saved first file code to {output_file}[/green]")
      else:
        rich.print("[red]Error: No file content found in program.[/red]")

    if _state.json_output:
      print(formatting.to_json(prog_data, "nickname", index))
    else:
      if code:
        files = prog_data.get("content", {}).get("files", [])
        for f in files:
          path = f.get("path", "unknown")
          content = f.get("content", "")
          rich.print(f"\n[bold]── {path} ──[/bold]")
          formatting.console.print(
              formatting.syntax.Syntax(content, "python", theme="monokai")
          )
      if insights:
        eval_insights = _get_eval_insights(prog_data)
        if eval_insights:
          rich.print("\n[bold]── Evaluation Insights ──[/bold]")
          for insight in eval_insights:
            label = insight.get("label", "info")
            text = insight.get("text", "")
            if text:
              rich.print(f"  [bold]{label}:[/bold] {text[:_MAX_INSIGHT_CHARS]}")
        else:
          rich.print("\n[dim]No evaluation insights available.[/dim]")
      formatting.console.print(
          formatting.format_program_detail(prog_data, index)
      )
  except client_module.ApiError as e:
    _handle_api_error(e)


@program_app.command("list")
def program_list(
    experiment: Annotated[
        Optional[str],
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ] = None,
    order_by: Annotated[
        Optional[str], typer.Option("--order-by", help="Sort field.")
    ] = None,
    state: Annotated[
        Optional[str], typer.Option("--state", help="Filter by state.")
    ] = None,
    page_size: Annotated[
        int, typer.Option("--page-size", help="Results per page.")
    ] = 100,
    cached: Annotated[
        bool,
        typer.Option("-c", "--cached", help="Use cached results if available."),
    ] = False,
) -> None:
  """List programs in an experiment."""
  try:
    client = _state.get_client()

    if experiment is None:
      raise typer.BadParameter("Missing required argument: EXPERIMENT.")

    exp_name = _resolve_experiment(experiment)
    exp_id = exp_name.split("/")[-1]
    cfg = _state.resolve_config()

    programs = None
    if cached:
      programs = _read_cached_programs(exp_id)
      if programs is not None:
        pass  # use cached
      else:
        rich.print("[dim]No cache available, fetching…[/dim]")

    if programs is None:
      programs = list(
          client.list_programs(
              exp_name,
              page_size=page_size,
              order_by=order_by,
              state_filter=state,
          )
      )
      config.save_cache(f"programs_list_{cfg.profile_name}_{exp_id}", programs)

    if not programs:
      rich.print("[dim]No programs found.[/dim]")
      return
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    index.save()
    if _state.json_output:
      print(formatting.to_json(programs, "nickname", index))
    else:
      formatting.console.print(formatting.format_program_table(programs, index))
  except client_module.ApiError as e:
    _handle_api_error(e)


@program_app.command("acquire")
def program_acquire(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    count: Annotated[
        int, typer.Option("--count", help="Number of programs to acquire.")
    ] = 1,
    program_dir: Annotated[
        Optional[str],
        typer.Option(
            "--program-dir",
            help="Directory to save acquired programs and lock files.",
        ),
    ] = None,
) -> None:
  """Acquire programs for evaluation (locks them)."""
  if _state.json_output and program_dir:
    rich.print("[red]Error:[/red] Cannot specify both --json and --program-dir")
    raise typer.Exit(1)

  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    result = client.acquire_programs(exp_name, desired_count=count)

    cfg = _state.resolve_config()
    lock_cache = locks.LockCache(cfg.profile_name)

    programs = result.get("programs") or result.get("alphaEvolvePrograms", [])
    lock_token = result.get("lockToken") or ""

    for p in programs:
      p_name = p.get("name", "")
      p_lock_token = p.get("lockToken") or p.get("lock_token") or lock_token
      if p_name and p_lock_token:
        lock_cache.add(p_name, p_lock_token)

    if program_dir:
      p_path = pathlib.Path(program_dir)
      p_path.mkdir(parents=True, exist_ok=True)

      index = nicknames.NicknameIndex()
      for p in programs:
        name = p.get("name", "")
        if name:
          nick = index.get_nickname(name)
          files = p.get("content", {}).get("files", [])
          code = (
              "\n\n".join(f.get("content", "") for f in files) if files else ""
          )

          p_lock_token = (
              p.get("lockToken") or p.get("lock_token") or lock_token or ""
          )

          code_file = p_path / f"{nick}.py"
          lock_file = p_path / f"{nick}.lock"

          code_file.write_text(code, encoding="utf-8")
          lock_file.write_text(p_lock_token, encoding="utf-8")
          rich.print(f"  [green]✓[/green] Saved {nick}.py and {nick}.lock")

      index.save()
    else:
      _state.output(result, index=nicknames.NicknameIndex())
  except client_module.ApiError as e:
    _handle_api_error(e)


@program_app.command("submit")
def program_submit(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    score: Annotated[
        float,
        typer.Option("--score", help="Evaluation score."),
    ],
    program_dir: Annotated[
        Optional[str],
        typer.Option(
            "--program-dir",
            help=(
                "Directory containing program .py files to submit."
                " Bundles all .py files (excluding evaluator.py and tests)."
                " Required when creating a new program (without --program)."
            ),
        ),
    ] = None,
    program: Annotated[
        Optional[str],
        typer.Option(
            "--program", help="Resource name of the program (if acquired)."
        ),
    ] = None,
    lock_token: Annotated[
        Optional[str],
        typer.Option("--lock-token", help="Lock token (if acquired)."),
    ] = None,
) -> None:
  """Submit a program (creates new or evaluates acquired ones).

  Args:
    experiment: Experiment name or ID.
    score: Evaluation score.
    program_dir: Directory containing program .py files.
    program: Resource name of the program (if acquired).
    lock_token: Lock token (if acquired).
  """
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)

    cfg = _state.resolve_config()
    lock_cache = locks.LockCache(cfg.profile_name)

    resolved_program = program
    if program:
      resolved_program = _resolve_program(program, experiment)

    if resolved_program and not lock_token:
      lock_token = lock_cache.get(resolved_program)

    if bool(resolved_program) != bool(lock_token):
      rich.print(
          "[red]Error:[/red] Both --program and --lock-token must be"
          " provided together (for acquired programs), or neither (for new"
          " programs)."
      )
      raise typer.Exit(1)

    if resolved_program:
      eval_scores = [{"metric": "score", "score": score}]
      submission = {
          "program": resolved_program,
          "lockToken": lock_token,
          "evaluation": {"scores": {"scores": eval_scores}},
      }
      result = client.submit_evaluations(exp_name, [submission])
      _state.output(result, index=nicknames.NicknameIndex())
    else:
      if not program_dir:
        rich.print(
            "[red]Error:[/red] --program-dir is required when creating a"
            " new program (without --program/--lock-token)."
        )
        raise typer.Exit(1)
      files_payload = _prepare_program_dir_payload(program_dir)
      program_body = {
          "content": {"files": files_payload},
          "evaluation": {
              "scores": {"scores": [{"metric": "score", "score": score}]}
          },
      }
      result = client.create_program(exp_name, program_body)
      _state.output(result, index=nicknames.NicknameIndex())
  except client_module.ApiError as e:
    _handle_api_error(e)


@program_app.command("evaluate")
def program_evaluate(
    evaluator: Annotated[
        str,
        typer.Option(
            "--evaluator",
            help="Path to the evaluator script.",
        ),
    ],
    program_file: Annotated[
        Optional[str],
        typer.Option(
            "--program-file",
            help="Path to a local program .py file to evaluate.",
        ),
    ] = None,
    program_name: Annotated[
        Optional[str],
        typer.Option(
            "--program-name",
            help=(
                "Resource name or nickname of a program to fetch from the API."
            ),
        ),
    ] = None,
    program_dir: Annotated[
        Optional[str],
        typer.Option(
            "--program-dir",
            help="Directory containing program files to evaluate.",
        ),
    ] = None,
    experiment: Annotated[
        Optional[str],
        typer.Option(
            "--experiment",
            help="Parent experiment (required when --program-name is used).",
            autocompletion=_autocomplete_experiment,
        ),
    ] = None,
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            help="Evaluation backend: local or podman.",
        ),
    ] = "local",
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            help="Maximum evaluation time in seconds.",
        ),
    ] = evaluator_module.DEFAULT_TIMEOUT_SECONDS,
    work_dir: Annotated[
        Optional[str],
        typer.Option(
            "--work-dir",
            help="Directory for evaluation workspace (temp dir if omitted).",
        ),
    ] = None,
) -> None:
  """Evaluate a program using a local evaluator script.

  The evaluator script runs the evolved program code and produces a numeric
  score.  It must accept --output-file and write JSON with a "score" key.

  Programs can be specified in three ways:

    1. --program-name <nickname-or-name> --experiment <exp>  (fetches from API)

    2. --program-file <path/to/file.py>  (reads a local file)

    3. --program-dir <directory>  (reads all .py files from a directory)

  Args:
    evaluator: Path to the evaluator script.
    program_file: Path to a local program .py file.
    program_name: Resource name or nickname of a program (fetched from API).
    program_dir: Directory containing program files to evaluate.
    experiment: Parent experiment (required when program_name is used).
    backend: Evaluation backend (local or podman).
    timeout: Maximum evaluation time in seconds.
    work_dir: Directory for evaluation workspace.
  """
  evaluator_path = pathlib.Path(evaluator)
  if not evaluator_path.exists():
    rich.print(f"[red]Error:[/red] Evaluator not found: {evaluator}")
    raise typer.Exit(1)

  # Resolve program files from the three possible sources.
  program_files: list[dict[str, str]] = []

  specified = sum(1 for x in (program_file, program_name, program_dir) if x)
  if specified > 1:
    rich.print(
        "[red]Error:[/red] Specify exactly one of --program-file,"
        " --program-name, or --program-dir."
    )
    raise typer.Exit(1)

  if specified == 0:
    rich.print(
        "[red]Error:[/red] Specify one of --program-file, --program-name,"
        " or --program-dir."
    )
    raise typer.Exit(1)

  if program_dir:
    # Read all .py files from the directory.
    p_dir = pathlib.Path(program_dir)
    if not p_dir.is_dir():
      rich.print(f"[red]Error:[/red] Not a directory: {program_dir}")
      raise typer.Exit(1)

    py_files = sorted(p_dir.glob("*.py"))
    if not py_files:
      rich.print(f"[red]Error:[/red] No .py files found in {program_dir}")
      raise typer.Exit(1)

    for fp in py_files:
      program_files.append({
          "path": fp.name,
          "content": fp.read_text(encoding="utf-8"),
      })

  elif program_file:
    local_path = pathlib.Path(program_file)
    if not local_path.exists() or not local_path.is_file():
      rich.print(f"[red]Error:[/red] Program file not found: {program_file}")
      raise typer.Exit(1)
    program_files.append({
        "path": local_path.name,
        "content": local_path.read_text(encoding="utf-8"),
    })

  elif program_name:
    # Fetch from API using resource name or nickname.
    if not experiment:
      rich.print(
          "[red]Error:[/red] --experiment is required when"
          " --program-name is used."
      )
      raise typer.Exit(1)

    try:
      client = _state.get_client()
      prog_name = _resolve_program(program_name, experiment)
      prog_data = _get_program(client, prog_name)
      files = prog_data.get("content", {}).get("files", [])
      if not files:
        rich.print("[red]Error:[/red] Program has no files.")
        raise typer.Exit(1)
      for f in files:
        program_files.append({
            "path": f.get("path", "program.py"),
            "content": f.get("content", ""),
        })
    except client_module.ApiError as e:
      _handle_api_error(e)

  # Run evaluation.
  eval_work_dir = pathlib.Path(work_dir) if work_dir else None

  try:
    eval_result = evaluator_module.evaluate_program(
        program_files=program_files,
        evaluator_path=evaluator_path,
        backend=backend,
        timeout=timeout,
        work_dir=eval_work_dir,
    )
  except ValueError as e:
    rich.print(f"[red]Error:[/red] {e!r}")
    raise typer.Exit(1)

  # Output results.
  if _state.json_output:
    print(json.dumps(eval_result.to_dict(), indent=2))
  else:
    if eval_result.success:
      rich.print(
          "[green]✓[/green] Evaluation succeeded. Score:"
          f" [bold]{eval_result.score:.6f}[/bold]"
      )
      if len(eval_result.scores) > 1:
        for s in eval_result.scores:
          rich.print(f"  {s.get('metric', '?')}: {s.get('score', '?')}")
    else:
      rich.print(f"[red]✗[/red] Evaluation failed: {eval_result.error}")
      if eval_result.stderr:
        for line in eval_result.stderr.strip().splitlines()[:20]:
          rich.print(f"  [dim red]{line}[/dim red]")

    if eval_result.stdout:
      for line in eval_result.stdout.strip().splitlines()[:10]:
        rich.print(f"  [dim]{line}[/dim]")

  if not eval_result.success:
    raise typer.Exit(1)


@program_app.command("diff")
def program_diff(
    program: Annotated[str, typer.Argument(help="Program name or ID.")],
    experiment: Annotated[
        Optional[str], typer.Option("--experiment", help="Parent experiment.")
    ] = None,
) -> None:
  """Show diff between a program and its parent."""
  try:
    client = _state.get_client()
    prog_name = _resolve_program(program, experiment)
    prog_data = _get_program(client, prog_name)
    parent_names = prog_data.get("parentPrograms", [])

    if not parent_names:
      rich.print(
          "[dim]This program has no parent (it's an initial program).[/dim]"
      )
      index = nicknames.NicknameIndex()
      if _state.json_output:
        print(formatting.to_json(prog_data, "nickname", index))
      else:
        formatting.console.print(
            formatting.format_program_detail(prog_data, index)
        )
      return

    parent_data = _get_program(client, parent_names[0])
    prog_files = prog_data.get("content", {}).get("files", [])
    parent_files = parent_data.get("content", {}).get("files", [])

    for pf, cf in zip(parent_files, prog_files):
      old_content = pf.get("content", "")
      new_content = cf.get("content", "")
      diff_syntax = formatting.format_diff(
          old_content,
          new_content,
          from_file=f"parent/{pf.get('path', '?')}",
          to_file=f"current/{cf.get('path', '?')}",
      )
      formatting.console.print(diff_syntax)

  except client_module.ApiError as e:
    _handle_api_error(e)


# ---------------------------------------------------------------------------
# Results commands
# ---------------------------------------------------------------------------


@results_app.command("failed")
def results_failed(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
) -> None:
  """Show failed programs with their error insights."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    all_programs = list(client.list_programs(exp_name))

    failed = []
    for p in all_programs:
      if not isinstance(p, dict):
        continue
      eval_data = p.get("evaluation", {})
      if not isinstance(eval_data, dict):
        continue
      scores_dict = eval_data.get("scores")
      if not isinstance(scores_dict, dict):
        failed.append(p)
        continue
      scores = scores_dict.get("scores", [])
      if not isinstance(scores, list) or not scores:
        failed.append(p)
        continue
      score = scores[0].get("score")
      # The controller submits failed evaluations with a sentinel
      # score of FAILURE_SCORE (-(10**12)), not null.
      if score is None or score <= evaluator_module.FAILURE_SCORE:
        failed.append(p)

    if not failed:
      rich.print("[dim]No failed programs found.[/dim]")
      return

    index = nicknames.NicknameIndex()
    index.add_many(all_programs)
    index.save()

    if _state.json_output:
      print(formatting.to_json(failed, "nickname", index))
    else:
      for prog in failed:
        nick = index.get_nickname(prog.get("name", ""))
        rich.print(f"\n[bold red]FAILED:[/bold red] [bold]{nick}[/bold]")
        # Show insights (error messages, tracebacks).
        eval_insights = _get_eval_insights(prog)
        if eval_insights:
          for insight in eval_insights:
            label = insight.get("label", "info")
            text = insight.get("text", "")
            if text:
              truncated = text[:_MAX_INSIGHT_CHARS]
              # Escape brackets to prevent Rich markup interpretation.
              rich.print(f"  \\[{label}] {truncated}")
        else:
          rich.print("  [dim]No insights available.[/dim]")
        # Show the evolved code block if present.
        files = prog.get("content", {}).get("files", [])
        for f in files:
          content = f.get("content", "")
          # Extract just the EVOLVE-BLOCK.
          if "EVOLVE-BLOCK-START" in content:
            all_lines = content.split("\n")
            in_block = False
            block_lines = []
            for line in all_lines:
              if "EVOLVE-BLOCK-START" in line:
                in_block = True
                continue
              if "EVOLVE-BLOCK-END" in line:
                in_block = False
                continue
              if in_block:
                block_lines.append(line)
            if block_lines:
              rich.print("  [dim]Evolved code:[/dim]")
              for bl in block_lines[:_MAX_EVOLVE_BLOCK_LINES]:
                rich.print(f"    {bl}")
              if len(block_lines) > _MAX_EVOLVE_BLOCK_LINES:
                remaining = len(block_lines) - _MAX_EVOLVE_BLOCK_LINES
                rich.print(f"    [dim]... ({remaining} more lines)[/dim]")

  except client_module.ApiError as e:
    _handle_api_error(e)


@results_app.command("best")
def results_best(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    top: Annotated[
        int, typer.Option("--top", help="Number of top programs.")
    ] = 5,
) -> None:
  """Show the best-scoring programs."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    # Fetch all programs and sort locally by score descending
    all_programs = list(client.list_programs(exp_name))

    def _get_score(p: dict[str, Any]) -> float:
      if not isinstance(p, dict):
        return -float("inf")
      eval_data = p.get("evaluation", {})
      if not isinstance(eval_data, dict):
        return -float("inf")
      scores_dict = eval_data.get("scores")
      if not isinstance(scores_dict, dict):
        return -float("inf")
      scores = scores_dict.get("scores", [])
      if not isinstance(scores, list) or not scores:
        return -float("inf")
      return scores[0].get("score", -float("inf"))

    # Sort by score descending; un-scored programs fall to the bottom.
    all_programs.sort(key=_get_score, reverse=True)
    programs = all_programs[:top]
    if not programs:
      rich.print("[dim]No scored programs found.[/dim]")
      return
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    index.save()
    if _state.json_output:
      print(formatting.to_json(programs, "nickname", index))
    else:
      formatting.console.print(formatting.format_program_table(programs, index))
  except client_module.ApiError as e:
    _handle_api_error(e)


@results_app.command("history")
def results_history(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
) -> None:
  """Show evaluation history for an experiment."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)
    # Fetch all programs and sort locally by creation time
    programs = list(client.list_programs(exp_name))
    programs.sort(key=lambda p: p.get("createTime", ""))
    if not programs:
      rich.print("[dim]No programs found.[/dim]")
      return
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    index.save()
    if _state.json_output:
      print(formatting.to_json(programs, "nickname", index))
    else:
      formatting.console.print(formatting.format_program_table(programs, index))
  except client_module.ApiError as e:
    _handle_api_error(e)


# ---------------------------------------------------------------------------
# Visualization commands
# ---------------------------------------------------------------------------


@results_app.command("plot")
def results_plot(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    output: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Output PNG file path.",
        ),
    ] = "score_progression.png",
    title: Annotated[
        str | None,
        typer.Option("--title", help="Chart title."),
    ] = None,
) -> None:
  """Generate a score progression chart (PNG) for an experiment."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)

    if not _state.json_output:
      rich.print("[dim]Fetching experiment data...[/dim]")

    programs = list(client.list_programs(exp_name))
    programs.sort(key=lambda p: p.get("createTime", ""))

    if not programs:
      rich.print("[dim]No programs found.[/dim]")
      raise typer.Exit(1)

    index = nicknames.NicknameIndex.load()
    index.add_many(programs)
    index.save()

    exp_nick = index.get_nickname(exp_name) or experiment
    chart_title = title or f"Experiment: {exp_nick}"

    output_path = pathlib.Path(output)
    visualization.generate_plot(
        programs=programs,
        output_path=output_path,
        title=chart_title,
        nickname_fn=index.get_nickname,
    )

    if _state.json_output:
      print(json.dumps({"output": str(output_path.resolve())}))
    else:
      rich.print(
          "[green]\u2713[/green] Chart saved to"
          f" [bold]{output_path.resolve()}[/bold]"
      )
  except client_module.ApiError as e:
    _handle_api_error(e)


@results_app.command("report")
def results_report(
    experiment: Annotated[
        str,
        typer.Argument(
            help="Experiment name or ID.",
            autocompletion=_autocomplete_experiment,
        ),
    ],
    output: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Output HTML file path.",
        ),
    ] = "experiment_report.html",
    markdown: Annotated[
        str | None,
        typer.Option(
            "--markdown",
            help="Path to a markdown report to embed below the chart.",
        ),
    ] = None,
) -> None:
  """Generate an interactive HTML report for an experiment."""
  try:
    client = _state.get_client()
    exp_name = _resolve_experiment(experiment)

    if not _state.json_output:
      rich.print("[dim]Fetching experiment data...[/dim]")

    programs = list(client.list_programs(exp_name))
    programs.sort(key=lambda p: p.get("createTime", ""))

    if not programs:
      rich.print("[dim]No programs found.[/dim]")
      raise typer.Exit(1)

    index = nicknames.NicknameIndex.load()
    index.add_many(programs)
    index.save()

    exp_data = client.get_experiment(exp_name)
    exp_nick = index.get_nickname(exp_name) or experiment

    # Extract model and duration from experiment metadata.
    exp_config = exp_data.get("config", {})
    model = formatting.format_model(exp_config.get("generationSettings", {}))
    create_time = exp_data.get("createTime", "")
    end_time = exp_data.get("endTime", "")
    duration = ""
    if create_time and end_time:
      try:
        start = datetime.datetime.fromisoformat(
            create_time.replace("Z", "+00:00")
        )
        end = datetime.datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        delta = end - start
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        duration = f"{hours}h {minutes}m" if hours else f"{minutes}m"
      except (ValueError, TypeError):
        pass

    md_path = pathlib.Path(markdown) if markdown else None
    output_path = pathlib.Path(output)

    visualization.generate_html_report(
        programs=programs,
        output_path=output_path,
        nickname=exp_nick,
        model=model,
        duration=duration,
        markdown_path=md_path,
        nickname_fn=index.get_nickname,
    )

    if _state.json_output:
      print(json.dumps({"output": str(output_path.resolve())}))
    else:
      rich.print(
          "[green]\u2713[/green] Interactive report saved to"
          f" [bold]{output_path.resolve()}[/bold]"
      )
      rich.print(
          "[dim]Open in a browser to explore the interactive chart.[/dim]"
      )
  except client_module.ApiError as e:
    _handle_api_error(e)
