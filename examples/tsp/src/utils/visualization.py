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

"""Google-style visualization helpers for the TSP example."""

import matplotlib.pyplot as plt
import numpy as np

from ..program import (
    NUM_CITIES,
    _generate_cities,
    _compute_distance_matrix,
    _tour_length,
    _validate_tour,
)

# ---------------------------------------------------------------------------
# Google brand palette
# ---------------------------------------------------------------------------
GOOGLE_BLUE = "#4285F4"
GOOGLE_RED = "#EA4335"
GOOGLE_YELLOW = "#FBBC04"
GOOGLE_GREEN = "#34A853"
GOOGLE_GREY = "#5F6368"
GOOGLE_LIGHT_GREY = "#DADCE0"
GOOGLE_BG = "#FFFFFF"
GOOGLE_BLUE_LIGHT = "#D2E3FC"
GOOGLE_RED_LIGHT = "#FAD2CF"
GOOGLE_GREEN_LIGHT = "#CEEAD6"
GOOGLE_YELLOW_LIGHT = "#FDE293"
GOOGLE_TEXT = "#202124"

GOOGLE_FONT_STACK = [
    "Google Sans", "Product Sans", "Roboto",
    "Helvetica Neue", "Arial", "sans-serif",
]


def apply_google_style(ax: plt.Axes):
    """Apply clean Google-style formatting to axes."""
    ax.set_facecolor(GOOGLE_BG)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GOOGLE_LIGHT_GREY)
    ax.spines["bottom"].set_color(GOOGLE_LIGHT_GREY)
    ax.tick_params(colors=GOOGLE_GREY, labelsize=9)
    ax.xaxis.label.set_color(GOOGLE_GREY)
    ax.yaxis.label.set_color(GOOGLE_GREY)
    ax.title.set_color(GOOGLE_TEXT)
    ax.grid(True, color=GOOGLE_LIGHT_GREY, linewidth=0.5, alpha=0.7)


def set_google_rcparams():
    """Set matplotlib rcParams for Google-style output."""
    plt.rcParams.update({
        "figure.facecolor": GOOGLE_BG,
        "savefig.facecolor": GOOGLE_BG,
        "font.family": "sans-serif",
        "font.sans-serif": GOOGLE_FONT_STACK,
    })


def run_tour(code: str, seed: int) -> tuple[list[int] | None, float | None]:
    """Execute code in sandbox and return (tour, length) for one instance."""
    ns: dict = {"np": np, "Any": object, "Mapping": dict}
    try:
        exec(code, ns)
    except Exception:
        return None, None
    construct_tour = ns.get("construct_tour")
    if not callable(construct_tour):
        return None, None
    cities = _generate_cities(seed, NUM_CITIES)
    distances = _compute_distance_matrix(cities)
    try:
        tour = construct_tour(distances, NUM_CITIES)
    except Exception:
        return None, None
    if not _validate_tour(tour, NUM_CITIES):
        return None, None
    return tour, _tour_length(tour, distances)


def plot_tour(
    ax: plt.Axes,
    cities: np.ndarray,
    tour: list[int],
    title: str,
    color: str = GOOGLE_BLUE,
):
    """Draw a tour with gradient coloring to show direction."""
    from matplotlib.collections import LineCollection

    apply_google_style(ax)
    n = len(tour)
    ordered = np.array([cities[i] for i in tour] + [cities[tour[0]]])

    # Build line segments with color gradient (dark→light along path)
    segments = []
    for i in range(len(ordered) - 1):
        segments.append([ordered[i], ordered[i + 1]])
    segments = np.array(segments)

    # Color gradient: start dark, end lighter
    cmap = plt.cm.get_cmap("Blues" if color == GOOGLE_BLUE else "Reds")
    colors = [cmap(0.3 + 0.6 * i / n) for i in range(n)]

    lc = LineCollection(segments, colors=colors, linewidths=1.8, zorder=3)
    ax.add_collection(lc)

    # Add direction arrows at regular intervals
    arrow_interval = max(1, n // 8)
    for i in range(0, n, arrow_interval):
        src = ordered[i]
        dst = ordered[i + 1]
        mid = (src + dst) / 2
        dx, dy = dst - src
        ax.annotate(
            "", xy=(mid[0] + dx * 0.15, mid[1] + dy * 0.15),
            xytext=(mid[0] - dx * 0.15, mid[1] - dy * 0.15),
            arrowprops=dict(
                arrowstyle="->", color=cmap(0.3 + 0.6 * i / n),
                lw=1.5, mutation_scale=10,
            ),
            zorder=4,
        )

    # City dots
    ax.scatter(
        cities[:, 0], cities[:, 1], c=GOOGLE_GREY, s=25, zorder=5,
        edgecolors="white", linewidths=0.6,
    )
    # Start city
    ax.scatter(
        cities[tour[0], 0], cities[tour[0], 1],
        c=GOOGLE_GREEN, s=100, zorder=6, marker="*", label="Start",
        edgecolors="white", linewidths=0.8,
    )
    ax.set_title(title, fontsize=10, fontweight="medium")
    ax.set_aspect("equal")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(False)
