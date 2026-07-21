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

"""Visualization utilities for AlphaEvolve experiment results.

Generates matplotlib score progression charts (PNG) and self-contained
interactive HTML reports from experiment program data.
"""

from __future__ import annotations

import collections.abc
import datetime
import html as html_module
import json
import pathlib
import re
from typing import Any

import markdown as markdown_lib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # pylint: disable=g-import-not-at-top
import pygments
import pygments.formatters.html
import pygments.lexers.python

# Type alias for the optional nickname resolution callback.
NicknameFn = collections.abc.Callable[[str], str] | None
# ---------------------------------------------------------------------------
# Markdown & syntax highlighting helpers
# ---------------------------------------------------------------------------


def _render_markdown(text: str) -> str:
  """Converts markdown text to HTML with syntax-highlighted code blocks."""
  md = markdown_lib.Markdown(
      extensions=[
          "fenced_code",
          "tables",
          "codehilite",
      ],
      extension_configs={
          "codehilite": {
              "css_class": "codehilite",
              "guess_lang": True,
              "noclasses": False,
          },
      },
  )
  return md.convert(text)


def _highlight_python(code: str) -> str:
  """Syntax-highlights Python code, returning an HTML string."""
  lexer = pygments.lexers.python.PythonLexer()
  formatter = pygments.formatters.html.HtmlFormatter(
      nowrap=True,
      cssclass="codehilite",
  )
  return pygments.highlight(code, lexer, formatter)


def _pygments_css() -> str:
  """Returns Pygments CSS rules for the dark theme (matching #282c34)."""
  # Generate base Pygments CSS using the monokai style, then override
  # the background to match our existing dark code block style.
  formatter = pygments.formatters.html.HtmlFormatter(
      style="monokai",
      cssclass="codehilite",
  )
  css = formatter.get_style_defs(".codehilite")
  # Override background and text color to match existing theme.
  css += """
.codehilite { background: #282c34; color: #abb2bf; padding: 16px;
  border-radius: 6px; overflow-x: auto; font-size: 0.85em;
  line-height: 1.5; margin: 8px 0; }
.codehilite pre { background: transparent; color: inherit; padding: 0;
  margin: 0; border-radius: 0; }
.codehilite code { background: transparent; color: inherit; }
"""
  return css


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

# Sentinel score used by the controller for failed evaluations.
_FAILURE_SCORE = -(10**12)


def _extract_score(program: dict[str, Any]) -> float | None:
  """Extracts the primary score from a program dict, or None if failed."""
  eval_data = program.get("evaluation", {})
  if not isinstance(eval_data, dict):
    return None
  scores_obj = eval_data.get("scores")
  if not isinstance(scores_obj, dict):
    return None
  scores_list = scores_obj.get("scores", [])
  if not isinstance(scores_list, list) or not scores_list:
    return None
  score = scores_list[0].get("score")
  if score is None:
    return None
  try:
    score = float(score)
  except (ValueError, TypeError):
    return None
  if score <= _FAILURE_SCORE:
    return None
  return score


def _extract_evolve_block(content: str) -> str | None:
  """Extracts code between EVOLVE-BLOCK markers, or None if not found."""
  lines = content.split("\n")
  in_block = False
  block_lines = []
  for line in lines:
    if "EVOLVE-BLOCK-START" in line:
      in_block = True
      continue
    if "EVOLVE-BLOCK-END" in line:
      in_block = False
      continue
    if in_block:
      block_lines.append(line)
  return "\n".join(block_lines) if block_lines else None


def _extract_code_snippet(
    program: dict[str, Any],
    max_lines: int = 30,
    evolve_block_only: bool = False,
) -> str:
  """Extracts source code from a program.

  Args:
    program: Program dict with content.files[].content.
    max_lines: Max lines to return.
    evolve_block_only: If True, extract only the EVOLVE-BLOCK content. Falls
      back to full code if no markers are found.

  Returns:
    Source code string, possibly truncated.
  """
  files = program.get("content", {}).get("files", [])
  if not files:
    return ""
  content = files[0].get("content", "")
  if not content:
    return ""

  if evolve_block_only:
    block = _extract_evolve_block(content)
    if block is not None:
      content = block

  all_lines = content.split("\n")
  lines = all_lines[:max_lines]
  if len(all_lines) > max_lines:
    lines.append(f"... ({len(all_lines) - max_lines} more lines)")
  return "\n".join(lines)


def prepare_chart_data(
    programs: list[dict[str, Any]],
    nickname_fn: NicknameFn = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[tuple[int, float, str, bool]],
]:
  """Prepares chart data from a list of program dicts.

  Programs are sorted by createTime internally to ensure consistent
  chart ordering regardless of the input order.

  Args:
    programs: List of program dicts (any order).
    nickname_fn: Optional callable(resource_name) -> nickname string.

  Returns:
    Tuple of (successful_points, failed_points, running_best) where:
      - successful_points: [{index, nickname, score}]
      - failed_points: [{index, nickname}]
      - running_best: [(index, best_score, nickname, is_new_high)]
  """
  # Defensive sort by createTime so chart order is deterministic.
  sorted_programs = sorted(programs, key=lambda p: p.get("createTime", ""))

  successful = []
  failed = []
  running_best = []
  best_so_far = float("-inf")

  for i, prog in enumerate(sorted_programs):
    name = prog.get("name", "")
    nickname = prog.get("nickname", "")
    if not nickname and nickname_fn and name:
      nickname = nickname_fn(name)
    if not nickname:
      nickname = f"prog-{i}"

    score = _extract_score(prog)
    if score is not None:
      is_new_high = score > best_so_far
      successful.append({"index": i, "nickname": nickname, "score": score})
      if is_new_high:
        best_so_far = score
      running_best.append((i, best_so_far, nickname, is_new_high))
    else:
      failed.append({"index": i, "nickname": nickname})

  return successful, failed, running_best


# ---------------------------------------------------------------------------
# Matplotlib chart
# ---------------------------------------------------------------------------


def _compute_ylim(
    scores: list[float],
    baseline: float,
) -> tuple[float, float]:
  """Computes y-axis limits that are robust to outlier low scores.

  Uses the interquartile range (IQR) to determine the visible range.
  Scores below Q1 - 1.5*IQR are treated as outliers and excluded from
  the limits, preventing a few bad evaluations from distorting the chart.

  Args:
    scores: All successful scores.
    baseline: The baseline (first program) score.

  Returns:
    (y_min, y_max) tuple for the axis limits.
  """
  if not scores:
    return (0.0, 1.0)
  if len(scores) == 1:
    margin = abs(scores[0]) * 0.1 or 0.5
    return (scores[0] - margin, scores[0] + margin)

  sorted_s = sorted(scores)
  q1 = sorted_s[len(sorted_s) // 4]
  q3 = sorted_s[(3 * len(sorted_s)) // 4]
  iqr = q3 - q1

  # Lower fence: at most Q1 - 1.5*IQR, but always include the baseline.
  lower_fence = q1 - 1.5 * iqr
  visible_min = min(s for s in sorted_s if s >= lower_fence)
  visible_min = min(visible_min, baseline)

  visible_max = sorted_s[-1]

  score_range = visible_max - visible_min
  margin = (
      score_range * 0.08 if score_range > 0 else abs(visible_max) * 0.1 or 0.5
  )

  return (visible_min - margin, visible_max + margin)


def generate_plot(
    programs: list[dict[str, Any]],
    output_path: pathlib.Path,
    title: str = "Score Progression",
    nickname_fn: NicknameFn = None,
) -> None:
  """Generates a scatter + running-best line chart as a PNG.

  Programs are sorted by createTime internally. Each new high score on
  the running-best line is annotated with the program nickname and score.

  Args:
    programs: List of program dicts (any order -- sorted internally).
    output_path: Path to write the PNG file.
    title: Chart title.
    nickname_fn: Optional callable(resource_name) -> nickname string.
  """
  successful, failed, running_best = prepare_chart_data(programs, nickname_fn)

  if not successful:
    # Create a minimal "no data" chart.
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.text(
        0.5,
        0.5,
        "No successful evaluations",
        ha="center",
        va="center",
        fontsize=14,
        color="#999",
        transform=ax.transAxes,
    )
    ax.set_title(title, fontsize=13, fontweight="bold")
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return

  fig, ax = plt.subplots(figsize=(12, 6))

  scores = [p["score"] for p in successful]
  indices = [p["index"] for p in successful]
  initial_score = _find_initial_score(programs)
  baseline = (
      initial_score if initial_score is not None else successful[0]["score"]
  )

  # Compute robust y-axis limits (outlier-resistant).
  y_min, y_max = _compute_ylim(scores, baseline)
  ax.set_ylim(y_min, y_max)

  # Failed evaluations as grey X markers at the bottom.
  if failed:
    fail_x = [p["index"] for p in failed]
    fail_y_val = y_min + (y_max - y_min) * 0.02
    ax.scatter(
        fail_x,
        [fail_y_val] * len(fail_x),
        color="#cccccc",
        marker="x",
        s=30,
        alpha=0.5,
        label=f"Failed ({len(failed)})",
        zorder=2,
    )

  # All successful evaluations as scatter points.
  ax.scatter(
      indices,
      scores,
      color="#6495ED",
      alpha=0.6,
      s=25,
      edgecolors="white",
      linewidth=0.5,
      label=f"Evaluations ({len(successful)})",
      zorder=3,
  )

  # Running best as a green step line.
  best_x = [r[0] for r in running_best]
  best_y = [r[1] for r in running_best]
  ax.step(
      best_x,
      best_y,
      where="post",
      color="#2ecc71",
      linewidth=2.5,
      label="Best score",
      zorder=4,
  )

  # Annotate every new high point with a star, name and score.
  # Annotations are placed to the left of the point.
  new_highs = [
      (idx, score, nick) for idx, score, nick, is_new in running_best if is_new
  ]
  for i, (idx, score, nick) in enumerate(new_highs):
    ax.scatter(
        [idx],
        [score],
        color="#2ecc71",
        s=80 if i < len(new_highs) - 1 else 120,
        edgecolors="white",
        linewidth=1.5,
        marker="*",
        zorder=5,
    )
    # Label to the LEFT of the point so the arrow always points
    # left-to-right (from label toward the data point).
    ax.annotate(
        f"{nick}: {score:.4f}",
        xy=(idx, score),
        xytext=(-10, 18),
        textcoords="offset points",
        fontsize=7,
        color="#2ecc71",
        fontweight="bold",
        ha="right",
        arrowprops=dict(arrowstyle="->", color="#2ecc71", lw=0.8),
    )

  # Baseline reference line.
  ax.axhline(
      y=baseline,
      color="#e74c3c",
      linestyle="--",
      alpha=0.5,
      linewidth=1,
      label=f"Baseline ({baseline:.4f})",
  )

  # Formatting.
  ax.set_xlabel("Evaluation #", fontsize=11)
  ax.set_ylabel("Score", fontsize=11)
  ax.set_title(title, fontsize=13, fontweight="bold")
  ax.legend(loc="lower right", fontsize=9, framealpha=0.9)
  ax.grid(True, alpha=0.3, linestyle="-")
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)

  fig.tight_layout()
  fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
  plt.close(fig)


# ---------------------------------------------------------------------------
# Interactive HTML report
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AlphaEvolve Report: {nickname}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    background: #fafafa; color: #333; line-height: 1.6;
  }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 1.8em; margin-bottom: 4px; }}
  h2 {{ font-size: 1.3em; margin: 32px 0 12px;
       border-bottom: 2px solid #e0e0e0; padding-bottom: 6px; }}
  h3 {{ font-size: 1.1em; margin: 20px 0 8px; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 24px; }}
  .result-banner {{
    background: #f0f9f0; border-left: 4px solid #2ecc71;
    padding: 16px 20px; margin: 16px 0; font-size: 1.2em;
  }}
  .result-banner .score {{ font-weight: bold; color: #2ecc71; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left;
           font-size: 0.9em; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  pre {{ background: #282c34; color: #abb2bf; padding: 16px;
        border-radius: 6px; overflow-x: auto; font-size: 0.85em;
        line-height: 1.5; margin: 8px 0; }}
  code {{ font-family: "SF Mono", "Fira Code", Consolas, monospace; }}
  {pygments_css}
  .chart-container {{
    position: relative; background: white; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 20px; margin: 16px 0;
  }}
  canvas {{ display: block; margin: 0 auto; }}
  .tooltip {{
    display: none; position: absolute; background: #282c34; color: #abb2bf;
    border-radius: 6px; padding: 12px 16px; font-size: 0.8em;
    max-width: 450px; z-index: 10; pointer-events: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  }}
  .tooltip .name {{ color: #61afef; font-weight: bold; }}
  .tooltip .score-val {{ color: #98c379; }}
  .tooltip pre {{ padding: 8px; margin-top: 8px; font-size: 0.8em;
                 max-height: 200px; overflow-y: auto; }}
  .markdown-body {{ margin-top: 32px; }}
  .markdown-body h1 {{ font-size: 1.6em; margin: 24px 0 8px; }}
  .markdown-body h2 {{ font-size: 1.3em; margin: 24px 0 8px;
                       border-bottom: 2px solid #e0e0e0;
                       padding-bottom: 6px; }}
  .markdown-body p {{ margin: 8px 0; }}
  #selected-program {{
    display: none; background: white; border: 2px solid #2ecc71;
    border-radius: 8px; padding: 20px; margin: 16px 0;
  }}
  #selected-program.visible {{ display: block; }}
  #selected-program .header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 12px;
  }}
  #selected-program .header h3 {{ margin: 0; color: #2ecc71; }}
  #selected-program .close-btn {{
    background: none; border: 1px solid #ccc; border-radius: 4px;
    padding: 4px 12px; cursor: pointer; color: #666; font-size: 0.85em;
  }}
  #selected-program .close-btn:hover {{ background: #f5f5f5; }}
  #selected-program .program-meta {{
    display: flex; gap: 24px; margin-bottom: 12px; font-size: 0.9em;
    color: #666;
  }}
  #selected-program .program-meta strong {{ color: #333; }}
  #selected-program pre {{
    max-height: 600px; overflow-y: auto;
  }}
  canvas {{ cursor: default; }}
</style>
</head>
<body>
<div class="container">

<h1>AlphaEvolve Report: {nickname}</h1>
<div class="meta">{date} &nbsp;|&nbsp; {model} &nbsp;|&nbsp; {duration}</div>

<div class="result-banner">
  {baseline:.4f} &rarr; <span class="score">{best:.4f}</span>
  &nbsp;(+{improvement:.1f}%)
</div>

<h2>Score Progression</h2>
<p style="margin:0 0 12px;font-size:0.88em;color:#666;line-height:1.5;">
  Each point represents one evaluated program.
  <span style="color:#2980b9;font-weight:600;"> Highlighted points</span>
  are the top 15 programs by score &mdash; hover for a preview, click to
  view the full evolved code.
  <span style="color:#bbb;"> Faded points</span> are remaining
  evaluations.
  The <span style="color:#2ecc71;font-weight:600;">green line</span>
  tracks the running best score and the
  <span style="color:#e74c3c;">dashed red line</span> marks the baseline.
</p>
<div class="chart-container">
  <canvas id="chart" width="900" height="400"></canvas>
  <div class="tooltip" id="tooltip"></div>
</div>

<p style="margin:8px 0 16px;font-size:0.85em;color:#888;text-align:center;">
  {chart_note}
</p>

<div id="selected-program">
  <div class="header">
    <h3 id="sel-title">Program</h3>
    <button class="close-btn" onclick="closeSelected()">Close</button>
  </div>
  <div class="program-meta">
    <span>Score: <strong id="sel-score"></strong></span>
    <span>Evaluation: <strong id="sel-eval"></strong></span>
    <span>Rank: <strong id="sel-rank"></strong></span>
  </div>
  <div id="sel-code-container" class="codehilite"
       style="max-height:600px;overflow-y:auto;"></div>
</div>

<div class="markdown-body">
{report_html}
</div>

</div>

<script>
const DATA = {chart_data_json};
const CODE_SNIPPETS = {code_snippets_json};
const FULL_CODE_HTML = {full_code_html_json};
const BASELINE_SCORE = {baseline};

const selPanel = document.getElementById("selected-program");
const selTitle = document.getElementById("sel-title");
const selScore = document.getElementById("sel-score");
const selEval = document.getElementById("sel-eval");
const selRank = document.getElementById("sel-rank");
const selCodeContainer = document.getElementById("sel-code-container");

function closeSelected() {{
  selPanel.classList.remove("visible");
}}

function showProgram(nickname, score, idx) {{
  selTitle.textContent = nickname;
  selScore.textContent = score.toFixed(6);
  selEval.textContent = "#" + idx;
  const ranked = DATA.filter(d => d.score !== null)
    .sort((a, b) => b.score - a.score);
  const rank = ranked.findIndex(d => d.nickname === nickname) + 1;
  selRank.textContent = rank > 0 ? "#" + rank + " of " + ranked.length : "N/A";

  const highlighted = FULL_CODE_HTML[nickname];
  if (highlighted) {{
    selCodeContainer.innerHTML = "<pre>" + highlighted + "</pre>";
  }} else {{
    selCodeContainer.innerHTML =
      "<p style='color:#888;padding:12px;'>Code not available.</p>";
  }}
  selPanel.classList.add("visible");
  selPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
}}

const canvas = document.getElementById("chart");
const ctx = canvas.getContext("2d");
const tooltip = document.getElementById("tooltip");
const W = canvas.width, H = canvas.height;
const PAD = {{top: 30, right: 30, bottom: 50, left: 70}};
const plotW = W - PAD.left - PAD.right;
const plotH = H - PAD.top - PAD.bottom;

const successful = DATA.filter(d => d.score !== null);
const failed = DATA.filter(d => d.score === null);

if (successful.length === 0) {{
  ctx.fillStyle = "#999";
  ctx.font = "14px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("No successful evaluations", W/2, H/2);
}} else {{
  const scores = successful.map(d => d.score);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const scoreRange = maxScore - minScore || 1;
  const maxIdx = Math.max(...DATA.map(d => d.index));

  function toX(idx) {{ return PAD.left + (idx / (maxIdx || 1)) * plotW; }}
  function toY(score) {{
    return PAD.top + plotH - ((score - minScore + scoreRange*0.05)
      / (scoreRange * 1.1)) * plotH;
  }}

  ctx.strokeStyle = "#e8e8e8"; ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {{
    const y = PAD.top + (plotH / 5) * i;
    ctx.beginPath(); ctx.moveTo(PAD.left, y);
    ctx.lineTo(W - PAD.right, y); ctx.stroke();
  }}

  ctx.strokeStyle = "#ccc"; ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(PAD.left, PAD.top);
  ctx.lineTo(PAD.left, H - PAD.bottom);
  ctx.lineTo(W - PAD.right, H - PAD.bottom);
  ctx.stroke();

  ctx.fillStyle = "#666"; ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  for (let i = 0; i <= 5; i++) {{
    const idx = Math.round((maxIdx / 5) * i);
    ctx.fillText(idx, toX(idx), H - PAD.bottom + 20);
  }}
  ctx.fillText("Evaluation #", W/2, H - 8);

  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let i = 0; i <= 5; i++) {{
    const score = minScore - scoreRange*0.05
      + (scoreRange * 1.1 / 5) * (5 - i);
    const y = PAD.top + (plotH / 5) * i;
    ctx.fillText(score.toFixed(3), PAD.left - 8, y);
  }}
  ctx.save(); ctx.translate(14, H/2); ctx.rotate(-Math.PI/2);
  ctx.textAlign = "center"; ctx.fillText("Score", 0, 0); ctx.restore();

  const baseline = BASELINE_SCORE;
  ctx.strokeStyle = "#e74c3c"; ctx.lineWidth = 1;
  ctx.setLineDash([6, 4]);
  ctx.beginPath(); ctx.moveTo(PAD.left, toY(baseline));
  ctx.lineTo(W - PAD.right, toY(baseline)); ctx.stroke();
  ctx.setLineDash([]);

  ctx.strokeStyle = "#2ecc71"; ctx.lineWidth = 2.5;
  ctx.beginPath();
  let best = -Infinity, started = false;
  for (const d of DATA) {{
    if (d.score !== null && d.score > best) best = d.score;
    if (best > -Infinity) {{
      const x = toX(d.index), y = toY(best);
      if (!started) {{ ctx.moveTo(x, y); started = true; }}
      else ctx.lineTo(x, y);
    }}
  }}
  ctx.stroke();

  if (failed.length > 0) {{
    const failY = toY(minScore - scoreRange * 0.03);
    ctx.strokeStyle = "#ccc"; ctx.lineWidth = 1.5;
    for (const d of failed) {{
      const x = toX(d.index);
      ctx.beginPath(); ctx.moveTo(x-4, failY-4);
      ctx.lineTo(x+4, failY+4); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x+4, failY-4);
      ctx.lineTo(x-4, failY+4); ctx.stroke();
    }}
  }}

  const pointPositions = [];
  for (const d of successful) {{
    const hasCode = d.has_code === true;
    const x = toX(d.index), y = toY(d.score);
    ctx.beginPath();
    ctx.arc(x, y, hasCode ? 5 : 3.5, 0, Math.PI * 2);
    ctx.fillStyle = hasCode
      ? "rgba(52, 152, 219, 0.8)"
      : "rgba(100, 149, 237, 0.35)";
    ctx.fill();
    ctx.strokeStyle = "white"; ctx.lineWidth = 0.5;
    ctx.stroke();
    pointPositions.push({{
      x, y, nickname: d.nickname, score: d.score,
      idx: d.index, hasCode: hasCode
    }});
  }}

  const bestProg = successful.reduce((a, b) =>
    a.score > b.score ? a : b);
  const bx = toX(bestProg.index), by = toY(bestProg.score);
  ctx.beginPath(); ctx.fillStyle = "#2ecc71";
  for (let i = 0; i < 10; i++) {{
    const angle = (i * Math.PI / 5) - Math.PI / 2;
    const r = i % 2 === 0 ? 10 : 4;
    const px = bx + r * Math.cos(angle);
    const py = by + r * Math.sin(angle);
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }}
  ctx.closePath(); ctx.fill();

  function findClosest(e) {{
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let closest = null, minDist = 20;
    for (const p of pointPositions) {{
      const dist = Math.sqrt((mx - p.x) ** 2 + (my - p.y) ** 2);
      if (dist < minDist) {{ closest = p; minDist = dist; }}
    }}
    return closest;
  }}

  canvas.addEventListener("mousemove", (e) => {{
    const closest = findClosest(e);
    if (closest) {{
      canvas.style.cursor = closest.hasCode ? "pointer" : "default";
      const code = CODE_SNIPPETS[closest.nickname] || "";
      const codeHtml = code
        ? `<pre><code>${{code.replace(/</g,"&lt;")
            .replace(/>/g,"&gt;")}}</code></pre>`
        : "";
      const hint = closest.hasCode
        ? "Click to view full code"
        : "Use: ae program show " + closest.nickname + " --code";
      tooltip.innerHTML =
        `<span class="name">${{closest.nickname}}</span> `
        + `(eval #${{closest.idx}})<br>`
        + `Score: <span class="score-val">${{
            closest.score.toFixed(4)}}</span>`
        + `<div style="margin-top:4px;font-size:0.75em;color:#666;">`
        + hint + `</div>`
        + codeHtml;
      tooltip.style.display = "block";
      const cRect = canvas.parentElement.getBoundingClientRect();
      tooltip.style.left =
        (e.clientX - cRect.left + 15) + "px";
      tooltip.style.top =
        (e.clientY - cRect.top - 10) + "px";
    }} else {{
      canvas.style.cursor = "default";
      tooltip.style.display = "none";
    }}
  }});

  canvas.addEventListener("click", (e) => {{
    const closest = findClosest(e);
    if (closest && closest.hasCode) {{
      tooltip.style.display = "none";
      showProgram(closest.nickname, closest.score, closest.idx);
    }}
  }});

  canvas.addEventListener("mouseleave", () => {{
    canvas.style.cursor = "default";
    tooltip.style.display = "none";
  }});
}}
</script>
</body>
</html>
"""


def _build_chart_data(
    successful: list[dict[str, Any]],
    failed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Builds the per-point chart data list from prepare_chart_data output.

  Args:
    successful: Successful points from prepare_chart_data.
    failed: Failed points from prepare_chart_data.

  Returns:
    Combined list of {index, nickname, score} dicts (score is None for
    failed programs), sorted by index.
  """
  chart_data = [
      {"index": p["index"], "nickname": p["nickname"], "score": p["score"]}
      for p in successful
  ]
  chart_data.extend(
      {"index": p["index"], "nickname": p["nickname"], "score": None}
      for p in failed
  )
  chart_data.sort(key=lambda d: d["index"])
  return chart_data


def _build_code_snippets(
    programs: list[dict[str, Any]],
    nickname_fn: NicknameFn = None,
    top_n: int = 15,
) -> tuple[dict[str, str], dict[str, str], set[str]]:
  """Extracts code previews and highlighted HTML for the top-N programs.

  Args:
    programs: List of program dicts (any order).
    nickname_fn: Optional callable(resource_name) -> nickname string.
    top_n: Number of top-scoring programs to extract code for.

  Returns:
    Tuple of (snippets, full_code_html, top_nicks) where:
      - snippets: {nickname: preview_code_string}
      - full_code_html: {nickname: syntax_highlighted_html}
      - top_nicks: set of nicknames that have code available
  """
  sorted_programs = sorted(programs, key=lambda p: p.get("createTime", ""))
  scored = [
      (p, s) for p in sorted_programs if (s := _extract_score(p)) is not None
  ]
  scored.sort(key=lambda x: x[1], reverse=True)

  snippets: dict[str, str] = {}
  full_code_html: dict[str, str] = {}
  top_nicks: set[str] = set()

  for prog, _ in scored[:top_n]:
    name = prog.get("name", "")
    nick = prog.get("nickname", "")
    if not nick and nickname_fn and name:
      nick = nickname_fn(name)
    if not nick:
      continue
    preview = _extract_code_snippet(prog, max_lines=30, evolve_block_only=True)
    if not preview:
      continue
    top_nicks.add(nick)
    snippets[nick] = preview
    full_src = _extract_code_snippet(
        prog, max_lines=5000, evolve_block_only=True
    )
    full_code_html[nick] = _highlight_python(full_src)

  return snippets, full_code_html, top_nicks


def _find_initial_score(programs: list[dict[str, Any]]) -> float | None:
  """Finds the initial (baseline) program's score.

  The initial program is identified as the one with no parent programs.
  When the backend omits ``createTime``, sorting by creation time is
  unreliable, so this provides a robust baseline for improvement
  calculations.

  Args:
    programs: List of raw program dicts from the API.

  Returns:
    The initial program's score, or None if not found.
  """
  for prog in programs:
    if not prog.get("parentPrograms"):
      score = _extract_score(prog)
      if score is not None:
        return score
  return None


def _compute_metrics(
    successful: list[dict[str, Any]],
    initial_score: float | None = None,
) -> tuple[float, float, float]:
  """Computes baseline, best score, and improvement percentage.

  Args:
    successful: Successful points from prepare_chart_data.
    initial_score: Score of the initial (no-parent) program, used as the
      baseline when available.  Falls back to the first successful point when
      ``None``.

  Returns:
    Tuple of (baseline, best, improvement_pct).
  """
  if initial_score is not None:
    baseline = initial_score
  else:
    baseline = successful[0]["score"] if successful else 0.0
  best = max(p["score"] for p in successful) if successful else 0.0
  if baseline != 0:
    improvement = ((best - baseline) / abs(baseline)) * 100
  else:
    improvement = 0.0
  return baseline, best, improvement


def _render_report_markdown(
    markdown_path: pathlib.Path | None,
) -> str:
  """Reads and renders a markdown report, stripping the score chart section.

  Args:
    markdown_path: Path to the markdown report file, or None.

  Returns:
    Rendered HTML string, or empty string if no file is provided.
  """
  if not markdown_path or not markdown_path.exists():
    return ""
  md_content = markdown_path.read_text(encoding="utf-8")
  md_content = re.sub(
      r"##\s+Score Progression\s*\n+"
      r"(?:!\[.*?\]\(.*?\)\s*\n*|[^\n#]*score_progression[^\n]*\n*)*",
      "",
      md_content,
  )
  return _render_markdown(md_content)


def generate_html_report(
    programs: list[dict[str, Any]],
    output_path: pathlib.Path,
    nickname: str = "experiment",
    model: str = "",
    duration: str = "",
    markdown_path: pathlib.Path | None = None,
    nickname_fn: NicknameFn = None,
) -> None:
  """Generates a self-contained interactive HTML report.

  Args:
    programs: List of program dicts (any order — sorted internally).
    output_path: Path to write the HTML file.
    nickname: Experiment nickname for the title.
    model: Model name string.
    duration: Duration string.
    markdown_path: Optional path to a markdown report file whose raw content is
      embedded below the chart.
    nickname_fn: Optional callable(resource_name) -> nickname string.
  """
  successful, failed, _ = prepare_chart_data(programs, nickname_fn)
  chart_data = _build_chart_data(successful, failed)

  snippets, full_code_html, top_nicks = _build_code_snippets(
      programs, nickname_fn
  )
  for entry in chart_data:
    entry["has_code"] = entry["nickname"] in top_nicks

  # Build the chart note.
  total_programs = len(chart_data)
  code_count = len(top_nicks)
  if total_programs <= 15:
    chart_note = (
        f"Showing {total_programs} programs."
        " Click any point to view the evolved code."
    )
  else:
    chart_note = (
        f"Top {code_count} programs (highlighted) have code"
        " available — click to inspect."
        " For any other program, run:"
        " ae program show <nickname>"
        f" --experiment {nickname} --code"
    )

  initial_score = _find_initial_score(programs)
  baseline, best, improvement = _compute_metrics(successful, initial_score)
  report_html = _render_report_markdown(markdown_path)
  date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

  output_html = _HTML_TEMPLATE.format(
      nickname=html_module.escape(nickname),
      date=date_str,
      model=html_module.escape(model or "N/A"),
      duration=html_module.escape(duration or "N/A"),
      baseline=baseline,
      best=best,
      improvement=improvement,
      pygments_css=_pygments_css(),
      chart_note=html_module.escape(chart_note),
      chart_data_json=json.dumps(chart_data),
      code_snippets_json=json.dumps(snippets),
      full_code_html_json=json.dumps(full_code_html),
      report_html=report_html,
  )

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(output_html, encoding="utf-8")
