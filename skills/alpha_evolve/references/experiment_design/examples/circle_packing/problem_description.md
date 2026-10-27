# Circle Packing in Unit Square

## Problem Statement

Given a positive integer **n**, place **n** non-overlapping circles inside the
unit square [0, 1] × [0, 1] such that the **sum of all radii** is maximized.

**Input:** An integer `n` (number of circles) and a `random_seed` for
reproducibility.

**Output:** A tuple `(centers, radii, sum_of_radii)` where:

- `centers` is an `(n, 2)` numpy array of (x, y) positions
- `radii` is an `(n,)` numpy array of circle radii
- `sum_of_radii` is a float, the objective value

## Formal Specification

**Variables:**

- Circle centers: (xᵢ, yᵢ) ∈ ℝ² for i = 1, ..., n
- Circle radii: rᵢ ∈ ℝ≥0 for i = 1, ..., n

**Objective:** Maximize Σᵢ rᵢ

**Constraints:**
1. **Containment:** Each circle must be fully inside the unit square:
   - rᵢ ≤ xᵢ ≤ 1 − rᵢ
   - rᵢ ≤ yᵢ ≤ 1 − rᵢ
2. **Non-overlap:** For all i ≠ j:
   - ‖(xᵢ, yᵢ) − (xⱼ, yⱼ)‖₂ ≥ rᵢ + rⱼ
3. **Non-negative radii:** rᵢ ≥ 0 for all i

## Evaluation

- **Metric:** `sum_of_radii` (maximize)
- **Strategy:** Fixed benchmark with n=26 circles
- **Inputs:** `{"n": 26}` — pack 26 circles, evaluated with seed 42

The score is `-inf` if any constraint is violated (shapes, bounds, overlaps).

## Solution Guidance

**Known approaches:**

- **Grid-based:** Place circles on a regular grid and compute maximum radii.
  Simple but suboptimal for non-uniform sizes.
- **Greedy constructive:** Place circles one at a time, choosing positions
  that maximize the new circle's radius. Order matters significantly.
- **Optimization-based:** Start with a random or grid placement, then use
  gradient descent or simulated annealing to adjust positions.
- **Apollonian gasket:** Fill gaps with progressively smaller circles,
  inspired by fractal packing.

**What makes a good solution:**

- Larger circles placed first, with smaller circles filling gaps
- Avoidance of wasted space near corners and edges
- Good balance between large few and many small circles

**Common pitfalls:**

- Numerical precision: distances and boundary checks must handle floating
  point carefully. Use tolerances (1e-9).
- Local optima: greedy approaches get stuck. Consider perturbation or
  restarts.
- Symmetry: the square has 8-fold symmetry (4 rotations × 2 reflections).
  Good solutions often exploit this.
