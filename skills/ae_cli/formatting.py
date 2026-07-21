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

"""Rich output formatting for the ae CLI.

Provides consistent formatting across all commands with support for
table, JSON, and compact output modes.
"""

from __future__ import annotations

import datetime
import json
import typing

from rich import console
from rich import panel
from rich import syntax
from rich import table
from rich import text

from . import nicknames

console = console.Console()


# ---------------------------------------------------------------------------
# Time formatting
# ---------------------------------------------------------------------------


def _relative_time(timestamp: str | None) -> str:
  """Formats an ISO timestamp into a human-readable relative time string.

  Args:
    timestamp: The RFC3339 or ISO-8601 timestamp string to convert.

  Returns:
    A formatted string (e.g., '5m ago', 'just now', 'N/A').
  """
  if not timestamp:
    return "—"
  try:
    # Handle ISO format with Z or +00:00.
    ts = timestamp.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(ts)
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
      return "just now"
    if seconds < 60:
      return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
      return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
      return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"
  except (ValueError, TypeError):
    return timestamp or ""


# ---------------------------------------------------------------------------
# Experiment formatting
# ---------------------------------------------------------------------------


def format_experiment_table(
    experiments: list[dict[str, typing.Any]],
    index: nicknames.NicknameIndex,
) -> table.Table:
  """Formats a list of experiments into a Rich Table grid structure.

  Args:
    experiments: A list of dictionaries containing experiment metadata.
    index: A NicknameIndex handle for resolving resource display names.

  Returns:
    A Rich Table object suitable for console rendering directly.
  """
  tbl = table.Table(
      show_header=True,
      header_style="bold cyan",
      title="Experiments",
      title_style="bold",
  )
  tbl.add_column("#", style="dim", width=4)
  tbl.add_column("Nickname", style="bold green")
  tbl.add_column("State", style="yellow")
  tbl.add_column("ID", style="dim")

  for i, exp in enumerate(experiments, 1):
    name = exp.get("name", "")
    nick = index.get_nickname(name)
    raw_state = exp.get("state", "UNKNOWN")
    state = _clean_state(raw_state)
    short_id = nicknames.shorten_name(name)

    state_style = _state_style(raw_state)
    tbl.add_row(
        str(i),
        nick,
        text.Text(state, style=state_style),
        short_id,
    )

  return tbl


def format_model(generation_settings: dict[str, typing.Any]) -> str:
  """Returns a human-readable description of the configured models.

  Renders the structured `models` field: a single model is shown by name; a
  mixture lists each model with its normalized weight, e.g.
  `gemini-2.5-flash (90%), gemini-2.5-pro (10%)`. The deprecated `model` field
  is intentionally ignored.

  Args:
    generation_settings: The `generationSettings` mapping from an experiment
      config.

  Returns:
    A display string, or an empty string when no models are present.
  """
  models = generation_settings.get("models") or []
  if not models:
    return ""
  if len(models) == 1:
    return str(models[0].get("name", ""))
  # Weights are relative, so normalize them to percentages for display. The
  # `or 1.0` guards against a zero total (avoids division by zero).
  total_weight = sum(model.get("weight", 1.0) for model in models) or 1.0
  parts = []
  for model in models:
    share = round(100 * model.get("weight", 1.0) / total_weight)
    parts.append(f"{model.get('name', '')} ({share}%)")
  return ", ".join(parts)


def format_experiment_detail(
    exp: dict[str, typing.Any],
    index: nicknames.NicknameIndex,
) -> panel.Panel:
  """Formats a single experiment into a detailed Rich Panel view structure.

  Args:
    exp: A dictionary containing a single experiment resource details.
    index: A NicknameIndex handle for resolving resource display aliases.

  Returns:
    A Rich Panel object representing the dashboard display summary view.
  """
  name = exp.get("name", "")
  nick = index.get_nickname(name)
  raw_state = exp.get("state", "UNKNOWN")
  state = _clean_state(raw_state)
  config = exp.get("config", {})

  lines = [
      f"[bold]Nickname:[/bold]  {nick}",
      f"[bold]Name:[/bold]      {name}",
      (
          "[bold]State:[/bold]    "
          f" [{_state_style(raw_state)}]{state}[/{_state_style(raw_state)}]"
      ),
      f"[bold]Created:[/bold]   {_relative_time(exp.get('createTime'))}",
  ]

  if config:
    lines.append("")
    lines.append("[bold]Configuration:[/bold]")
    if config.get("title"):
      lines.append(f"  Title: {config['title']}")
    if config.get("problemDescription"):
      lines.append(f"  Problem: {config['problemDescription'][:200]}")
    if config.get("programLanguage"):
      lines.append(f"  Language: {config['programLanguage']}")
    model = format_model(config.get("generationSettings", {}))
    if model:
      lines.append(f"  Model: {model}")

  stats = exp.get("stats", {})
  if stats:
    lines.append("")
    lines.append("[bold]Stats:[/bold]")
    for k, v in stats.items():
      lines.append(f"  {k}: {v}")

  return panel.Panel(
      "\n".join(lines),
      title=f"[bold]{nick}[/bold]",
      border_style="cyan",
  )


# ---------------------------------------------------------------------------
# Program formatting
# ---------------------------------------------------------------------------


def format_program_table(
    programs: list[dict[str, typing.Any]],
    index: nicknames.NicknameIndex,
) -> table.Table:
  """Formats a list of programs into a Rich Table grid structure.

  Args:
    programs: A list of dictionaries containing program metadata.
    index: A NicknameIndex handle for resolving resource display names.

  Returns:
    A Rich Table object suitable for console rendering directly.
  """
  tbl = table.Table(
      show_header=True,
      header_style="bold cyan",
      title="Programs",
      title_style="bold",
  )
  tbl.add_column("#", style="dim", width=4)
  tbl.add_column("Nickname", style="bold green")
  tbl.add_column("Score", style="magenta", justify="right")
  tbl.add_column("State", style="yellow")
  tbl.add_column("Created", style="dim")
  tbl.add_column("ID", style="dim")

  for i, prog in enumerate(programs, 1):
    name = prog.get("name", "")
    nick = index.get_nickname(name)
    raw_state = prog.get("state", "UNKNOWN")
    state = _clean_state(raw_state)
    created = _relative_time(prog.get("createTime"))
    short_id = nicknames.shorten_name(name)
    score = _extract_best_score(prog)

    state_style = _state_style(raw_state)
    tbl.add_row(
        str(i),
        nick,
        score,
        text.Text(state, style=state_style),
        created,
        short_id,
    )

  return tbl


def format_program_detail(
    prog: dict[str, typing.Any],
    index: nicknames.NicknameIndex,
) -> panel.Panel:
  """Formats a single program into a detailed panel with source code.

  Args:
    prog: A dictionary containing a single program resource details.
    index: A NicknameIndex handle for resolving resource names aliases.

  Returns:
    A Rich Panel object representing the dashboard display summary view.
  """
  name = prog.get("name", "")
  nick = index.get_nickname(name)
  raw_state = prog.get("state", "UNKNOWN")
  state = _clean_state(raw_state)

  lines = [
      f"[bold]Nickname:[/bold]  {nick}",
      f"[bold]Name:[/bold]      {name}",
      (
          "[bold]State:[/bold]    "
          f" [{_state_style(raw_state)}]{state}[/{_state_style(raw_state)}]"
      ),
      f"[bold]Created:[/bold]   {_relative_time(prog.get('createTime'))}",
      f"[bold]Score:[/bold]     {_extract_best_score(prog)}",
  ]

  # Parent programs.
  parents = prog.get("parentPrograms", [])
  if parents:
    parent_labels = []
    for p in parents:
      if "/" in p:
        # Full resource name — resolve to a nickname.
        parent_labels.append(index.get_nickname(p))
      else:
        # Short index (e.g. "1") — API returns these instead of full
        # resource names. Display as-is rather than generating a fake
        # nickname from a non-resource string.
        parent_labels.append(f"program #{p}")
    lines.append(f"[bold]Parents:[/bold]   {', '.join(parent_labels)}")

  # Evaluation insights.
  eval_data = prog.get("evaluation", {})
  insights = eval_data.get("insights", {}).get("insights", [])
  if insights:
    lines.append("")
    lines.append("[bold]Insights:[/bold]")
    for insight in insights:
      label = insight.get("label", "")
      insight_text = insight.get("text", "")
      lines.append(f"  [{label}] {insight_text}")

  return panel.Panel(
      "\n".join(lines),
      title=f"[bold]{nick}[/bold]",
      border_style="cyan",
  )


def format_program_code(prog: dict[str, typing.Any]) -> list[syntax.Syntax]:
  """Extracts and syntax-highlights program source code files payload.

  Args:
    prog: A dictionary containing the program resource details.

  Returns:
    A list array containing Rich Syntax objects representing highlighted blocks.
  """
  content = prog.get("content", {})
  files = content.get("files", [])
  result = []
  for f in files:
    code = f.get("content", "")
    lang = f.get("programLanguage", "python")
    result.append(
        syntax.Syntax(
            code, lang, theme="monokai", line_numbers=True, word_wrap=True
        )
    )
  return result


# ---------------------------------------------------------------------------
# Engine formatting
# ---------------------------------------------------------------------------


def format_engine_table(
    engines: list[dict[str, typing.Any]],
    active_engine: str = "",
) -> table.Table:
  """Formats a list of engines into a Rich Table.

  Args:
    engines: A list of dictionaries containing engine metadata.
    active_engine: The engine ID currently configured, used to mark the active
      row.

  Returns:
    A Rich Table object suitable for console rendering.
  """
  tbl = table.Table(
      show_header=True,
      header_style="bold cyan",
      title="Engines",
      title_style="bold",
  )
  tbl.add_column("Engine ID", style="bold green")
  tbl.add_column("Solution Type")
  tbl.add_column("Active", style="dim")
  for eng in engines:
    name = eng.get("name", "unknown")
    eng_id = name.split("/")[-1]
    sol_type = eng.get("solutionType", "unknown").replace("SOLUTION_TYPE_", "")
    is_active = "✓" if eng_id == active_engine else ""
    tbl.add_row(eng_id, sol_type, is_active)
  return tbl


# ---------------------------------------------------------------------------
# Diff formatting
# ---------------------------------------------------------------------------


def format_diff(
    old_content: str,
    new_content: str,
    from_file: str = "parent",
    to_file: str = "current",
) -> syntax.Syntax:
  """Formats a unified diff with Rich syntax highlighting.

  Args:
    old_content: The source string content to compare from.
    new_content: The target string content to compare against.
    from_file: Label identifier for the old content stream buffer.
    to_file: Label identifier for the new content stream buffer.

  Returns:
    A Rich Syntax object representing the highlighted unified diff.
  """
  import difflib  # pylint: disable=g-import-not-at-top

  diff_lines = difflib.unified_diff(
      old_content.splitlines(keepends=True),
      new_content.splitlines(keepends=True),
      fromfile=from_file,
      tofile=to_file,
  )
  diff_text = "".join(diff_lines)
  return syntax.Syntax(diff_text, "diff", theme="monokai", word_wrap=True)


# ---------------------------------------------------------------------------
# Error formatting
# ---------------------------------------------------------------------------


def format_error(
    status_code: int,
    message: str,
    details: typing.Any = None,
) -> panel.Panel:
  """Formats an API error as a detailed Rich panel.

  Args:
    status_code: The HTTP status numeric code wrapper accurately.
    message: The operational description payload string accurately.
    details: Optional structured dict committing debug payloads correctly.

  Returns:
    A Rich Panel describing formatted output errors correctly triggers.
  """
  lines = [
      f"[bold red]Status:[/bold red] {status_code}",
      f"[bold red]Message:[/bold red] {message}",
  ]
  if details:
    lines.append(f"[dim]{json.dumps(details, indent=2)}[/dim]")

  # Add hints for common errors.
  hints = {
      401: (
          "Check your credentials: run [bold]gcloud auth application-default"
          " login[/bold]"
      ),
      403: "Check project permissions and API enablement.",
      404: "Resource not found. Verify the experiment/program name.",
      429: "Rate limited. Wait a moment and retry.",
      503: "Service temporarily unavailable. Retry shortly.",
  }
  hint = hints.get(status_code)
  if hint:
    lines.append(f"\n[yellow]Hint:[/yellow] {hint}")

  return panel.Panel(
      "\n".join(lines),
      title="[bold red]API Error[/bold red]",
      border_style="red",
  )


# ---------------------------------------------------------------------------
# JSON output helpers
# ---------------------------------------------------------------------------


def to_json(
    data: typing.Any,
    nickname_field: str | None = None,
    index: nicknames.NicknameIndex | None = None,
) -> str:
  """Converts data structures to JSON, optionally enriching with nicknames.

  Args:
    data: The payload object (list or dict) to serialize correctly.
    nickname_field: Optional dictionary key for injection triggers correctly.
    index: A NicknameIndex handles resolving aliases answers safely.

  Returns:
    A string JSON serializable triggers buffers descriptive state correctly.
  """

  def _enrich(item: typing.Any, idx: nicknames.NicknameIndex) -> None:
    if isinstance(item, list):
      for x in item:
        _enrich(x, idx)
    elif isinstance(item, dict):
      name = item.get("name", "")
      if name and nickname_field and nickname_field not in item:
        item[nickname_field] = idx.get_nickname(name)
      for v in item.values():
        _enrich(v, idx)

  if index and nickname_field:
    _enrich(data, index)

  return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_best_score(prog: dict[str, typing.Any]) -> str:
  """Extracts the best score string from a program's evaluation records.

  Args:
    prog: A dictionary containing program resource details metadata.

  Returns:
    A string representing the best performers score value alias wrapper.
  """
  eval_data = prog.get("evaluation", {})
  scores = eval_data.get("scores", {}).get("scores", [])
  if not scores:
    return "—"
  # Take first score metric.
  best = scores[0]
  metric = best.get("metric", "")
  score = best.get("score", "")
  if metric:
    return f"{score} ({metric})"
  return str(score)


def clean_state(state: str) -> str:
  """Strips proto enum prefixes from a state string for display.

  Args:
    state: The raw state string (e.g. 'EXPERIMENT_STATE_COMPLETED').

  Returns:
    A cleaned string without the enum prefix (e.g. 'COMPLETED').
  """
  return _clean_state(state)


def _clean_state(state: str) -> str:
  """Strips proto enum prefixes from state string for display view structures.

  Args:
    state: The raw state string committed triggers correctly buffers.

  Returns:
    A cleaned string alias descriptive triggers accurately buffers triggers.
  """
  for prefix in ("PROGRAM_STATE_", "EXPERIMENT_STATE_"):
    if state.startswith(prefix):
      state = state[len(prefix) :]
      break
  if state in ("UNSPECIFIED", "UNKNOWN"):
    return "—"
  return state


def _state_style(state: str) -> str:
  """Returns a Rich style string identifier for a given state name.

  Args:
    state: The raw state string identifier buffers accurate triggers.

  Returns:
    A Rich style string targets colors descriptive state directly.
  """
  cleaned = _clean_state(state)
  styles = {
      "ACTIVE": "green",
      "COMPLETED": "green",
      "INITIALIZED": "blue",
      "GENERATING": "yellow",
      "EVALUATING": "yellow",
      "PAUSED": "dim yellow",
      "SUCCEEDED": "green bold",
      "FAILED": "red",
      "CANCELLED": "dim red",
      "—": "dim",
  }
  return styles.get(cleaned, "white")
