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

"""Stdlib argparse CLI entry point for AlphaEvolve.

Provides the full `ae` command surface without requiring `typer`, `click`,
`google-auth`, `filelock`, `coolname`, or `Markdown`. Designed for sandboxed
and minimal Python environments, including callers that inject an MCP tool
caller (`mcp_caller`) into `AlphaEvolveClient`.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import pathlib
import shlex
import subprocess
import sys
from typing import Any, NoReturn

import rich
from rich import markup as rich_markup

from . import client as client_module
from . import config
from . import controller as controller_module
from . import dashboard
from . import evaluator as evaluator_module
from . import formatting
from . import locks
from . import nicknames
from . import resolution
from . import version as ae_version

# Maximum characters to display for a single insight text.
_MAX_INSIGHT_CHARS = 2000
# Maximum lines of evolved code to display inline.
_MAX_EVOLVE_BLOCK_LINES = 20
# States treated as already running by `experiment resume`.
_RUNNING_STATES = ("RUNNING", "STARTED", "ACTIVE")

# First-party modules required by this stdlib CLI entry point (no typer/click).
SANDBOX_CLI_MODULES: tuple[str, ...] = (
    "__init__.py",
    "version.py",
    "config.py",
    "locks.py",
    "nicknames.py",
    "formatting.py",
    "client.py",
    "resolution.py",
    "evaluator.py",
    "controller.py",
    "dashboard.py",
    "visualization.py",
    "sandbox_cli.py",
)


class _CliExitError(Exception):
  """Internal control-flow exception carrying a process exit code."""

  def __init__(self, code: int) -> None:
    super().__init__(f"exit {code}")
    self.code = code


class _SandboxState:
  """Per-invocation CLI state and client/config helpers."""

  def __init__(
      self,
      *,
      project: str | None = None,
      location: str | None = None,
      json_output: bool = False,
      compact: bool = False,
      verbose: bool = False,
      mcp_caller: client_module.McpCaller | None = None,
      config_defaults: dict[str, Any] | None = None,
      config_overrides: dict[str, Any] | None = None,
      allow_gcloud: bool = True,
  ) -> None:
    self.project = project
    self.location = location
    self.json_output = json_output
    self.compact = compact
    self.verbose = verbose
    self.mcp_caller = mcp_caller
    self.config_defaults = dict(config_defaults) if config_defaults else {}
    self.config_overrides = dict(config_overrides) if config_overrides else {}
    self.allow_gcloud = allow_gcloud

  def warn(self, message: str) -> None:
    print(message, file=sys.stderr)

  def err(self, message: str) -> NoReturn:
    if self.json_output:
      print(json.dumps({"error": {"status": 1, "message": message}}))
    else:
      print(f"Error: {message}", file=sys.stderr)
    raise _CliExitError(1)

  def handle_api_error(self, e: client_module.ApiError) -> NoReturn:
    if self.json_output:
      print(
          json.dumps({"error": {"status": e.status_code, "message": e.message}})
      )
    else:
      formatting.console.print(
          formatting.format_error(e.status_code, e.message, e.details)
      )
    raise _CliExitError(1)

  def resolve_config(self) -> config.Config:
    overrides: dict[str, Any] = dict(self.config_overrides)
    if self.project:
      overrides["project"] = self.project
    if self.location:
      overrides["location"] = self.location
    return config.load_config(
        cli_overrides=overrides or None,
        defaults_override=self.config_defaults or None,
        allow_gcloud=self.allow_gcloud,
    )

  def get_client(self) -> client_module.AlphaEvolveClient:
    """Creates an API client from resolved configuration."""
    cfg = self.resolve_config()
    if not cfg.project:
      self.err(
          "No project configured. Run `ae config --project=<id>` or pass"
          " --project=<id>."
      )

    if self.mcp_caller is not None:
      if not cfg.has_valid_session():
        cfg.session = "-"
      try:
        return client_module.AlphaEvolveClient(
            cfg, verbose=self.verbose, mcp_caller=self.mcp_caller
        )
      except ValueError as e:
        self.err(str(e))

    if not cfg.has_valid_session():
      self.warn("Session not configured. Creating a new session...")
      try:
        tmp_client = client_module.AlphaEvolveClient(cfg, verbose=self.verbose)
        new_session_id = tmp_client.create_session()
        cfg.session = new_session_id
        config.save_session(cfg.profile_name, new_session_id)
        self.warn(f"Created session: {new_session_id}")
      except (ValueError, ImportError) as e:
        self.err(str(e))
      except Exception as e:  # pylint: disable=broad-exception-caught
        self.err(f"Error creating session: {e}")

    try:
      return client_module.AlphaEvolveClient(cfg, verbose=self.verbose)
    except (ValueError, ImportError) as e:
      self.err(str(e))

  def stdout_is_tty(self) -> bool:
    try:
      return sys.stdout.isatty()
    except (AttributeError, ValueError):
      return False

  def print_table(self, tbl: Any) -> None:
    if self.stdout_is_tty() and not self.compact:
      formatting.console.print(tbl)
    else:
      print(formatting.table_to_tsv(tbl))

  def print_empty(self, message: str) -> None:
    if self.json_output:
      print(json.dumps([]))
    else:
      self.warn(message)

  def output(
      self,
      data: Any,
      *,
      index: nicknames.NicknameIndex | None = None,
      table_fn: Any = None,
  ) -> None:
    """Prints structured data in JSON, compact, or Rich format."""
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
    if table_fn:
      formatting.console.print(table_fn)
    elif isinstance(data, dict):
      for k, v in data.items():
        rich.print(f"  [bold]{k}:[/bold] {v}")
    else:
      print(data)


# ---------------------------------------------------------------------------
# Shared resolution & cache helpers
# ---------------------------------------------------------------------------


def _invalidate_cache() -> None:
  resolution.invalidate_cache()


def _read_cached_experiments(
    state: _SandboxState,
) -> list[dict[str, Any]] | None:
  return resolution.read_cached_experiments(state.resolve_config())


def _read_cached_programs(
    state: _SandboxState, exp_id: str
) -> list[dict[str, Any]] | None:
  return resolution.read_cached_programs(state.resolve_config(), exp_id)


def _list_experiments_aggregated(
    state: _SandboxState,
    client: client_module.AlphaEvolveClient,
    page_size: int = 100,
) -> list[dict[str, Any]]:
  return resolution.list_experiments_aggregated(
      client, state.resolve_config(), page_size=page_size, warn_fn=state.warn
  )


def _resolve_experiment(
    state: _SandboxState,
    identifier: str,
    client: client_module.AlphaEvolveClient | None = None,
) -> str:
  if "/" in identifier:
    return identifier
  if client is None:
    client = state.get_client()
  return resolution.resolve_experiment(
      identifier, client, state.resolve_config(), warn_fn=state.warn
  )


def _resolve_program(
    state: _SandboxState,
    identifier: str,
    experiment: str | None = None,
    client: client_module.AlphaEvolveClient | None = None,
) -> str:
  """Resolves a program identifier to a full resource name."""
  if "/" in identifier:
    return identifier
  try:
    return resolution.resolve_program(
        identifier,
        experiment,
        state.resolve_config(),
        get_client_fn=lambda: client or state.get_client(),
        resolve_experiment_fn=lambda exp: _resolve_experiment(
            state, exp, client=client
        ),
        is_mcp=(state.mcp_caller is not None),
    )
  except ValueError as e:
    state.err(str(e))


def _get_program(
    state: _SandboxState,
    client: client_module.AlphaEvolveClient,
    prog_name: str,
) -> dict[str, Any]:
  return resolution.get_program(client, state.resolve_config(), prog_name)


def _prepare_program_dir_payload(
    state: _SandboxState, dir_path: str
) -> list[dict[str, str]]:
  """Bundles program .py files from a directory (excluding evaluator & tests)."""
  p_dir = pathlib.Path(dir_path)
  if not p_dir.is_dir():
    state.err(f"Not a directory: {dir_path}")

  exclude_prefixes = ("test_",)
  exclude_names = {"evaluator.py", "setup.py", "conftest.py"}
  py_files = [
      f
      for f in sorted(p_dir.glob("*.py"))
      if f.name not in exclude_names
      and not any(f.name.startswith(p) for p in exclude_prefixes)
  ]
  if not py_files:
    state.err(
        f"No program .py files found in {dir_path} (evaluator.py and test files"
        " are excluded)."
    )
  if not (p_dir / "initial_program.py").is_file():
    state.err(
        f"{dir_path} does not contain initial_program.py. The main program file"
        " must be named initial_program.py."
    )

  payload: list[dict[str, str]] = []
  total_chars = 0
  for fp in py_files:
    content = fp.read_text(encoding="utf-8")
    total_chars += len(content)
    payload.append({"path": fp.name, "content": content})

  estimated_tokens = total_chars // 4
  if estimated_tokens > 200_000 and not state.json_output:
    state.warn(
        f"Warning: Total program content is ~{estimated_tokens:,} tokens."
        " Context quality may degrade above ~200k tokens."
    )
  return payload


def _get_eval_insights(prog_data: dict[str, Any]) -> list[dict[str, str]]:
  return prog_data.get("evaluation", {}).get("insights", {}).get("insights", [])


def _report_already_running(
    state: _SandboxState, exp_data: dict[str, Any]
) -> None:
  if state.json_output:
    state.output(exp_data)
    return
  clean = formatting.clean_state(exp_data.get("state", ""))
  rich.print(
      "[green]✓[/green] Experiment is already running (state:"
      f" [bold]{clean}[/bold]); nothing to resume."
  )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_version(state: _SandboxState, unused_args: argparse.Namespace) -> None:
  """Handles `ae version`."""
  del state, unused_args
  print(f"ae {ae_version.__version__}")


def _cmd_config_show(
    state: _SandboxState, unused_args: argparse.Namespace
) -> None:
  """Handles `ae config show`."""
  del unused_args
  cfg = state.resolve_config()
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
  if state.json_output:
    print(json.dumps(data, indent=2))
  else:
    rich.print("\n[bold]Active Configuration[/bold]")
    rich.print("━" * 40)
    for k, v in data.items():
      rich.print(f"  [bold]{k}:[/bold] {v}")
    rich.print()


def _cmd_config_test(
    state: _SandboxState, unused_args: argparse.Namespace
) -> None:
  """Handles `ae config test`."""
  del unused_args
  cfg = state.resolve_config()
  account = "(unknown)"
  if state.mcp_caller is not None:
    account = "(MCP)"
  elif state.allow_gcloud and os.environ.get("ALPHAEVOLVE_NO_GCLOUD") != "1":
    try:
      account = subprocess.check_output(
          [config.gcloud_path(), "config", "get-value", "account"],
          text=True,
          encoding="utf-8",
          errors="replace",
      ).strip()
    except (subprocess.CalledProcessError, OSError):
      pass

  if not state.json_output:
    rich.print("\n[bold]Testing AlphaEvolve Setup[/bold]")
    rich.print("━" * 40)
    rich.print(f"Account:    [magenta]{account}[/magenta]")
    rich.print(f"Project:    [magenta]{cfg.project or '(unset)'}[/magenta]")
    rich.print(f"Location:   [magenta]{cfg.location}[/magenta]")
    rich.print(
        "Session:   "
        f" [magenta]{rich_markup.escape(cfg.session or '(unset)')}[/magenta]"
    )
    rich.print(
        "Base URL:  "
        f" [magenta]{cfg.base_url or client_module.build_base_url(cfg.location)}[/magenta]\n"
    )

  if not cfg.project:
    state.err("No project configured. Run `ae config --project=<id>`.")

  try:
    if state.mcp_caller is not None:
      client = client_module.AlphaEvolveClient(
          cfg, verbose=state.verbose, mcp_caller=state.mcp_caller
      )
      next(client.list_experiments(session_id="-", page_size=1), None)
    else:
      client = client_module.AlphaEvolveClient(cfg, verbose=state.verbose)
      if cfg.has_concrete_session():
        next(client.list_experiments(page_size=1), None)
      else:
        next(client.list_sessions(page_size=1), None)
  except client_module.ApiError as e:
    state.handle_api_error(e)
  except Exception as e:  # pylint: disable=broad-exception-caught
    state.err(str(e))

  if state.json_output:
    effective_session = (
        "-"
        if state.mcp_caller is not None and not cfg.has_valid_session()
        else cfg.session
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "account": account,
                "project": cfg.project,
                "location": cfg.location,
                "engine": cfg.engine,
                "session": effective_session,
                "transport": "mcp" if state.mcp_caller is not None else "rest",
            },
            indent=2,
        )
    )
  else:
    rich.print(
        "\n[green]✓ Success![/green] Connected to AlphaEvolve Cloud API."
    )


def _cmd_config_list(
    state: _SandboxState, unused_args: argparse.Namespace
) -> None:
  """Handles `ae config list`."""
  del unused_args
  profiles = config.list_profiles()
  active = config.get_active_profile_name()
  if not profiles:
    if state.json_output:
      print(json.dumps([]))
    else:
      rich.print(
          "No profiles found. Run `ae config --project=<id>` to create one."
      )
    return
  if state.json_output:
    print(json.dumps([{"name": p, "active": p == active} for p in profiles]))
  else:
    for p in profiles:
      marker = " [green]← active[/green]" if p == active else ""
      rich.print(f"  {p}{marker}")


def _cmd_config_switch(state: _SandboxState, args: argparse.Namespace) -> None:
  profile = args.profile
  if not config.profile_path(profile).exists():
    avail = ", ".join(config.list_profiles()) or "(none)"
    state.err(f"Profile '{profile}' not found. Available: {avail}")
  config.set_active_profile(profile)
  _invalidate_cache()
  if state.json_output:
    print(json.dumps({"active": profile}))
  else:
    rich.print(f"[green]✓[/green] Active profile: [bold]{profile}[/bold]")


def _cmd_config_discover(
    state: _SandboxState, unused_args: argparse.Namespace
) -> None:
  """Handles `ae config discover`."""
  del unused_args
  if (
      state.mcp_caller is not None
      or not state.allow_gcloud
      or os.environ.get("ALPHAEVOLVE_NO_GCLOUD") == "1"
  ):
    resolved = "gcloud"
    gcloud_found = False
  else:
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
  if state.json_output:
    print(json.dumps(data, indent=2))
  elif gcloud_found:
    rich.print(f"  [bold]gcloud:[/bold] {resolved}")
    rich.print(f"  [bold]project:[/bold] {project or '(not set)'}")
    if projects:
      rich.print(f"  [bold]available projects:[/bold] {len(projects)}")
  else:
    rich.print("[yellow]gcloud not found[/yellow]")


def _cmd_config_set(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae config --<flag>=<value>` profile updates."""
  if args.model is not None:
    state.warn("--model is deprecated; use --models")

  updates: dict[str, Any] = {}
  for key in (
      "project",
      "location",
      "collection",
      "engine",
      "session",
      "model",
      "base_url",
  ):
    val = getattr(args, key)
    if val is not None:
      updates[key] = val
  if args.models is not None:
    try:
      updates["models"] = config.parse_models_flag(
          args.models, warn_fn=state.warn
      )
    except ValueError as e:
      state.err(str(e))

  if not updates:
    state.err(
        "No configuration updates specified. Pass flags (e.g. --project=...,"
        " --engine=..., --models=...) or a subcommand (show, test, list,"
        " switch)."
    )

  existing = config.load_profile(args.name)
  existing.update(updates)
  path = config.save_profile(args.name, existing)
  if state.json_output:
    print(
        json.dumps(
            {"profile": args.name, "path": str(path), "updated": list(updates)}
        )
    )
  else:
    rich.print(
        f"[green]✓[/green] Updated profile [bold]{args.name}[/bold] → {path}"
    )


def _cmd_engine_list(
    state: _SandboxState, unused_args: argparse.Namespace
) -> None:
  """Handles `ae engine list`."""
  del unused_args
  try:
    client = state.get_client()
    engines = list(client.list_engines())
    if not engines:
      state.print_empty("No engines found.")
      return
    if state.json_output:
      print(json.dumps(engines, indent=2, default=str))
    else:
      cfg = state.resolve_config()
      state.print_table(
          formatting.format_engine_table(engines, active_engine=cfg.engine)
      )
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_create(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae experiment create`."""
  try:
    cfg = state.resolve_config()
    try:
      parsed = (
          config.parse_models_flag(args.models, warn_fn=state.warn)
          if args.models
          else None
      )
      resolved = config.resolve_models(
          parsed,
          args.model,
          cfg_models=cfg.models,
          cfg_model=config.config_model_preset(cfg, warn_fn=state.warn),
          warn_fn=state.warn,
      )
    except ValueError as e:
      state.err(str(e))

    problem_description = args.problem
    if problem_description and args.problem_file:
      state.err("Cannot specify both --problem and --problem-file")
    if args.problem_file:
      p_path = pathlib.Path(args.problem_file)
      if not p_path.exists():
        state.err(f"Problem file {args.problem_file} not found")
      problem_description = p_path.read_text(encoding="utf-8")

    client = state.get_client()
    generation_settings: dict[str, Any] = {}
    if resolved:
      generation_settings["models"] = resolved
    exp_config: dict[str, Any] = {
        "runSettings": {
            "maxPrograms": args.max_programs,
            "concurrency": args.concurrency,
        },
        "generationSettings": generation_settings,
    }
    if args.title:
      exp_config["title"] = args.title
    if problem_description:
      exp_config["problemDescription"] = problem_description
    if args.language:
      exp_config["programLanguage"] = args.language

    result = client.create_experiment({"config": exp_config})
    name = result.get("name", "")
    if name:
      nick, index = nicknames.NicknameIndex.get_nickname_synchronized(name)
    else:
      nick = ""
      index = nicknames.NicknameIndex()
    if state.json_output:
      print(formatting.to_json(result, "nickname", index))
    else:
      rich.print(f"[green]✓[/green] Created experiment [bold]{nick}[/bold]")
      formatting.console.print(
          formatting.format_experiment_detail(result, index)
      )
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_describe(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae experiment describe`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    result = client.get_experiment(exp_name)
    index = nicknames.NicknameIndex()
    if state.json_output:
      print(formatting.to_json(result, "nickname", index))
    else:
      formatting.console.print(
          formatting.format_experiment_detail(result, index)
      )
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_list(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae experiment list`."""
  try:
    if args.cached:
      experiments = _read_cached_experiments(state)
      if experiments is None:
        state.warn("No cache available, fetching…")
        client = state.get_client()
        experiments = _list_experiments_aggregated(
            state, client, page_size=args.page_size
        )
    else:
      client = state.get_client()
      experiments = _list_experiments_aggregated(
          state, client, page_size=args.page_size
      )

    if not experiments:
      state.print_empty("No experiments found.")
      return

    index = nicknames.NicknameIndex()
    index.add_many(experiments)
    if state.json_output:
      print(formatting.to_json(experiments, "nickname", index))
    else:
      try:
        experiments.sort(key=lambda x: x.get("createTime", ""), reverse=True)
      except (TypeError, AttributeError):
        pass
      state.print_table(formatting.format_experiment_table(experiments, index))
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_start(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae experiment start`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    exp_data = client.get_experiment(exp_name)
    exp_state = exp_data.get("state", "").removeprefix("EXPERIMENT_STATE_")
    if exp_state not in ("CREATED", "INITIALIZED", ""):
      hint = ""
      if exp_state in ("ACTIVE", "RUNNING"):
        hint = " Hint: Use `ae experiment run` to start the evaluation loop."
      state.err(
          f"Cannot start experiment in state {exp_state}. Only CREATED"
          f" experiments can be started.{hint}"
      )

    files_payload = _prepare_program_dir_payload(state, args.program_dir)
    if not state.json_output:
      rich.print(
          f"[dim]Bundling {len(files_payload)} program file(s) from"
          f" {args.program_dir}…[/dim]"
      )

    try:
      validated_score = evaluator_module.validate_score(args.score, "score")
    except evaluator_module.EvaluationError as e:
      state.err(str(e))

    program_body: dict[str, Any] = {
        "content": {"files": files_payload},
        "evaluation": {
            "scores": {
                "scores": [{"metric": "score", "score": validated_score}]
            }
        },
    }
    created = client.create_program(exp_name, program_body)
    initial_program_name = created.get("name")
    if initial_program_name and not state.json_output:
      rich.print(
          "[green]✓[/green] Initial program created:"
          f" [bold]{initial_program_name.split('/')[-1]}[/bold]"
      )

    result = client.start_experiment(exp_name)
    op_name = result.get("name", "")
    if not state.json_output:
      rich.print(
          "[green]✓[/green] Experiment started. Operation:"
          f" [bold]{op_name}[/bold]"
      )
    if op_name:
      config.save_operation(exp_name, op_name)
    _invalidate_cache()
    state.output(result)
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_resume(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae experiment resume`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    exp_data = client.get_experiment(exp_name)
    if formatting.clean_state(exp_data.get("state", "")) in _RUNNING_STATES:
      _report_already_running(state, exp_data)
      return

    try:
      result = client.resume_experiment(exp_name)
    except client_module.ApiError as e:
      if e.status_code == 400 and any(
          f"Cannot resume experiment from state {s}" in e.message
          for s in _RUNNING_STATES
      ):
        _report_already_running(state, client.get_experiment(exp_name))
        return
      raise

    op_name = result.get("name", "")
    if not state.json_output:
      rich.print(
          "[green]✓[/green] Experiment resumed. Operation:"
          f" [bold]{op_name}[/bold]"
      )
    if op_name:
      config.save_operation(exp_name, op_name)
    _invalidate_cache()
    state.output(result)
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_delete(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae experiment delete`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    if not args.force:
      state.err("Pass --force to delete an experiment in non-interactive mode.")
    client.delete_experiment(exp_name)
    _invalidate_cache()
    if state.json_output:
      print(json.dumps({"deleted": exp_name}))
    else:
      rich.print(f"[green]✓[/green] Deleted: [bold]{args.experiment}[/bold]")
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_experiment_run(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae experiment run`."""
  evaluator_path = pathlib.Path(args.evaluator)
  if not evaluator_path.exists():
    state.err(f"Evaluator not found: {args.evaluator}")
  if args.extra_evaluator_args:
    try:
      shlex.split(args.extra_evaluator_args, posix=(os.name != "nt"))
    except ValueError as e:
      state.err(f"Invalid extra-evaluator-args: {e}")

  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    dash_path = pathlib.Path(args.dashboard) if args.dashboard else None
    index = nicknames.NicknameIndex.load()
    exp_nick = index.get_nickname(exp_name) or args.experiment
    cfg = state.resolve_config()
    lock_cache = locks.LockCache(cfg.profile_name)

    def _log(msg: str) -> None:
      if state.json_output:
        state.warn(msg)
      else:
        rich.print(msg)

    class _RunCallbacks(controller_module.ControllerCallbacks):
      """Progress and dashboard callbacks for the controller loop."""

      def on_acquire(self, program_name: str, nickname: str) -> None:
        del program_name
        _log(f"  Acquired: {nickname}")

      def on_evaluate(
          self,
          program_name: str,
          nickname: str,
          result: evaluator_module.EvaluationResult,
      ) -> None:
        del program_name
        if result.success:
          _log(f"  ✓ {nickname} score={result.score:.6f}")
        else:
          _log(f"  ✗ {nickname} failed: {result.error}")

      def on_submit(
          self, program_name: str, nickname: str, score: float
      ) -> None:
        del program_name, score
        _log(f"  Submitted: {nickname}")

      def on_new_best(
          self, program_name: str, nickname: str, score: float
      ) -> None:
        del program_name
        _log(f"  ★ New best: {nickname} score={score:.6f}")

      def on_no_programs(self) -> None:
        _log("  No programs available, waiting…")

      def on_experiment_terminal(self, exp_state: str) -> None:
        _log(f"  Experiment reached terminal state: {exp_state}")

      def on_error(self, stage: str, error: Exception) -> None:
        _log(f"  Error ({stage}): {error}")

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
        _log(
            f"  Progress: {progress} | succeeded={stats.total_succeeded}"
            f" failed={stats.total_failed}"
        )
        if dash_path is not None:
          self.write_dashboard("RUNNING")

      def write_dashboard(self, exp_state: str) -> None:
        if dash_path is None:
          return
        try:
          all_progs = list(client.list_programs(exp_name))
          succeeded = []
          failed = []
          scored_progs = []
          for p in all_progs:
            scores = p.get("evaluation", {}).get("scores", {}).get("scores", [])
            if scores:
              try:
                score_val = float(scores[0].get("score", 0.0))
                if score_val != evaluator_module.FAILURE_SCORE:
                  succeeded.append(p)
                  p_name = p.get("name") or ""
                  nick = (
                      index.get_nickname(p_name)
                      if p_name
                      else p.get("nickname", "")
                  )
                  scored_progs.append((nick, score_val))
                else:
                  failed.append(p)
              except (ValueError, TypeError):
                pass
          scored_progs.sort(key=lambda x: x[1], reverse=True)
          succeeded.sort(key=lambda p: p.get("createTime", ""))
          global_history = []
          for i, p in enumerate(succeeded, 1):
            scores = p.get("evaluation", {}).get("scores", {}).get("scores", [])
            if scores:
              try:
                global_history.append((i, float(scores[0].get("score", 0.0))))
              except (ValueError, TypeError):
                pass
          dashboard.write_dashboard(
              path=dash_path,
              nickname=exp_nick,
              state=exp_state,
              total_evaluated=len(all_progs),
              total_succeeded=len(succeeded),
              total_failed=len(failed),
              best_score=scored_progs[0][1] if scored_progs else None,
              best_nickname=scored_progs[0][0] if scored_progs else None,
              score_history=global_history,
              leaderboard=[
                  {"nickname": n, "score": s} for n, s in scored_progs[:10]
              ],
          )
        except Exception as e:  # pylint: disable=broad-exception-caught
          state.warn(f"Dashboard write failed: {e!r}")

    _log(f"Running controller loop for {args.experiment}")
    cb = _RunCallbacks()
    stats = controller_module.run_controller_loop(
        client=client,
        experiment_name=exp_name,
        evaluator_path=evaluator_path,
        max_iterations=args.max_iterations,
        timeout=args.timeout,
        backend=args.backend,
        callbacks=cb,
        lock_cache=lock_cache,
        extra_evaluator_args=args.extra_evaluator_args,
    )

    if dash_path is not None:
      try:
        final_state = client.get_experiment(exp_name).get("state", "UNKNOWN")
      except client_module.ApiError:
        final_state = "UNKNOWN"
      cb.write_dashboard(final_state)
      _log(f"  Dashboard written to {dash_path}")

    if state.json_output:
      print(json.dumps(stats.to_dict(), indent=2))
    else:
      rich.print("\n[bold]Controller finished.[/bold]")
      rich.print(f"  Total evaluated: {stats.total_evaluated}")
      rich.print(f"  Succeeded: {stats.total_succeeded}")
      rich.print(f"  Failed: {stats.total_failed}")
      if stats.best_score is not None:
        rich.print(f"  Best score: {stats.best_score:.6f}")
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_program_list(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae program list`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    exp_id = exp_name.split("/")[-1]
    cfg = state.resolve_config()

    programs = None
    if args.cached:
      programs = _read_cached_programs(state, exp_id)
      if programs is None:
        state.warn("No cache available, fetching…")

    if programs is None:
      programs = list(
          client.list_programs(
              exp_name,
              page_size=args.page_size,
              order_by=args.order_by,
              state_filter=args.state,
          )
      )
      config.save_cache(f"programs_list_{cfg.profile_name}_{exp_id}", programs)

    if not programs:
      state.print_empty("No programs found.")
      return
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    index.save()
    if state.json_output:
      print(formatting.to_json(programs, "nickname", index))
    else:
      state.print_table(formatting.format_program_table(programs, index))
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_program_show(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae program show`."""
  try:
    client = state.get_client()
    prog_name = _resolve_program(
        state, args.program, args.experiment, client=client
    )
    prog_data = _get_program(state, client, prog_name)
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
    content = prog_data.get("content")
    files = content.get("files", []) if isinstance(content, dict) else []

    if args.output_file:
      if files:
        if len(files) > 1:
          state.warn(
              "Warning: Program has multiple files. Saving the first one."
          )
        with open(args.output_file, "w", encoding="utf-8") as f:
          f.write(files[0].get("content", ""))
        state.warn(f"Saved program code to {args.output_file}")
      else:
        state.err("No file content found in program.")

    if state.json_output:
      print(formatting.to_json(prog_data, "nickname", index))
    elif args.code and not state.stdout_is_tty():
      if not files:
        state.err("No file content found in program.")
      for f in files:
        if len(files) > 1:
          sys.stdout.write(f"# --- {f.get('path', 'unknown')} ---\n")
        file_content = f.get("content", "")
        sys.stdout.write(file_content)
        if file_content and not file_content.endswith("\n"):
          sys.stdout.write("\n")
      if args.insights:
        for insight in _get_eval_insights(prog_data):
          if text := insight.get("text", ""):
            state.warn(
                f"{insight.get('label', 'info')}: {text[:_MAX_INSIGHT_CHARS]}"
            )
    else:
      if args.code:
        for f in files:
          path = f.get("path", "unknown")
          file_content = f.get("content", "")
          rich.print(f"\n[bold]── {path} ──[/bold]")
          formatting.console.print(
              formatting.syntax.Syntax(file_content, "python", theme="monokai")
          )
      if args.insights:
        eval_insights = _get_eval_insights(prog_data)
        if eval_insights:
          rich.print("\n[bold]── Evaluation Insights ──[/bold]")
          for insight in eval_insights:
            label = insight.get("label", "info")
            text = insight.get("text", "")
            if text:
              rich.print(
                  f"  [bold]{rich_markup.escape(label)}:[/bold]"
                  f" {rich_markup.escape(text[:_MAX_INSIGHT_CHARS])}"
              )
        else:
          rich.print("\n[dim]No evaluation insights available.[/dim]")
      formatting.console.print(
          formatting.format_program_detail(prog_data, index)
      )
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_program_diff(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae program diff`."""
  try:
    client = state.get_client()
    prog_name = _resolve_program(
        state, args.program, args.experiment, client=client
    )
    prog_data = _get_program(state, client, prog_name)
    parent_names = prog_data.get("parentPrograms", [])

    if not parent_names:
      index = nicknames.NicknameIndex()
      if state.json_output:
        print(formatting.to_json(prog_data, "nickname", index))
      else:
        rich.print(
            "[dim]This program has no parent (it's an initial program).[/dim]"
        )
        formatting.console.print(
            formatting.format_program_detail(prog_data, index)
        )
      return

    parent_data = _get_program(state, client, parent_names[0])
    prog_files = prog_data.get("content", {}).get("files", [])
    parent_files = parent_data.get("content", {}).get("files", [])
    for pf, cf in zip(parent_files, prog_files):
      diff_syntax = formatting.format_diff(
          pf.get("content", ""),
          cf.get("content", ""),
          from_file=f"parent/{pf.get('path', '?')}",
          to_file=f"current/{cf.get('path', '?')}",
      )
      formatting.console.print(diff_syntax)
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_program_evaluate(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae program evaluate`."""
  evaluator_path = pathlib.Path(args.evaluator)
  if not evaluator_path.exists():
    state.err(f"Evaluator not found: {args.evaluator}")

  specified = sum(
      1 for x in (args.program_file, args.program_name, args.program_dir) if x
  )
  if specified != 1:
    state.err(
        "Specify exactly one of --program-file, --program-name, or"
        " --program-dir."
    )

  program_files: list[dict[str, str]] = []
  if args.program_dir:
    p_dir = pathlib.Path(args.program_dir)
    if not p_dir.is_dir():
      state.err(f"Not a directory: {args.program_dir}")
    py_files = sorted(p_dir.glob("*.py"))
    if not py_files:
      state.err(f"No .py files found in {args.program_dir}")
    for fp in py_files:
      program_files.append(
          {"path": fp.name, "content": fp.read_text(encoding="utf-8")}
      )
  elif args.program_file:
    local_path = pathlib.Path(args.program_file)
    if not local_path.exists() or not local_path.is_file():
      state.err(f"Program file not found: {args.program_file}")
    program_files.append({
        "path": local_path.name,
        "content": local_path.read_text(encoding="utf-8"),
    })
  elif args.program_name:
    if not args.experiment:
      state.err("--experiment is required when --program-name is used.")
    try:
      client = state.get_client()
      prog_name = _resolve_program(
          state, args.program_name, args.experiment, client=client
      )
      prog_data = _get_program(state, client, prog_name)
      files = prog_data.get("content", {}).get("files", [])
      if not files:
        state.err("Program has no files.")
      for f in files:
        program_files.append({
            "path": f.get("path", "program.py"),
            "content": f.get("content", ""),
        })
    except client_module.ApiError as e:
      state.handle_api_error(e)

  eval_work_dir = pathlib.Path(args.work_dir) if args.work_dir else None
  try:
    eval_result = evaluator_module.evaluate_program(
        program_files=program_files,
        evaluator_path=evaluator_path,
        backend=args.backend,
        timeout=args.timeout,
        work_dir=eval_work_dir,
    )
  except ValueError as e:
    state.err(f"{e!r}")

  if state.json_output:
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
    raise _CliExitError(1)


def _cmd_program_acquire(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae program acquire`."""
  if state.json_output and args.program_dir:
    state.err("Cannot specify both --json and --program-dir")
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    result = client.acquire_programs(exp_name, desired_count=args.count)

    cfg = state.resolve_config()
    lock_cache = locks.LockCache(cfg.profile_name)
    programs = result.get("programs") or result.get("alphaEvolvePrograms", [])
    lock_token = result.get("lockToken") or ""

    for p in programs:
      p_name = p.get("name", "")
      p_lock_token = p.get("lockToken") or p.get("lock_token") or lock_token
      if p_name and p_lock_token:
        lock_cache.add(p_name, p_lock_token)

    if args.program_dir:
      p_path = pathlib.Path(args.program_dir)
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
          (p_path / f"{nick}.py").write_text(code, encoding="utf-8")
          (p_path / f"{nick}.lock").write_text(p_lock_token, encoding="utf-8")
          rich.print(f"  [green]✓[/green] Saved {nick}.py and {nick}.lock")
      index.save()
    else:
      state.output(result, index=nicknames.NicknameIndex())
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_program_submit(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae program submit`."""
  if (args.score is None) == (args.metrics_file is None):
    state.err("Specify exactly one of --score or --metrics-file.")

  if args.metrics_file is not None:
    try:
      evaluation_payload = evaluator_module.parse_metrics_file(
          pathlib.Path(args.metrics_file)
      )
    except evaluator_module.EvaluationError as e:
      state.err(str(e))
  else:
    try:
      validated_score = evaluator_module.validate_score(args.score, "score")
    except evaluator_module.EvaluationError as e:
      state.err(str(e))
    evaluation_payload = {
        "scores": {"scores": [{"metric": "score", "score": validated_score}]}
    }

  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    cfg = state.resolve_config()
    lock_cache = locks.LockCache(cfg.profile_name)

    resolved_program = args.program
    if args.program:
      resolved_program = _resolve_program(
          state, args.program, args.experiment, client=client
      )

    lock_token = args.lock_token
    if resolved_program and not lock_token:
      lock_token = lock_cache.get(resolved_program)

    if bool(resolved_program) != bool(lock_token):
      state.err(
          "Both --program and --lock-token must be provided together (for"
          " acquired programs), or neither (for new programs)."
      )

    if resolved_program:
      submission = {
          "program": resolved_program,
          "lockToken": lock_token,
          "evaluation": evaluation_payload,
      }
      result = client.submit_evaluations(exp_name, [submission])
      state.output(result, index=nicknames.NicknameIndex())
    else:
      if not args.program_dir:
        state.err(
            "--program-dir is required when creating a new program (without"
            " --program/--lock-token)."
        )
      files_payload = _prepare_program_dir_payload(state, args.program_dir)
      program_body = {
          "content": {"files": files_payload},
          "evaluation": evaluation_payload,
      }
      result = client.create_program(exp_name, program_body)
      state.output(result, index=nicknames.NicknameIndex())
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_results_best(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae results best`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
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

    all_programs.sort(key=_get_score, reverse=True)
    programs = all_programs[: args.top]
    if not programs:
      state.print_empty("No scored programs found.")
      return
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    index.save()
    if state.json_output:
      print(formatting.to_json(programs, "nickname", index))
    else:
      state.print_table(formatting.format_program_table(programs, index))
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_results_history(
    state: _SandboxState, args: argparse.Namespace
) -> None:
  """Handles `ae results history`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    programs = list(client.list_programs(exp_name))
    programs.sort(key=lambda p: p.get("createTime", ""))
    if not programs:
      state.print_empty("No programs found.")
      return
    index = nicknames.NicknameIndex()
    index.add_many(programs)
    index.save()
    if state.json_output:
      print(formatting.to_json(programs, "nickname", index))
    else:
      state.print_table(formatting.format_program_table(programs, index))
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_results_failed(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae results failed`."""
  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
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
      if score is None or score <= evaluator_module.FAILURE_SCORE:
        failed.append(p)

    if not failed:
      state.print_empty("No failed programs found.")
      return

    index = nicknames.NicknameIndex()
    index.add_many(all_programs)
    index.save()

    if state.json_output:
      print(formatting.to_json(failed, "nickname", index))
      return

    for prog in failed:
      nick = index.get_nickname(prog.get("name", ""))
      rich.print(f"\n[bold red]FAILED:[/bold red] [bold]{nick}[/bold]")
      eval_insights = _get_eval_insights(prog)
      if eval_insights:
        for insight in eval_insights:
          label = insight.get("label", "info")
          text = insight.get("text", "")
          if text:
            rich.print(
                f"  \\[{rich_markup.escape(label)}]"
                f" {rich_markup.escape(text[:_MAX_INSIGHT_CHARS])}"
            )
      else:
        rich.print("  [dim]No insights available.[/dim]")
      for f in prog.get("content", {}).get("files", []):
        content = f.get("content", "")
        if "EVOLVE-BLOCK-START" in content:
          in_block = False
          block_lines = []
          for line in content.split("\n"):
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
              rich.print(f"    {rich_markup.escape(bl)}")
            if len(block_lines) > _MAX_EVOLVE_BLOCK_LINES:
              remaining = len(block_lines) - _MAX_EVOLVE_BLOCK_LINES
              rich.print(f"    [dim]... ({remaining} more lines)[/dim]")
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_results_plot(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae results plot`."""
  from . import visualization  # pylint: disable=g-import-not-at-top

  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    if not state.json_output:
      rich.print("[dim]Fetching experiment data...[/dim]")
    programs = list(client.list_programs(exp_name))
    programs.sort(key=lambda p: p.get("createTime", ""))
    if not programs:
      state.err("No programs found.")

    index = nicknames.NicknameIndex.load()
    index.add_many(programs)
    index.save()
    exp_nick = index.get_nickname(exp_name) or args.experiment
    chart_title = args.title or f"Experiment: {exp_nick}"
    output_path = pathlib.Path(args.output)
    visualization.generate_plot(
        programs=programs,
        output_path=output_path,
        title=chart_title,
        nickname_fn=index.get_nickname,
    )
    if state.json_output:
      print(json.dumps({"output": str(output_path.resolve())}))
    else:
      rich.print(
          "[green]✓[/green] Chart saved to"
          f" [bold]{output_path.resolve()}[/bold]"
      )
  except client_module.ApiError as e:
    state.handle_api_error(e)


def _cmd_results_report(state: _SandboxState, args: argparse.Namespace) -> None:
  """Handles `ae results report`."""
  from . import visualization  # pylint: disable=g-import-not-at-top

  try:
    client = state.get_client()
    exp_name = _resolve_experiment(state, args.experiment, client=client)
    if not state.json_output:
      rich.print("[dim]Fetching experiment data...[/dim]")
    programs = list(client.list_programs(exp_name))
    programs.sort(key=lambda p: p.get("createTime", ""))
    if not programs:
      state.err("No programs found.")

    index = nicknames.NicknameIndex.load()
    index.add_many(programs)
    index.save()
    exp_data = client.get_experiment(exp_name)
    exp_nick = index.get_nickname(exp_name) or args.experiment

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
        hours, remainder = divmod(int((end - start).total_seconds()), 3600)
        minutes = remainder // 60
        duration = f"{hours}h {minutes}m" if hours else f"{minutes}m"
      except (ValueError, TypeError):
        pass

    md_path = pathlib.Path(args.markdown) if args.markdown else None
    output_path = pathlib.Path(args.output)
    visualization.generate_html_report(
        programs=programs,
        output_path=output_path,
        nickname=exp_nick,
        model=model,
        duration=duration,
        markdown_path=md_path,
        nickname_fn=index.get_nickname,
    )
    if state.json_output:
      print(json.dumps({"output": str(output_path.resolve())}))
    else:
      rich.print(
          "[green]✓[/green] Interactive report saved to"
          f" [bold]{output_path.resolve()}[/bold]"
      )
  except client_module.ApiError as e:
    state.handle_api_error(e)


# ---------------------------------------------------------------------------
# Argument parser construction
# ---------------------------------------------------------------------------


def _build_config_set_parser() -> argparse.ArgumentParser:
  """Builds the argparse parser for `ae config --<flag>=<value>`."""
  parser = argparse.ArgumentParser(
      prog="ae config",
      description=(
          "Manage CLI configuration. Subcommands: show, test, list, switch,"
          " discover. Or pass flags below to update a profile."
      ),
  )
  parser.add_argument("--name", default="default", help="Profile name.")
  parser.add_argument(
      "--project", default=None, help="Google Cloud project ID."
  )
  parser.add_argument(
      "--location", default=None, help="Discovery Engine location."
  )
  parser.add_argument(
      "--collection", default=None, help="Discovery Engine collection ID."
  )
  parser.add_argument(
      "--engine", default=None, help="Discovery Engine app/engine ID."
  )
  parser.add_argument("--session", default=None, help="Session ID or '-'.")
  parser.add_argument(
      "--model",
      default=None,
      help="[DEPRECATED: use --models] Base model enum.",
  )
  parser.add_argument(
      "--models",
      action="append",
      default=None,
      help="Generation model spec; repeat per model.",
  )
  parser.add_argument(
      "--base-url",
      dest="base_url",
      default=None,
      help="API base URL to override the default.",
  )
  return parser


def _dispatch_config(state: _SandboxState, config_args: list[str]) -> None:
  """Handles both `ae config <subcommand>` and `ae config --flag=...`."""
  if not config_args:
    _build_config_set_parser().print_help()
    raise _CliExitError(1)

  first = config_args[0]
  if first in ("-h", "--help"):
    _build_config_set_parser().print_help()
    return

  if first == "show":
    p = argparse.ArgumentParser(prog="ae config show")
    _cmd_config_show(state, p.parse_args(config_args[1:]))
  elif first == "test":
    p = argparse.ArgumentParser(prog="ae config test")
    _cmd_config_test(state, p.parse_args(config_args[1:]))
  elif first == "list":
    p = argparse.ArgumentParser(prog="ae config list")
    _cmd_config_list(state, p.parse_args(config_args[1:]))
  elif first == "switch":
    p = argparse.ArgumentParser(prog="ae config switch")
    p.add_argument("profile", help="Profile name to switch to.")
    _cmd_config_switch(state, p.parse_args(config_args[1:]))
  elif first == "discover":
    p = argparse.ArgumentParser(prog="ae config discover")
    _cmd_config_discover(state, p.parse_args(config_args[1:]))
  else:
    p = _build_config_set_parser()
    _cmd_config_set(state, p.parse_args(config_args))


def _build_parser() -> argparse.ArgumentParser:
  """Builds the top-level stdlib argparse CLI parser."""
  parser = argparse.ArgumentParser(
      prog="ae",
      description="CLI for the AlphaEvolve Cloud API.",
  )
  parser.add_argument("--project", default=None, help="GCP project ID.")
  parser.add_argument("--location", default=None, help="API location.")
  parser.add_argument(
      "--json",
      dest="json_output",
      action="store_true",
      help="JSON output mode.",
  )
  parser.add_argument(
      "--compact", action="store_true", help="Compact output mode."
  )
  parser.add_argument("--verbose", action="store_true", help="Debug logging.")

  subparsers = parser.add_subparsers(dest="command")

  # version
  p_version = subparsers.add_parser("version", help="Show the CLI version.")
  p_version.set_defaults(handler=_cmd_version)

  # config (custom dispatch to support both flags and subcommands)
  p_config = subparsers.add_parser(
      "config", help="Manage CLI configuration.", add_help=False
  )
  p_config.add_argument("config_args", nargs=argparse.REMAINDER)

  # engine
  p_engine = subparsers.add_parser("engine", help="Manage engines.")
  engine_sub = p_engine.add_subparsers(dest="engine_cmd")
  p_eng_list = engine_sub.add_parser("list", help="List available engines.")
  p_eng_list.set_defaults(handler=_cmd_engine_list)

  # experiment
  p_exp = subparsers.add_parser("experiment", help="Manage experiments.")
  exp_sub = p_exp.add_subparsers(dest="experiment_cmd")

  p_exp_create = exp_sub.add_parser("create", help="Create a new experiment.")
  p_exp_create.add_argument(
      "--max-programs",
      type=int,
      required=True,
      help="Max programs to generate.",
  )
  p_exp_create.add_argument(
      "--concurrency", type=int, default=4, help="Concurrency limit."
  )
  p_exp_create.add_argument("--title", default="", help="Experiment title.")
  p_exp_create.add_argument(
      "--problem", default="", help="Problem description."
  )
  p_exp_create.add_argument(
      "--problem-file", default="", help="File containing problem description."
  )
  p_exp_create.add_argument(
      "--language", default="python", help="Programming language."
  )
  p_exp_create.add_argument(
      "--model", default="", help="[DEPRECATED: use --models] LLM model preset."
  )
  p_exp_create.add_argument(
      "--models",
      action="append",
      default=None,
      help="Generation model spec; repeat per model.",
  )
  p_exp_create.set_defaults(handler=_cmd_experiment_create)

  p_exp_desc = exp_sub.add_parser(
      "describe", help="Show details of an experiment."
  )
  p_exp_desc.add_argument(
      "experiment", help="Experiment name, ID, or nickname."
  )
  p_exp_desc.set_defaults(handler=_cmd_experiment_describe)

  p_exp_list = exp_sub.add_parser("list", help="List experiments.")
  p_exp_list.add_argument(
      "--page-size", type=int, default=100, help="Results per page."
  )
  p_exp_list.add_argument(
      "-c", "--cached", action="store_true", help="Use cached results."
  )
  p_exp_list.set_defaults(handler=_cmd_experiment_list)

  p_exp_start = exp_sub.add_parser("start", help="Start an experiment.")
  p_exp_start.add_argument("experiment", help="Experiment name or ID.")
  p_exp_start.add_argument(
      "--program-dir", required=True, help="Directory with program .py files."
  )
  p_exp_start.add_argument(
      "--score", type=float, required=True, help="Initial program score."
  )
  p_exp_start.set_defaults(handler=_cmd_experiment_start)

  p_exp_resume = exp_sub.add_parser(
      "resume", help="Resume a paused experiment."
  )
  p_exp_resume.add_argument("experiment", help="Experiment name or ID.")
  p_exp_resume.set_defaults(handler=_cmd_experiment_resume)

  p_exp_delete = exp_sub.add_parser("delete", help="Delete an experiment.")
  p_exp_delete.add_argument("experiment", help="Experiment name or ID.")
  p_exp_delete.add_argument(
      "--force", action="store_true", help="Skip confirmation."
  )
  p_exp_delete.set_defaults(handler=_cmd_experiment_delete)

  p_exp_run = exp_sub.add_parser(
      "run", help="Run the acquire + evaluate + submit controller loop."
  )
  p_exp_run.add_argument("experiment", help="Experiment name or ID.")
  p_exp_run.add_argument(
      "--evaluator", required=True, help="Path to the evaluator script."
  )
  p_exp_run.add_argument(
      "--max-iterations",
      type=int,
      default=0,
      help="Max evaluation iterations (0 = unlimited).",
  )
  p_exp_run.add_argument(
      "--timeout",
      type=int,
      default=evaluator_module.DEFAULT_TIMEOUT_SECONDS,
      help="Evaluation timeout in seconds.",
  )
  p_exp_run.add_argument(
      "--backend", default="local", help="Evaluation backend: local or podman."
  )
  p_exp_run.add_argument(
      "--dashboard", default=None, help="Path to a markdown dashboard file."
  )
  p_exp_run.add_argument(
      "--extra-evaluator-args",
      default=None,
      help="Extra arguments passed to the evaluator script.",
  )
  p_exp_run.set_defaults(handler=_cmd_experiment_run)

  # program
  p_prog = subparsers.add_parser("program", help="Manage programs.")
  prog_sub = p_prog.add_subparsers(dest="program_cmd")

  p_prog_list = prog_sub.add_parser("list", help="List programs.")
  p_prog_list.add_argument("experiment", help="Experiment name or ID.")
  p_prog_list.add_argument("--order-by", default=None, help="Sort field.")
  p_prog_list.add_argument("--state", default=None, help="Filter by state.")
  p_prog_list.add_argument(
      "--page-size", type=int, default=100, help="Results per page."
  )
  p_prog_list.add_argument(
      "-c", "--cached", action="store_true", help="Use cached results."
  )
  p_prog_list.set_defaults(handler=_cmd_program_list)

  p_prog_show = prog_sub.add_parser("show", help="Show details of a program.")
  p_prog_show.add_argument("program", help="Program name or ID.")
  p_prog_show.add_argument(
      "--experiment", default=None, help="Parent experiment."
  )
  p_prog_show.add_argument(
      "--code", action="store_true", help="Show program source code."
  )
  p_prog_show.add_argument(
      "--insights", action="store_true", help="Show evaluation insights."
  )
  p_prog_show.add_argument(
      "--output-file", default=None, help="Save program code to file."
  )
  p_prog_show.set_defaults(handler=_cmd_program_show)

  p_prog_diff = prog_sub.add_parser(
      "diff", help="Show diff between a program and its parent."
  )
  p_prog_diff.add_argument("program", help="Program name or ID.")
  p_prog_diff.add_argument(
      "--experiment", default=None, help="Parent experiment."
  )
  p_prog_diff.set_defaults(handler=_cmd_program_diff)

  p_prog_eval = prog_sub.add_parser(
      "evaluate", help="Evaluate a program using a local evaluator script."
  )
  p_prog_eval.add_argument(
      "--evaluator", required=True, help="Path to the evaluator script."
  )
  p_prog_eval.add_argument(
      "--program-file", default=None, help="Local program .py file."
  )
  p_prog_eval.add_argument(
      "--program-name", default=None, help="Program resource name or nickname."
  )
  p_prog_eval.add_argument(
      "--program-dir", default=None, help="Directory of program files."
  )
  p_prog_eval.add_argument(
      "--experiment", default=None, help="Parent experiment."
  )
  p_prog_eval.add_argument(
      "--backend", default="local", help="Evaluation backend."
  )
  p_prog_eval.add_argument(
      "--timeout",
      type=int,
      default=evaluator_module.DEFAULT_TIMEOUT_SECONDS,
      help="Evaluation timeout in seconds.",
  )
  p_prog_eval.add_argument(
      "--work-dir", default=None, help="Evaluation workspace directory."
  )
  p_prog_eval.set_defaults(handler=_cmd_program_evaluate)

  p_prog_acq = prog_sub.add_parser(
      "acquire", help="Acquire programs for evaluation."
  )
  p_prog_acq.add_argument("experiment", help="Experiment name or ID.")
  p_prog_acq.add_argument(
      "--count", type=int, default=1, help="Number of programs to acquire."
  )
  p_prog_acq.add_argument(
      "--program-dir",
      default=None,
      help="Directory to save acquired programs and lock files.",
  )
  p_prog_acq.set_defaults(handler=_cmd_program_acquire)

  p_prog_sub = prog_sub.add_parser(
      "submit", help="Submit an evaluation or create a new program."
  )
  p_prog_sub.add_argument("experiment", help="Experiment name or ID.")
  p_prog_sub.add_argument(
      "--score", type=float, default=None, help="Evaluation score."
  )
  p_prog_sub.add_argument(
      "--metrics-file",
      default=None,
      help="JSON file with multi-metric scores and optional insights.",
  )
  p_prog_sub.add_argument(
      "--program-dir",
      default=None,
      help="Directory containing program .py files (for new programs).",
  )
  p_prog_sub.add_argument(
      "--program",
      default=None,
      help="Resource name or nickname of an acquired program.",
  )
  p_prog_sub.add_argument(
      "--lock-token", default=None, help="Lock token of an acquired program."
  )
  p_prog_sub.set_defaults(handler=_cmd_program_submit)

  # results
  p_res = subparsers.add_parser("results", help="View results.")
  res_sub = p_res.add_subparsers(dest="results_cmd")

  p_res_best = res_sub.add_parser(
      "best", help="Show the best-scoring programs."
  )
  p_res_best.add_argument("experiment", help="Experiment name or ID.")
  p_res_best.add_argument(
      "--top", type=int, default=5, help="Number of top programs."
  )
  p_res_best.set_defaults(handler=_cmd_results_best)

  p_res_hist = res_sub.add_parser(
      "history", help="Show evaluation history for an experiment."
  )
  p_res_hist.add_argument("experiment", help="Experiment name or ID.")
  p_res_hist.set_defaults(handler=_cmd_results_history)

  p_res_fail = res_sub.add_parser(
      "failed", help="Show failed programs with their error insights."
  )
  p_res_fail.add_argument("experiment", help="Experiment name or ID.")
  p_res_fail.set_defaults(handler=_cmd_results_failed)

  p_res_plot = res_sub.add_parser(
      "plot", help="Generate a score progression chart (PNG)."
  )
  p_res_plot.add_argument("experiment", help="Experiment name or ID.")
  p_res_plot.add_argument(
      "-o",
      "--output",
      default="score_progression.png",
      help="Output PNG file path.",
  )
  p_res_plot.add_argument("--title", default=None, help="Chart title.")
  p_res_plot.set_defaults(handler=_cmd_results_plot)

  p_res_rep = res_sub.add_parser(
      "report", help="Generate an interactive HTML report."
  )
  p_res_rep.add_argument("experiment", help="Experiment name or ID.")
  p_res_rep.add_argument(
      "-o",
      "--output",
      default="experiment_report.html",
      help="Output HTML file path.",
  )
  p_res_rep.add_argument(
      "--markdown",
      default=None,
      help="Path to a markdown report to embed below the chart.",
  )
  p_res_rep.set_defaults(handler=_cmd_results_report)

  return parser


_GLOBAL_VALUE_FLAGS = frozenset({"--project", "--location"})
_GLOBAL_BOOL_FLAGS = frozenset({"--json", "--compact", "--verbose"})


def _extract_config_invocation(
    raw_argv: list[str],
) -> tuple[list[str], list[str]] | None:
  """Splits `[global flags...] config [config args...]` without mangling flags.

  `argparse`'s `REMAINDER` rejects leading options like `config --project=123`,
  so we split around the `config` subcommand token directly while preserving
  exact argument order.

  Args:
    raw_argv: Raw CLI argument list excluding the executable name.

  Returns:
    A `(global_tokens, config_tokens)` tuple if the command is `config`, or
    `None` for all other commands.
  """
  i = 0
  while i < len(raw_argv):
    tok = raw_argv[i]
    if tok in _GLOBAL_BOOL_FLAGS:
      i += 1
    elif tok in _GLOBAL_VALUE_FLAGS:
      i += 2
    elif any(tok.startswith(f"{flag}=") for flag in _GLOBAL_VALUE_FLAGS):
      i += 1
    elif tok == "config":
      return raw_argv[:i], raw_argv[i + 1 :]
    else:
      return None
  return None


def main(
    argv: list[str] | None = None,
    *,
    mcp_caller: client_module.McpCaller | None = None,
    config_defaults: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    allow_gcloud: bool | None = None,
) -> int:
  """Runs the stdlib argparse AlphaEvolve CLI and returns the exit code.

  Args:
    argv: Command-line arguments (defaults to ``sys.argv[1:]``).
    mcp_caller: Optional injected MCP tool caller forwarded to
      ``AlphaEvolveClient``.
    config_defaults: Optional environment defaults (e.g. ``project``,
      ``location``, ``engine``) layered above built-in defaults and *below* the
      user's active profile, so ``ae config --engine=...`` takes precedence.
    config_overrides: Optional pinned config overrides (e.g. ``session="-"``,
      ``base_url``) layered *above* the profile and env vars, and below explicit
      CLI flags (``--project``, ``--location``).
    allow_gcloud: Whether ``gcloud`` subprocess calls are permitted. Defaults to
      ``False`` when ``mcp_caller`` is provided and ``True`` otherwise.

  Returns:
    Integer process exit code (0 on success, non-zero on error).
  """
  parser = _build_parser()
  raw_argv = list(sys.argv[1:] if argv is None else argv)
  if not raw_argv:
    parser.print_help()
    return 0

  config_split = _extract_config_invocation(raw_argv)
  if config_split is not None:
    global_tokens, config_tokens = config_split
    try:
      args = parser.parse_args(global_tokens + ["config"])
    except SystemExit as e:
      return int(e.code) if isinstance(e.code, int) else (1 if e.code else 0)
    args.config_args = config_tokens
  else:
    try:
      args = parser.parse_args(raw_argv)
    except SystemExit as e:
      return int(e.code) if isinstance(e.code, int) else (1 if e.code else 0)

  effective_allow_gcloud = (
      (mcp_caller is None) if allow_gcloud is None else allow_gcloud
  )
  state = _SandboxState(
      project=args.project,
      location=args.location,
      json_output=args.json_output,
      compact=args.compact,
      verbose=args.verbose,
      mcp_caller=mcp_caller,
      config_defaults=config_defaults,
      config_overrides=config_overrides,
      allow_gcloud=effective_allow_gcloud,
  )

  try:
    if args.command == "config":
      _dispatch_config(state, args.config_args)
      return 0
    handler = getattr(args, "handler", None)
    if handler is None:
      if not args.command:
        parser.print_help()
      else:
        parser.parse_args([args.command, "--help"])
      return 0
    handler(state, args)
    return 0
  except _CliExitError as e:
    return e.code
  except SystemExit as e:
    return int(e.code) if isinstance(e.code, int) else (1 if e.code else 0)
  except Exception as e:  # pylint: disable=broad-exception-caught
    try:
      state.err(str(e))
    except _CliExitError as exit_exc:
      return exit_exc.code


if __name__ == "__main__":
  sys.exit(main())
