# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Original implementation of Brenda Kulfan's Class-Shape Transformation (CST) method.

Reference:
  B. M. Kulfan, "Universal Parametric Geometry Representation Method,"
  Journal of Aircraft, Vol. 45, No. 1, 2008.
"""

import math
from typing import Sequence
import numpy as np


class CST_shape:
    """Evaluates 2D airfoil coordinates from Kulfan CST representation parameters."""

    def __init__(
        self,
        wl: Sequence[float] = (-1.0, -1.0, -1.0),
        wu: Sequence[float] = (1.0, 1.0, 1.0),
        dz: float = 0.0,
        N: int = 200,
    ) -> None:
        self.wl = np.asarray(wl, dtype=float)
        self.wu = np.asarray(wu, dtype=float)
        self.dz = float(dz)
        self.N = int(N)
        self.coord: np.ndarray | None = None

    def airfoil_coor(self) -> np.ndarray:
        """Computes and returns the (x, y) coordinates of the airfoil."""
        # Generate cosine-spaced x coordinates from trailing edge -> leading edge -> trailing edge
        angles = np.linspace(0.0, 2.0 * math.pi, self.N, endpoint=False)
        x = 0.5 * (np.cos(angles) + 1.0)

        center_idx = int(np.where(x == 0.0)[0][0])
        xl = x[:center_idx]
        xu = x[center_idx:]

        yl = self._compute_surface_y(xl, self.wl, -self.dz)
        yu = self._compute_surface_y(xu, self.wu, self.dz)

        y = np.concatenate([yl, yu])
        self.coord = np.column_stack((x, y))
        return self.coord

    @staticmethod
    def _compute_surface_y(x: np.ndarray, weights: np.ndarray, dz: float) -> np.ndarray:
        """Computes surface y-coordinates for a given x distribution and Bernstein weights."""
        # Kulfan class function for round leading edge / sharp trailing edge airfoil (N1=0.5, N2=1.0)
        class_function = (x ** 0.5) * (1.0 - x)

        # Bernstein polynomial shape function
        n = len(weights) - 1
        shape_function = np.zeros_like(x, dtype=float)

        for j, weight in enumerate(weights):
            binomial_coeff = math.factorial(n) / (math.factorial(j) * math.factorial(n - j))
            bernstein_basis = binomial_coeff * (x ** j) * ((1.0 - x) ** (n - j))
            shape_function += weight * bernstein_basis

        return class_function * shape_function + x * dz
