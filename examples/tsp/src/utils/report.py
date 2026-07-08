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

"""Google-style experiment report for the TSP example."""

import logging
import os

import matplotlib.pyplot as plt
import numpy as np

from alpha_evolve.visualization import get_score

from ..evaluate import INITIAL_PROGRAM_CODE, METRIC_NAME
from ..program import (
    NUM_CITIES,
    INSTANCE_SEEDS,
    _generate_cities,
    _compute_distance_matrix,
    _random_tour_length,
)
from .visualization import (
    GOOGLE_BLUE,
    GOOGLE_BLUE_LIGHT,
    GOOGLE_BG,
    GOOGLE_GREEN,
    GOOGLE_GREEN_LIGHT,
    GOOGLE_GREY,
    GOOGLE_LIGHT_GREY,
    GOOGLE_RED,
    GOOGLE_RED_LIGHT,
    GOOGLE_TEXT,
    GOOGLE_YELLOW,
    GOOGLE_YELLOW_LIGHT,
    apply_google_style,
    plot_tour,
    run_tour,
    set_google_rcparams,
)

logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "report"
)


def generate_report(
    programs: list[dict],
    seed_score: float,
    save_dir: str | None = None,
):
    """Generate a multi-panel improvement report in Google style.

    Figures saved to ``save_dir``:
      1. evolution_progress.png  -- step-line best-so-far over iterations
      2. tour_length_distribution.png -- histogram
      3. seed_vs_best.png -- side-by-side tour comparison
      4. best_all_instances.png -- best tour on every test instance
      5. per_instance_comparison.png -- grouped bar chart

    Also saves the best evolved program to ``evolved_program/main.py``.
    """
    if save_dir is None:
        save_dir = REPORT_DIR
    os.makedirs(save_dir, exist_ok=True)
    set_google_rcparams()

    # Sort by score (best first) for "best program" selection
    scores = [get_score(p, METRIC_NAME) for p in programs]
    valid_programs = [p for p, s in zip(programs, scores) if np.isfinite(s)]
    tour_lengths = [-s for s in scores if np.isfinite(s)]

    best_score = max(scores) if scores else seed_score
    best_length = -best_score
    seed_length = -seed_score
    improvement_abs = seed_length - best_length
    improvement_pct = (
        improvement_abs / seed_length * 100.0 if seed_length else 0.0
    )

    # Sort programs chronologically by name (ID) for evolution chart
    chrono_programs = sorted(
        programs,
        key=lambda p: p.get("name", ""),
    )
    chrono_scores = [get_score(p, METRIC_NAME) for p in chrono_programs]

    # ---- Console summary ----
    _print_summary(seed_length, best_length, improvement_abs, improvement_pct,
                   len(programs), len(valid_programs))

    # ---- Per-instance breakdown ----
    per_instance_seed, per_instance_best, per_instance_random = (
        _print_per_instance(valid_programs)
    )

    # ---- Figures ----
    _fig_evolution_progress(chrono_scores, seed_length, best_length, save_dir)
    _fig_tour_length_distribution(tour_lengths, seed_length, best_length, save_dir)
    _fig_seed_vs_best(valid_programs, save_dir)
    _fig_best_all_instances(valid_programs, save_dir)
    _fig_per_instance_comparison(
        per_instance_seed, per_instance_best, per_instance_random, save_dir,
    )

    # ---- Save best evolved program ----
    _save_best_program(valid_programs)

    logger.info("Report saved to %s/", save_dir)


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

def _print_summary(
    seed_length: float,
    best_length: float,
    improvement_abs: float,
    improvement_pct: float,
    n_programs: int,
    n_valid: int,
):
    print()
    print("\033[1m" + "=" * 64 + "\033[0m")
    print("\033[1m  AlphaEvolve TSP -- Experiment Report\033[0m")
    print("\033[1m" + "=" * 64 + "\033[0m")
    print(f"  Cities              : {NUM_CITIES}")
    print(f"  Test instances      : {len(INSTANCE_SEEDS)}")
    print(f"  Programs evaluated  : {n_programs}")
    print(f"  Valid programs      : {n_valid}")
    print("-" * 64)
    print(f"  Seed tour length    : {seed_length:.4f}")
    print(f"  Best tour length    : \033[32m{best_length:.4f}\033[0m")
    print(
        f"  Improvement         : \033[32m{improvement_abs:.4f}  "
        f"({improvement_pct:.2f}%)\033[0m"
    )
    print("=" * 64)


def _print_per_instance(
    valid_programs: list[dict],
) -> tuple[list[float], list[float], list[float]]:
    per_instance_seed: list[float] = []
    per_instance_best: list[float] = []
    per_instance_random: list[float] = []

    if not valid_programs:
        return per_instance_seed, per_instance_best, per_instance_random

    best_code = valid_programs[0]["content"]["files"][0]["content"]
    print(
        f"\n  {'Instance':<10} {'Seed':>10} {'Best':>10} "
        f"{'Improv':>10} {'Random':>10}"
    )
    print("  " + "-" * 50)
    for seed in INSTANCE_SEEDS:
        _, s_len = run_tour(INITIAL_PROGRAM_CODE, seed)
        _, b_len = run_tour(best_code, seed)
        cities = _generate_cities(seed, NUM_CITIES)
        distances = _compute_distance_matrix(cities)
        r_len = _random_tour_length(distances, NUM_CITIES, seed)
        per_instance_seed.append(s_len or 0.0)
        per_instance_best.append(b_len or 0.0)
        per_instance_random.append(r_len)
        imp = ((s_len - b_len) / s_len * 100) if s_len and b_len else 0
        print(
            f"  {seed:<10} {s_len:>10.4f} {b_len:>10.4f} "
            f"{imp:>9.2f}% {r_len:>10.4f}"
        )
    print()
    return per_instance_seed, per_instance_best, per_instance_random


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def _fig_evolution_progress(
    scores: list[float],
    seed_length: float,
    best_length: float,
    save_dir: str,
):
    """Step-line best-so-far with individual scores as scatter points."""
    fig, ax = plt.subplots(figsize=(12, 5))
    apply_google_style(ax)

    best_so_far: list[float] = []
    individual_lengths: list[float] = []
    running = seed_length
    for s in scores:
        tl = -s if np.isfinite(s) else np.inf
        individual_lengths.append(tl)
        if tl < running:
            running = tl
        best_so_far.append(running)

    iters = list(range(len(best_so_far)))

    # Seed baseline
    ax.axhline(
        seed_length, color=GOOGLE_YELLOW, linestyle="--", linewidth=2,
        label=f"Seed baseline ({seed_length:.4f})", zorder=2,
    )

    # Individual candidate scores as faded scatter
    valid_iters = [i for i, l in zip(iters, individual_lengths) if l < seed_length * 2]
    valid_lengths = [l for l in individual_lengths if l < seed_length * 2]
    ax.scatter(
        valid_iters, valid_lengths,
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

    # Y-axis: focus on the interesting range
    finite_lengths = [l for l in individual_lengths if np.isfinite(l)]
    if finite_lengths:
        y_min = min(finite_lengths) * 0.95
        y_max = seed_length * 1.15
        ax.set_ylim(y_min, y_max)

    ax.set_xlabel("Evolution iteration", fontsize=11)
    ax.set_ylabel("Mean tour length", fontsize=11)
    ax.set_title(
        "AlphaEvolve TSP -- Evolution Progress",
        fontsize=14, fontweight="bold", pad=12,
    )
    ax.legend(
        loc="upper right", fontsize=9,
        framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY,
    )
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "evolution_progress.png"), dpi=150)
    plt.close(fig)


def _fig_tour_length_distribution(
    tour_lengths: list[float],
    seed_length: float,
    best_length: float,
    save_dir: str,
):
    if not tour_lengths:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    apply_google_style(ax)

    ax.hist(
        tour_lengths, bins=25,
        color=GOOGLE_BLUE_LIGHT, edgecolor=GOOGLE_BLUE, alpha=0.9,
    )
    ax.axvline(
        seed_length, color=GOOGLE_RED, linestyle="--",
        linewidth=1.8, label=f"Seed ({seed_length:.4f})",
    )
    ax.axvline(
        best_length, color=GOOGLE_GREEN, linestyle="--",
        linewidth=1.8, label=f"Best ({best_length:.4f})",
    )
    ax.set_xlabel("Tour length", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title(
        "Tour Length Distribution", fontsize=13, fontweight="bold", pad=10,
    )
    ax.legend(fontsize=9, framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY)
    plt.tight_layout()
    fig.savefig(
        os.path.join(save_dir, "tour_length_distribution.png"), dpi=150,
    )
    plt.close(fig)


def _fig_seed_vs_best(valid_programs: list[dict], save_dir: str):
    if not valid_programs:
        return
    best_code = valid_programs[0]["content"]["files"][0]["content"]
    fig, (ax_seed, ax_best) = plt.subplots(1, 2, figsize=(16, 7))
    fig.patch.set_facecolor(GOOGLE_BG)

    first_seed = INSTANCE_SEEDS[0]
    cities = _generate_cities(first_seed, NUM_CITIES)

    seed_tour, seed_len = run_tour(INITIAL_PROGRAM_CODE, first_seed)
    if seed_tour:
        plot_tour(
            ax_seed, cities, seed_tour,
            f"Seed: Nearest Neighbor ({seed_len:.4f})", color=GOOGLE_RED,
        )

    best_tour, best_len = run_tour(best_code, first_seed)
    if best_tour:
        plot_tour(
            ax_best, cities, best_tour,
            f"Best Evolved ({best_len:.4f})", color=GOOGLE_BLUE,
        )

    fig.suptitle(
        f"Seed vs Best -- Instance seed={first_seed}",
        fontsize=13, fontweight="bold", color=GOOGLE_TEXT,
    )
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "seed_vs_best.png"), dpi=150)
    plt.close(fig)


def _fig_best_all_instances(valid_programs: list[dict], save_dir: str):
    if not valid_programs:
        return
    best_code = valid_programs[0]["content"]["files"][0]["content"]
    n_inst = len(INSTANCE_SEEDS)

    # Use 2-row grid for better readability
    ncols = min(3, n_inst)
    nrows = (n_inst + ncols - 1) // ncols
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(6 * ncols, 6 * nrows),
    )
    fig.patch.set_facecolor(GOOGLE_BG)
    axes_flat = axes.flatten() if hasattr(axes, "flatten") else [axes]

    for idx, seed in enumerate(INSTANCE_SEEDS):
        ax = axes_flat[idx]
        cities = _generate_cities(seed, NUM_CITIES)
        tour, length = run_tour(best_code, seed)
        if tour:
            plot_tour(ax, cities, tour, f"seed={seed}  |  length={length:.4f}")
        else:
            apply_google_style(ax)
            ax.set_title(f"seed={seed}\nINVALID", color=GOOGLE_RED)

    # Hide unused axes
    for idx in range(n_inst, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle(
        "Best Evolved Tour -- All Instances",
        fontsize=14, fontweight="bold", color=GOOGLE_TEXT, y=1.01,
    )
    plt.tight_layout()
    fig.savefig(os.path.join(save_dir, "best_all_instances.png"), dpi=150)
    plt.close(fig)


def _fig_per_instance_comparison(
    per_instance_seed: list[float],
    per_instance_best: list[float],
    per_instance_random: list[float],
    save_dir: str,
):
    if not per_instance_seed or not per_instance_best:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    apply_google_style(ax)

    x = np.arange(len(INSTANCE_SEEDS))
    w = 0.30

    bars_seed = ax.bar(
        x - w / 2, per_instance_seed, w, label="Seed (NN)",
        color=GOOGLE_YELLOW_LIGHT, edgecolor=GOOGLE_YELLOW, linewidth=0.8,
    )
    bars_best = ax.bar(
        x + w / 2, per_instance_best, w, label="Best evolved",
        color=GOOGLE_GREEN_LIGHT, edgecolor=GOOGLE_GREEN, linewidth=0.8,
    )

    # Annotate improvement % on each pair
    for i, (s, b) in enumerate(zip(per_instance_seed, per_instance_best)):
        if s > 0:
            imp = (s - b) / s * 100
            ax.annotate(
                f"-{imp:.1f}%",
                xy=(x[i] + w / 2, b),
                xytext=(0, -14), textcoords="offset points",
                ha="center", fontsize=8, fontweight="bold",
                color=GOOGLE_GREEN,
            )

    # Y-axis: start from a sensible base to show differences
    all_vals = per_instance_seed + per_instance_best
    y_min = min(all_vals) * 0.85
    y_max = max(all_vals) * 1.08
    ax.set_ylim(y_min, y_max)

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"seed={s}" for s in INSTANCE_SEEDS], fontsize=9,
    )
    ax.set_ylabel("Tour length", fontsize=11)
    ax.set_title(
        "Per-Instance: Seed vs Best Evolved",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax.legend(fontsize=9, framealpha=0.9, edgecolor=GOOGLE_LIGHT_GREY)
    plt.tight_layout()
    fig.savefig(
        os.path.join(save_dir, "per_instance_comparison.png"), dpi=150,
    )
    plt.close(fig)


# ---------------------------------------------------------------------------
# Save best program
# ---------------------------------------------------------------------------

def _save_best_program(valid_programs: list[dict]):
    if not valid_programs:
        return
    best_code = valid_programs[0]["content"]["files"][0]["content"]
    evolved_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "evolved_program",
    )
    os.makedirs(evolved_dir, exist_ok=True)
    evolved_path = os.path.join(evolved_dir, "main.py")
    with open(evolved_path, "w") as f:
        f.write(best_code)
    logger.info("Best evolved program saved to %s", evolved_path)
