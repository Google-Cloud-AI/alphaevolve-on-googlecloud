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

"""Travelling Salesman Problem — seed algorithm for AlphaEvolve.

Given N cities with 2D coordinates, find the shortest tour visiting all cities
exactly once and returning to the start. The EVOLVE-BLOCK contains
``construct_tour(distances, n)`` which returns a permutation of city indices.
AlphaEvolve will evolve this function to produce shorter tours.
"""

from typing import Any, Mapping

import numpy as np


# EVOLVE-BLOCK-START

def construct_tour(distances: np.ndarray, n: int) -> list[int]:
    """Construct a tour using the nearest-neighbor heuristic.

    Starting from city 0, repeatedly visit the nearest unvisited city.

    Args:
        distances: n x n symmetric distance matrix.
        n: number of cities.

    Returns:
        A permutation of [0, n) representing the visit order.
    """
    visited = [False] * n
    tour = [0]
    visited[0] = True

    for _ in range(n - 1):
        current = tour[-1]
        best_next = -1
        best_dist = np.inf
        for j in range(n):
            if not visited[j] and distances[current][j] < best_dist:
                best_dist = distances[current][j]
                best_next = j
        tour.append(best_next)
        visited[best_next] = True

    return tour

# EVOLVE-BLOCK-END


# ---------------------------------------------------------------------------
# Evaluation helpers — OUTSIDE the evolve block (never modified by the LLM)
# ---------------------------------------------------------------------------

# Fixed city instances for reproducible evaluation
NUM_INSTANCES = 5
NUM_CITIES = 50
INSTANCE_SEEDS = [42, 123, 256, 789, 1024]


def _generate_cities(seed: int, n: int = NUM_CITIES) -> np.ndarray:
    """Generate n random 2D city coordinates in [0, 1] x [0, 1]."""
    rng = np.random.RandomState(seed)
    return rng.rand(n, 2)


def _compute_distance_matrix(cities: np.ndarray) -> np.ndarray:
    """Compute pairwise Euclidean distance matrix."""
    diff = cities[:, np.newaxis, :] - cities[np.newaxis, :, :]
    return np.sqrt((diff ** 2).sum(axis=2))


def _tour_length(tour: list[int], distances: np.ndarray) -> float:
    """Total length of the tour including return to start."""
    length = 0.0
    for i in range(len(tour)):
        length += distances[tour[i]][tour[(i + 1) % len(tour)]]
    return length


def _random_tour_length(distances: np.ndarray, n: int, seed: int) -> float:
    """Average length of random tours (sample 50 and take mean)."""
    rng = np.random.RandomState(seed + 99999)
    lengths = []
    for _ in range(50):
        perm = rng.permutation(n).tolist()
        lengths.append(_tour_length(perm, distances))
    return float(np.mean(lengths))


def _validate_tour(tour: list[int], n: int) -> bool:
    """Check that tour is a valid permutation of [0, n)."""
    if not isinstance(tour, list):
        return False
    if len(tour) != n:
        return False
    if set(tour) != set(range(n)):
        return False
    return True


def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
    """Evaluate the construct_tour function across fixed city instances.

    Returns:
        Dictionary with metrics:
        - neg_tour_length: negative average tour length (higher is better)
        - tour_validity: 1.0 if all tours are valid, else 0.0
        - avg_improvement_over_random: average % improvement vs random tours
    """
    n = NUM_CITIES
    total_tour_length = 0.0
    total_improvement = 0.0
    all_valid = True

    for seed in INSTANCE_SEEDS:
        cities = _generate_cities(seed, n)
        distances = _compute_distance_matrix(cities)
        tour = construct_tour(distances, n)

        if not _validate_tour(tour, n):
            all_valid = False
            return {
                "neg_tour_length": -np.inf,
                "tour_validity": 0.0,
                "avg_improvement_over_random": -np.inf,
            }

        length = _tour_length(tour, distances)
        total_tour_length += length

        rand_length = _random_tour_length(distances, n, seed)
        improvement = (rand_length - length) / rand_length * 100.0
        total_improvement += improvement

    avg_tour_length = total_tour_length / NUM_INSTANCES
    avg_improvement = total_improvement / NUM_INSTANCES

    return {
        "neg_tour_length": -avg_tour_length,
        "tour_validity": 1.0 if all_valid else 0.0,
        "avg_improvement_over_random": avg_improvement,
    }
