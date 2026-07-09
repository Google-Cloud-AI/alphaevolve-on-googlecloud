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
# pylint: disable=g-import-not-at-top
# pylint: disable=g-bad-import-order
# pylint: disable=pointless-string-statement

"""Initial program for circle packing evolution."""

from typing import Any, Mapping

# EVOLVE-BLOCK-START
"""Constructor-based circle packing for n=26 circles"""
import numpy as np
import ctypes
import os


def construct_packing(n, random_seed: int):
  """Construct a specific arrangement of 26 circles in a unit square.

  The goal is to maximize the sum of their radii.

  Args:
    n: Number of circles.
    random_seed: Random seed for reproducibility.

  Returns:
    Tuple of (centers, radii, sum_of_radii)
    centers: np.array of shape (26, 2) with (x, y) coordinates
    radii: np.array of shape (26) with radius of each circle
    sum_of_radii: Sum of all radii
  """

  rng = np.random.default_rng(random_seed)
  centers = np.zeros((n, 2))

  # Place circles in a structured pattern
  # This is a simple pattern - evolution will improve this

  # First, place a large circle in the center
  centers[0] = [0.5, 0.5]

  # Place 8 circles around it in a ring
  for i in range(8):
    angle = 2 * np.pi * i / 8
    centers[i + 1] = [0.5 + 0.3 * np.cos(angle), 0.5 + 0.3 * np.sin(angle)]

  # Place 16 more circles in an outer ring
  for i in range(16):
    angle = 2 * np.pi * i / 16 * rng.uniform(0.9, 1.1)
    centers[i + 9] = [0.5 + 0.7 * np.cos(angle), 0.5 + 0.7 * np.sin(angle)]

  # Additional positioning adjustment to make sure all circles
  # are inside the square and don't overlap
  # Clip to ensure everything is inside the unit square
  centers = np.clip(centers, 0.01, 0.99)

  # Compute maximum valid radii for this configuration by calling the C++ library
  radii = call_compute_max_radii_cpp(centers)

  # Calculate the sum of radii
  sum_radii = np.sum(radii)

  return centers, radii, sum_radii


# ctypes setup for calling the C++ library
packing_lib = None
try:
  # Load the shared library
  print("Loading and configuring libpacking.so")
  lib_path = os.path.join(os.getcwd(), "libpacking.so")
  packing_lib = ctypes.CDLL(lib_path)

  # Define the function signature from the C++ library
  # void compute_max_radii_cpp(int n, double* centers_flat, double* radii_out)
  packing_lib.compute_max_radii_cpp.argtypes = [
      ctypes.c_int,
      np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags='C_CONTIGUOUS'),
      np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags='C_CONTIGUOUS')
  ]
  packing_lib.compute_max_radii_cpp.restype = None
  print("Success loading and configuring libpacking.so")

except OSError as e:
  print(f"Error loading or configuring libpacking.so: {e}")
  print("Please ensure libpacking.so is compiled and in the same directory.")
  packing_lib = None


def call_compute_max_radii_cpp(centers: np.ndarray) -> np.ndarray:
  """Helper function to call the C++ compute_max_radii function."""
  if packing_lib is None:
    raise RuntimeError("packing_lib not loaded.")

  n = centers.shape[0]
  if centers.shape != (n, 2):
    raise ValueError("Centers must have shape (n, 2)")

  # Flatten centers array for C++ interface (row-major)
  centers_flat = centers.astype(np.float64).flatten()

  # Prepare radii array for output
  radii_out = np.zeros(n, dtype=np.float64)

  # Call the C++ function
  packing_lib.compute_max_radii_cpp(n, centers_flat, radii_out)

  return radii_out

# EVOLVE-BLOCK-END


def _circles_overlap(centers, radii):
  """Protected function to compute max radii."""
  n = centers.shape[0]

  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
      if radii[i] + radii[j] > dist:
        return True

  return False


def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
  """Construct a packing and evaluate its score."""
  n = eval_inputs["n"]
  if "random_seed" not in eval_inputs:
    random_seed = 42
  else:
    random_seed = eval_inputs["random_seed"]
  centers, radii, _ = construct_packing(n, random_seed=random_seed)
  if (
      centers.shape != (n, 2)
      or not np.isfinite(centers).all()
      or not ((radii[:, None] <= centers) & (centers <= 1 - radii[:, None])).all()
  ):
    return {"sum_of_radii": -np.inf}

  if radii.shape != (n,) or not np.isfinite(radii).all() or not (0 <= radii).all():
    return {"sum_of_radii": -np.inf}

  if _circles_overlap(centers, radii):
    return {"sum_of_radii": -np.inf}

  return {"sum_of_radii": float(np.sum(radii))}
