"""Initial program for Circle Packing in Unit Square.

Pack n non-overlapping circles inside a unit square [0,1]x[0,1] to maximize
the sum of their radii. Each circle must be entirely contained within the
square and no two circles may overlap.
"""

from typing import Any, Mapping

import numpy as np


# EVOLVE-BLOCK-START


def construct_packing(
    n: int, random_seed: int
) -> tuple[np.ndarray, np.ndarray, float]:
  """Construct an arrangement of n circles in a unit square.

  The goal is to maximize the sum of their radii while ensuring:
  - All circles are fully inside [0,1]x[0,1]
  - No two circles overlap

  Args:
      n: Number of circles to pack.
      random_seed: Random seed for reproducibility.

  Returns:
      Tuple of (centers, radii, sum_of_radii) where:
      - centers: np.ndarray of shape (n, 2) with (x, y) positions
      - radii: np.ndarray of shape (n,) with radius of each circle
      - sum_of_radii: float, sum of all radii
  """
  rng = np.random.default_rng(random_seed)
  centers = np.zeros((n, 2))

  # Place first circle in center
  centers[0] = [0.5, 0.5]

  # Place 8 circles in an inner ring
  for i in range(min(8, n - 1)):
    angle = 2 * np.pi * i / 8
    centers[i + 1] = [0.5 + 0.3 * np.cos(angle), 0.5 + 0.3 * np.sin(angle)]

  # Place remaining circles in an outer ring
  remaining = n - 9
  for i in range(max(0, remaining)):
    angle = 2 * np.pi * i / max(remaining, 1) + rng.uniform(-0.05, 0.05)
    r = 0.42
    centers[i + 9] = [0.5 + r * np.cos(angle), 0.5 + r * np.sin(angle)]

  # Clip to ensure all centers are inside the square
  centers = np.clip(centers, 0.02, 0.98)

  radii = compute_max_radii(centers)
  return centers, radii, float(np.sum(radii))


def compute_max_radii(centers: np.ndarray) -> np.ndarray:
  """Compute maximum non-overlapping radii for given center positions.

  Each radius is limited by:
  1. Distance to the nearest square boundary
  2. Distance to other circles (so they don't overlap)

  Args:
      centers: np.ndarray of shape (n, 2) with circle positions.

  Returns:
      np.ndarray of shape (n,) with maximum valid radii.
  """
  n = centers.shape[0]
  radii = np.zeros(n)

  # Limit by distance to square boundaries
  for i in range(n):
    x, y = centers[i]
    radii[i] = min(x, y, 1.0 - x, 1.0 - y)

  # Limit by distance to other circles
  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
      if radii[i] + radii[j] > dist:
        scale = dist / (radii[i] + radii[j] + 1e-10)
        radii[i] *= scale
        radii[j] *= scale

  return radii


# EVOLVE-BLOCK-END


def _circles_overlap(centers: np.ndarray, radii: np.ndarray) -> bool:
  """Check if any two circles overlap. Used for validation."""
  n = centers.shape[0]
  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
      if radii[i] + radii[j] > dist + 1e-9:
        return True
  return False


def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
  """Evaluate the packing solution.

  This function is OUTSIDE the evolve block — its contract is fixed.
  It calls the evolved construct_packing() and validates the result.

  Args:
      eval_inputs: Must contain 'n' (number of circles).

  Returns:
      {"sum_of_radii": score} where score is the sum of radii,
      or -inf if the packing is invalid.
  """
  n = eval_inputs["n"]
  random_seed = eval_inputs.get("random_seed", 42)

  centers, radii, _ = construct_packing(n, random_seed=random_seed)

  # Validate shapes
  if centers.shape != (n, 2) or radii.shape != (n,):
    return {"sum_of_radii": -np.inf}

  # Validate finiteness
  if not np.isfinite(centers).all() or not np.isfinite(radii).all():
    return {"sum_of_radii": -np.inf}

  # Validate non-negative radii
  if not (radii >= 0).all():
    return {"sum_of_radii": -np.inf}

  # Validate circles inside square
  if not ((radii <= centers[:, 0]) & (centers[:, 0] <= 1 - radii)).all():
    return {"sum_of_radii": -np.inf}
  if not ((radii <= centers[:, 1]) & (centers[:, 1] <= 1 - radii)).all():
    return {"sum_of_radii": -np.inf}

  # Validate no overlaps
  if _circles_overlap(centers, radii):
    return {"sum_of_radii": -np.inf}

  return {"sum_of_radii": float(np.sum(radii))}


if __name__ == "__main__":
  scores = evaluate({"n": 26})
  for metric, value in scores.items():
    print(f"{metric}: {value}")
