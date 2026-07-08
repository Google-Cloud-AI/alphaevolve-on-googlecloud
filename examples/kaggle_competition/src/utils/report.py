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

"""Experiment report for the Kaggle competition example."""

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


def generate_report(
    programs: list[dict],
    seed_score: float,
    save_dir: str | None = None,
):
    """Generate an improvement report and save the best evolved program.

    Outputs:
      - Console summary with MAE progression
      - report/evolution_progress.png — best-so-far MAE over iterations
      - report/mae_distribution.png — histogram of all valid MAE scores
      - evolved_program/main.py — source code of the best candidate
      - evolved_program/result.json — score metadata
    """
    if save_dir is None:
        save_dir = REPORT_DIR
    os.makedirs(save_dir, exist_ok=True)

    scores = [get_score(p, METRIC_NAME) for p in programs]
    valid_idx = [i for i, s in enumerate(scores) if np.isfinite(s)]
    valid_programs = [programs[i] for i in valid_idx]
    valid_scores = [scores[i] for i in valid_idx]
    mae_values = [-s for s in valid_scores]

    best_score = max(valid_scores) if valid_scores else seed_score
    best_mae = -best_score
    seed_mae = -seed_score

    # Sort chronologically for evolution chart
    chrono_programs = sorted(programs, key=lambda p: p.get("name", ""))
    chrono_scores = [get_score(p, METRIC_NAME) for p in chrono_programs]

    # ---- Console summary ----
    _print_summary(
        seed_mae, best_mae,
        n_total=len(programs),
        n_valid=len(valid_programs),
        n_failed=len(programs) - len(valid_programs),
        all_maes=mae_values,
    )

    # ---- Figures ----
    _fig_evolution_progress(chrono_scores, seed_mae, best_mae, save_dir)
    _fig_mae_distribution(mae_values, seed_mae, best_mae, save_dir)

    # ---- Save best program ----
    _save_best_program(valid_programs, best_score)

    logger.info("Report saved to %s/", save_dir)


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

def _print_summary(
    seed_mae: float,
    best_mae: float,
    n_total: int,
    n_valid: int,
    n_failed: int,
    all_maes: list[float],
):
    improvement = (seed_mae - best_mae) / seed_mae * 100 if seed_mae else 0
    print()
    print("\033[1m" + "=" * 64 + "\033[0m")
    print("\033[1m  AlphaEvolve Kaggle -- Experiment Report\033[0m")
    print("\033[1m" + "=" * 64 + "\033[0m")
    print(f"  Competition         : Zillow Prize (logerror prediction)")
    print(f"  Programs evaluated  : {n_total}")
    print(f"  Successful          : {n_valid}")
    print(f"  Failed              : {n_failed}")
    print("-" * 64)
    print(f"  Seed MAE (Ridge)    : {seed_mae:.6f}")
    print(f"  Best MAE            : \033[32m{best_mae:.6f}\033[0m")
    print(
        f"  Improvement         : \033[32m{seed_mae - best_mae:.6f}  "
        f"({improvement:.2f}%)\033[0m"
    )
    if all_maes:
        print(f"  Median MAE          : {np.median(all_maes):.6f}")
        print(f"  Worst MAE           : {max(all_maes):.6f}")
    print("=" * 64)

    if all_maes:
        print(f"\n  {'Rank':<6} {'MAE':>12} {'vs Seed':>12}")
        print("  " + "-" * 30)
        sorted_maes = sorted(all_maes)
        for i, mae in enumerate(sorted_maes[:10]):
            delta = (seed_mae - mae) / seed_mae * 100
            sign = "+" if delta > 0 else ""
            print(f"  #{i+1:<5} {mae:>12.6f} {sign}{delta:>11.2f}%")
        if len(sorted_maes) > 10:
            print(f"  ... ({len(sorted_maes) - 10} more)")
    print()


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _fig_evolution_progress(
    scores: list[float],
    seed_mae: float,
    best_mae: float,
    save_dir: str,
):
    """Step-line best-so-far MAE over iterations."""
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(GOOGLE_BG)
    ax.set_facecolor(GOOGLE_BG)

    best_so_far: list[float] = []
    individual_maes: list[float] = []
    running = seed_mae
    for s in scores:
        mae = -s if np.isfinite(s) else np.inf
        individual_maes.append(mae)
        if mae < running:
            running = mae
        best_so_far.append(running)

    iters = list(range(len(best_so_far)))

    # Seed baseline
    ax.axhline(
        seed_mae, color=GOOGLE_YELLOW, linestyle="--", linewidth=2,
        label=f"Seed baseline ({seed_mae:.6f})", zorder=2,
    )

    # Individual candidate scores (only finite, reasonable ones)
    cutoff = seed_mae * 1.5
    valid_iters = [i for i, m in zip(iters, individual_maes) if m < cutoff]
    valid_maes = [m for m in individual_maes if m < cutoff]
    ax.scatter(
        valid_iters, valid_maes,
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

    # Y-axis range
    finite_maes = [m for m in individual_maes if np.isfinite(m) and m < cutoff]
    if finite_maes:
        ax.set_ylim(min(finite_maes) * 0.995, seed_mae * 1.01)

    ax.set_xlabel("Evolution iteration", fontsize=11)
    ax.set_ylabel("MAE (lower is better)", fontsize=11)
    ax.set_title(
        "AlphaEvolve Kaggle -- Evolution Progress",
        fontsize=14, fontweight="bold", pad=12,
    )
    ax.legend(
        loc="upper right", fontsize=9,
        framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY,
    )
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "evolution_progress.png"), dpi=150)
    plt.close(fig)


def _fig_mae_distribution(
    mae_values: list[float],
    seed_mae: float,
    best_mae: float,
    save_dir: str,
):
    """Histogram of MAE across all valid programs."""
    if not mae_values:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(GOOGLE_BG)
    ax.set_facecolor(GOOGLE_BG)

    ax.hist(
        mae_values, bins=25,
        color=GOOGLE_BLUE_LIGHT, edgecolor=GOOGLE_BLUE, alpha=0.9,
    )
    ax.axvline(
        seed_mae, color=GOOGLE_RED, linestyle="--",
        linewidth=1.8, label=f"Seed ({seed_mae:.6f})",
    )
    ax.axvline(
        best_mae, color=GOOGLE_GREEN, linestyle="--",
        linewidth=1.8, label=f"Best ({best_mae:.6f})",
    )
    ax.set_xlabel("MAE", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title(
        "MAE Distribution Across Evolved Programs",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax.legend(fontsize=9, framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY)
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "mae_distribution.png"), dpi=150)
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
    code_path = os.path.join(EVOLVED_DIR, "main.py")
    with open(code_path, "w") as f:
        f.write(best_code)

    # Save metadata
    meta = {
        "metric": METRIC_NAME,
        "score": best_score,
        "mae": -best_score,
        "program_name": best.get("name", ""),
        "parent_programs": best.get("parentPrograms", []),
    }
    meta_path = os.path.join(EVOLVED_DIR, "result.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Best evolved program saved to %s", code_path)
    print(f"  Best program saved to: {code_path}")
    print(f"  Result metadata:       {meta_path}")
