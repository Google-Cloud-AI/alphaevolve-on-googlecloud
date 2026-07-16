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

"""Experiment report for the LLM fine-tuning example."""

import json
import logging
import os

import matplotlib.pyplot as plt
import numpy as np

from alpha_evolve.visualization import get_score

from ..evaluate import METRIC_NAME

logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "report"
)
EVOLVED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "evolved_program"
)

# Google brand colours
GOOGLE_BLUE = "#4285F4"
GOOGLE_BLUE_LIGHT = "#AECBFA"
GOOGLE_GREEN = "#34A853"
GOOGLE_GREEN_LIGHT = "#A8DAB5"
GOOGLE_YELLOW = "#FBBC05"
GOOGLE_RED = "#EA4335"
GOOGLE_TEXT = "#202124"
GOOGLE_GREY = "#5F6368"
GOOGLE_LIGHT_GREY = "#DADCE0"
GOOGLE_BG = "#FFFFFF"

# Scores at or below this magnitude are bootstrap sentinels — e.g. an
# un-evaluated seed created with SEED_BOOTSTRAP_SCORE (-1e12) in run_evolution.py
# — not real measurements. They are kept out of every statistic and plot. Genuine
# neg_eval_loss values are small (roughly -1 to -100 including failed evals), so
# this threshold never excludes a real result.
SENTINEL_SCORE_THRESHOLD = -1e11


def _is_real_score(score: float) -> bool:
    """True only for a finite, non-sentinel (actually-measured) score."""
    return np.isfinite(score) and score > SENTINEL_SCORE_THRESHOLD


def generate_report(
    programs: list[dict],
    seed_score: float | None,
    save_dir: str | None = None,
):
    """Generate an improvement report and save the best evolved program.

    Args:
        programs: Programs returned by the AlphaEvolve API.
        seed_score: The seed's real ``neg_eval_loss`` when it was actually
            evaluated (BASELINE_SEED=true), or ``None`` when the seed evaluation
            was skipped. A skipped seed is bootstrapped into the database with a
            sentinel score that must never be reported as a real baseline.
        save_dir: Output directory (defaults to ``report/``).

    Outputs:
      - Console summary with eval-loss progression
      - report/evolution_progress.png — best-so-far neg_eval_loss over iterations
      - report/score_distribution.png — histogram of all valid scores
      - evolved_program/program.py — source code of the best candidate
      - evolved_program/result.json — score metadata
    """
    if save_dir is None:
        save_dir = REPORT_DIR
    os.makedirs(save_dir, exist_ok=True)

    scores = [get_score(p, METRIC_NAME) for p in programs]
    valid_idx = [i for i, s in enumerate(scores) if _is_real_score(s)]
    valid_programs = [programs[i] for i in valid_idx]
    valid_scores = [scores[i] for i in valid_idx]
    eval_losses = [-s for s in valid_scores]

    # A seed baseline is only meaningful when the seed was actually evaluated.
    has_seed_baseline = seed_score is not None and _is_real_score(seed_score)
    seed_loss = -seed_score if has_seed_baseline else None

    best_score = max(valid_scores) if valid_scores else None
    best_loss = -best_score if best_score is not None else None

    # Sort chronologically for evolution chart
    chrono_programs = sorted(programs, key=lambda p: p.get("name", ""))
    chrono_scores = [get_score(p, METRIC_NAME) for p in chrono_programs]

    # ---- Console summary ----
    _print_summary(
        seed_loss, best_loss,
        n_total=len(programs),
        n_valid=len(valid_programs),
        n_unscored=len(programs) - len(valid_programs),
        all_losses=eval_losses,
    )

    # ---- Figures ----
    _fig_evolution_progress(chrono_scores, seed_loss, best_loss, save_dir)
    _fig_score_distribution(eval_losses, seed_loss, best_loss, save_dir)

    # ---- Save best program ----
    if best_score is not None:
        _save_best_program(valid_programs, best_score)

    logger.info("Report saved to %s/", save_dir)


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

def _print_summary(
    seed_loss: float | None,
    best_loss: float | None,
    n_total: int,
    n_valid: int,
    n_unscored: int,
    all_losses: list[float],
):
    print()
    print("\033[1m" + "=" * 64 + "\033[0m")
    print("\033[1m  AlphaEvolve LLM Fine-Tuning -- Experiment Report\033[0m")
    print("\033[1m" + "=" * 64 + "\033[0m")
    print(f"  Task                : LoRA fine-tuning (Gemma 4 E2B)")
    print(f"  Programs returned   : {n_total}")
    print(f"  Successful          : {n_valid}")
    print(f"  Unscored / failed   : {n_unscored}")
    print("-" * 64)
    if seed_loss is not None:
        print(f"  Seed eval loss      : {seed_loss:.6f}")
    else:
        print(f"  Seed eval loss      : not evaluated (baseline skipped)")
    if best_loss is not None:
        print(f"  Best eval loss      : \033[32m{best_loss:.6f}\033[0m")
    else:
        print(f"  Best eval loss      : n/a (no successful programs)")
    if seed_loss is not None and best_loss is not None:
        improvement = (seed_loss - best_loss) / seed_loss * 100 if seed_loss else 0
        print(
            f"  Improvement         : \033[32m{seed_loss - best_loss:.6f}  "
            f"({improvement:.2f}%)\033[0m"
        )
    if all_losses:
        print(f"  Median eval loss    : {np.median(all_losses):.6f}")
        print(f"  Worst eval loss     : {max(all_losses):.6f}")
    print("=" * 64)

    if all_losses:
        show_delta = seed_loss is not None and seed_loss != 0
        header = f"\n  {'Rank':<6} {'Eval Loss':>12}"
        print(header + (f" {'vs Seed':>12}" if show_delta else ""))
        print("  " + "-" * (30 if show_delta else 18))
        sorted_losses = sorted(all_losses)
        for i, loss in enumerate(sorted_losses[:10]):
            if show_delta:
                delta = (seed_loss - loss) / seed_loss * 100
                sign = "+" if delta > 0 else ""
                print(f"  #{i+1:<5} {loss:>12.6f} {sign}{delta:>11.2f}%")
            else:
                print(f"  #{i+1:<5} {loss:>12.6f}")
        if len(sorted_losses) > 10:
            print(f"  ... ({len(sorted_losses) - 10} more)")
    print()


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _fig_evolution_progress(
    scores: list[float],
    seed_loss: float | None,
    best_loss: float | None,
    save_dir: str,
):
    """Step-line best-so-far neg_eval_loss over iterations."""
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(GOOGLE_BG)
    ax.set_facecolor(GOOGLE_BG)

    # Plot only real (finite, non-sentinel) measurements so an un-evaluated seed
    # or bootstrap sentinel never distorts the axis or the best-so-far line.
    iters: list[int] = []
    individual_scores: list[float] = []
    best_so_far: list[float] = []
    running = -float("inf")
    for i, s in enumerate(scores):
        if not _is_real_score(s):
            continue
        iters.append(i)
        individual_scores.append(s)
        if s > running:
            running = s
        best_so_far.append(running)

    # Seed baseline (only when the seed was actually evaluated)
    if seed_loss is not None:
        ax.axhline(
            -seed_loss, color=GOOGLE_YELLOW, linestyle="--", linewidth=2,
            label=f"Seed baseline ({-seed_loss:.4f})", zorder=2,
        )

    # Individual candidate scores
    ax.scatter(
        iters, individual_scores,
        color=GOOGLE_BLUE_LIGHT, s=18, zorder=3, alpha=0.6,
        edgecolors=GOOGLE_BLUE, linewidths=0.3, label="Individual candidates",
    )

    # Best-so-far step line
    ax.step(
        iters, best_so_far, where="post",
        color=GOOGLE_BLUE, linewidth=2.5, label="Best so far", zorder=4,
    )
    if best_so_far:
        ax.scatter(
            [iters[-1]], [best_so_far[-1]],
            color=GOOGLE_BLUE, s=60, zorder=5,
            edgecolors="white", linewidths=1.5,
        )

    ax.set_xlabel("Evolution iteration", fontsize=11)
    ax.set_ylabel("neg_eval_loss (higher is better)", fontsize=11)
    ax.set_title(
        "AlphaEvolve LLM Fine-Tuning -- Evolution Progress",
        fontsize=14, fontweight="bold", pad=12,
    )
    ax.legend(
        loc="lower right", fontsize=9,
        framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY,
    )
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "evolution_progress.png"), dpi=150)
    plt.close(fig)


def _fig_score_distribution(
    eval_losses: list[float],
    seed_loss: float | None,
    best_loss: float | None,
    save_dir: str,
):
    """Histogram of eval loss across all valid programs."""
    if not eval_losses:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(GOOGLE_BG)
    ax.set_facecolor(GOOGLE_BG)

    ax.hist(
        eval_losses, bins=25,
        color=GOOGLE_BLUE_LIGHT, edgecolor=GOOGLE_BLUE, alpha=0.9,
    )
    if seed_loss is not None:
        ax.axvline(
            seed_loss, color=GOOGLE_RED, linestyle="--",
            linewidth=1.8, label=f"Seed ({seed_loss:.4f})",
        )
    if best_loss is not None:
        ax.axvline(
            best_loss, color=GOOGLE_GREEN, linestyle="--",
            linewidth=1.8, label=f"Best ({best_loss:.4f})",
        )
    ax.set_xlabel("Eval Loss", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title(
        "Eval Loss Distribution Across Evolved Programs",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax.legend(fontsize=9, framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY)
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "score_distribution.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Save best program
# ---------------------------------------------------------------------------

def _save_best_program(valid_programs: list[dict], best_score: float):
    """Save best evolved program source code and metadata."""
    if not valid_programs:
        return
    os.makedirs(EVOLVED_DIR, exist_ok=True)

    best = valid_programs[0]
    best_code = best["content"]["files"][0]["content"]

    # Save source code
    code_path = os.path.join(EVOLVED_DIR, "program.py")
    with open(code_path, "w") as f:
        f.write(best_code)

    # Save metadata
    meta = {
        "metric": METRIC_NAME,
        "score": best_score,
        "eval_loss": -best_score,
        "program_name": best.get("name", ""),
        "parent_programs": best.get("parentPrograms", []),
    }
    meta_path = os.path.join(EVOLVED_DIR, "result.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Best evolved program saved to %s", code_path)
    print(f"  Best program saved to: {code_path}")
    print(f"  Result metadata:       {meta_path}")
