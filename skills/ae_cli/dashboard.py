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

"""Markdown dashboard generator for AlphaEvolve experiments.

Writes a self-updating markdown file with experiment progress, score chart,
and leaderboard. Designed to be used as a persistent artifact that agents
can show to users.
"""

from __future__ import annotations

import datetime
import pathlib
from typing import Any


# Width of the ASCII bar chart in characters.
_CHART_WIDTH = 40

# Maximum number of entries in the score history chart.
_MAX_CHART_ENTRIES = 30


def _ascii_bar(value: float, min_val: float, max_val: float) -> str:
  """Renders a single ASCII bar for a chart value."""
  if max_val == min_val:
    width = _CHART_WIDTH
  else:
    fraction = (value - min_val) / (max_val - min_val)
    width = max(1, int(fraction * _CHART_WIDTH))
  return "\u2588" * width


def _format_score_chart(
    scores: list[tuple[int, float]],
) -> str:
  """Renders an ASCII bar chart of score progression.

  Args:
    scores: List of (evaluation_number, score) tuples in chronological order.

  Returns:
    A multi-line string with the ASCII chart.
  """
  if not scores:
    return "_No scores recorded yet._"

  # Trim to last N entries.
  display = scores[-_MAX_CHART_ENTRIES:]
  all_scores = [s for _, s in display]
  min_s = min(all_scores)
  max_s = max(all_scores)

  lines = []
  lines.append("```")
  for eval_num, score in display:
    bar = _ascii_bar(score, min_s, max_s)
    lines.append(f"  {eval_num:>4d} | {bar} {score:.6f}")
  lines.append("```")
  lines.append(f"  _Range: [{min_s:.6f}, {max_s:.6f}]_")
  return "\n".join(lines)


def generate_dashboard(
    nickname: str,
    state: str,
    total_evaluated: int,
    total_succeeded: int,
    total_failed: int,
    best_score: float | None,
    best_nickname: str | None,
    score_history: list[tuple[int, float]],
    leaderboard: list[dict[str, Any]],
) -> str:
  """Generates a markdown dashboard string.

  Args:
    nickname: Experiment nickname.
    state: Current experiment state.
    total_evaluated: Total programs evaluated.
    total_succeeded: Successful evaluations.
    total_failed: Failed evaluations.
    best_score: Best score so far.
    best_nickname: Nickname of the best program.
    score_history: List of (eval_number, score) for the chart.
    leaderboard: List of dicts with nickname and score keys.

  Returns:
    A complete markdown dashboard string.
  """
  now = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC")

  lines = []
  lines.append(f"# Experiment: {nickname}")
  lines.append("")
  lines.append(f"_Last updated: {now}_")
  lines.append("")

  # Status bar
  state_emoji = {
      "RUNNING": "running",
      "ACTIVE": "running",
      "COMPLETED": "completed",
      "FAILED": "failed",
      "CANCELLED": "cancelled",
      "PAUSED": "paused",
  }
  status = state_emoji.get(state, state)
  lines.append(
      f"**Status:** {status} | **Evaluated:** {total_evaluated}"
      f" | **Succeeded:** {total_succeeded}"
      f" | **Failed:** {total_failed}"
  )
  lines.append("")

  # Best score
  if best_score is not None:
    lines.append(
        f"**Best score:** {best_score:.6f} ({best_nickname or 'unknown'})"
    )
  else:
    lines.append("**Best score:** _none yet_")
  lines.append("")

  # Score progression chart
  lines.append("## Score Progression")
  lines.append("")
  lines.append(_format_score_chart(score_history))
  lines.append("")

  # Leaderboard
  if leaderboard:
    lines.append("## Leaderboard")
    lines.append("")
    lines.append("| Rank | Nickname | Score |")
    lines.append("|------|----------|-------|")
    for i, entry in enumerate(leaderboard[:10], 1):
      nick = entry.get("nickname", "?")
      score = entry.get("score", 0.0)
      lines.append(f"| {i} | {nick} | {score:.6f} |")
    lines.append("")

  return "\n".join(lines)


def write_dashboard(
    path: pathlib.Path,
    nickname: str,
    state: str,
    total_evaluated: int,
    total_succeeded: int,
    total_failed: int,
    best_score: float | None,
    best_nickname: str | None,
    score_history: list[tuple[int, float]],
    leaderboard: list[dict[str, Any]],
) -> None:
  """Generates and writes the dashboard markdown file.

  Overwrites the file on each call so it always reflects current state.

  Args:
    path: Path to write the dashboard markdown file.
    nickname: Experiment nickname.
    state: Current experiment state.
    total_evaluated: Total programs evaluated.
    total_succeeded: Successful evaluations.
    total_failed: Failed evaluations.
    best_score: Best score so far.
    best_nickname: Nickname of the best program.
    score_history: List of (eval_number, score) for the chart.
    leaderboard: List of dicts with nickname and score keys.
  """
  content = generate_dashboard(
      nickname=nickname,
      state=state,
      total_evaluated=total_evaluated,
      total_succeeded=total_succeeded,
      total_failed=total_failed,
      best_score=best_score,
      best_nickname=best_nickname,
      score_history=score_history,
      leaderboard=leaderboard,
  )
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")
