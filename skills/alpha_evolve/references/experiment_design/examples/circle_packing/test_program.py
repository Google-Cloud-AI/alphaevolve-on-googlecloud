"""Tests for the circle packing initial program."""

from initial_program import construct_packing
from initial_program import evaluate
import numpy as np


EVAL_INPUTS = {"n": 26}


class TestSolve:
  """Tests for the core packing functions."""

  def test_construct_packing_returns_correct_shapes(self):
    """construct_packing returns (centers, radii, sum) with correct shapes."""
    centers, radii, total = construct_packing(26, random_seed=42)
    assert centers.shape == (26, 2)
    assert radii.shape == (26,)
    assert isinstance(total, (int, float, np.floating))

  def test_construct_packing_centers_in_bounds(self):
    """All circle centers are inside [0, 1]."""
    centers, _, _ = construct_packing(26, random_seed=42)
    assert np.all(centers >= 0.0)
    assert np.all(centers <= 1.0)

  def test_construct_packing_radii_non_negative(self):
    """All radii are non-negative."""
    _, radii, _ = construct_packing(26, random_seed=42)
    assert np.all(radii >= 0.0)

  def test_construct_packing_circles_inside_square(self):
    """Each circle (center ± radius) is fully inside [0, 1]."""
    centers, radii, _ = construct_packing(26, random_seed=42)
    assert np.all(centers[:, 0] - radii >= -1e-9)
    assert np.all(centers[:, 0] + radii <= 1.0 + 1e-9)
    assert np.all(centers[:, 1] - radii >= -1e-9)
    assert np.all(centers[:, 1] + radii <= 1.0 + 1e-9)

  def test_construct_packing_no_overlaps(self):
    """No two circles overlap."""
    centers, radii, _ = construct_packing(26, random_seed=42)
    n = len(radii)
    for i in range(n):
      for j in range(i + 1, n):
        dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
        assert dist >= radii[i] + radii[j] - 1e-9, (
            f"Circles {i} and {j} overlap: dist={dist}, "
            f"r_i+r_j={radii[i] + radii[j]}"
        )

  def test_construct_packing_deterministic(self):
    """Same seed produces same result."""
    c1, r1, s1 = construct_packing(26, random_seed=42)
    c2, r2, s2 = construct_packing(26, random_seed=42)
    np.testing.assert_array_equal(c1, c2)
    np.testing.assert_array_equal(r1, r2)
    assert s1 == s2


class TestEvaluate:
  """Tests for the evaluate function."""

  def test_evaluate_returns_dict_with_metric(self):
    """evaluate() returns a dict containing 'sum_of_radii'."""
    result = evaluate(EVAL_INPUTS)
    assert isinstance(result, dict)
    assert "sum_of_radii" in result

  def test_evaluate_returns_finite_score(self):
    """evaluate() returns a finite positive score."""
    result = evaluate(EVAL_INPUTS)
    score = result["sum_of_radii"]
    assert isinstance(score, float)
    assert np.isfinite(score)
    assert score > 0

  def test_evaluate_deterministic(self):
    """Same inputs produce same score."""
    r1 = evaluate(EVAL_INPUTS)
    r2 = evaluate(EVAL_INPUTS)
    assert r1["sum_of_radii"] == r2["sum_of_radii"]
