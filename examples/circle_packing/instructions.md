Evolve a constructor-based algorithm to pack N circles into a unit square,
maximizing the sum of their radii.

## Problem

Pack N=26 circles into a unit square [0, 1] x [0, 1] so that:
- No two circles overlap
- Every circle stays entirely within the square
- The sum of all radii is maximized

"Better" means a higher sum of radii while satisfying all constraints.

## Function signature

```python
def construct_packing(n: int, random_seed: int) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Args:
        n: Number of circles to pack.
        random_seed: Seed for reproducibility.

    Returns:
        centers: np.ndarray of shape (n, 2) — (x, y) coordinates
        radii:   np.ndarray of shape (n,)   — radius of each circle
        sum_of_radii: float — sum of all radii
    """
```

A helper `compute_max_radii(centers, random_seed)` may also be evolved.

## Constraints

- All centers must be within [0, 1] x [0, 1].
- Each circle must fit inside the square: for circle i, `radii[i] <= centers[i, 0]`,
  `radii[i] <= centers[i, 1]`, `radii[i] <= 1 - centers[i, 0]`,
  `radii[i] <= 1 - centers[i, 1]`.
- No two circles may overlap: for all i != j,
  `distance(centers[i], centers[j]) >= radii[i] + radii[j]`.
- All values must be finite (no NaN or inf).
- All radii must be non-negative.

## Available libraries

- `numpy` (imported as `np`)
- `typing.Any`, `typing.Mapping`

No other imports are allowed.

## Strategies to explore

- Deterministic grid or lattice placements (hexagonal, square)
- Concentric ring arrangements with optimized spacing
- Greedy placement with largest-first ordering
- Gradient-based local refinement of positions
- Known analytical packings for small N
- Hybrid approaches: structured seed + local search

Known dead ends:
- Pure random placement rarely achieves good density
- Placing all circles with equal radii wastes space

## Baselines

The seed program uses a simple concentric ring layout (1 center + 8 inner + 16 outer)
with proportional radius scaling. It achieves a sum_of_radii around 2.5.
A good packing should exceed 3.0.
