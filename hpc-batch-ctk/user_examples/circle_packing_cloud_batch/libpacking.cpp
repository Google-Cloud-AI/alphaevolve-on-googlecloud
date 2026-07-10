// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>

// EVOLVE-BLOCK-START
extern "C" {

void compute_max_radii_cpp(int n, double* centers_flat, double* radii_out) {
    // centers_flat is a flattened array of size n*2: [x0, y0, x1, y1, ...]
    // radii_out is an array of size n to be filled with the computed radii.

    // First, limit by distance to square borders
    for (int i = 0; i < n; ++i) {
        double x = centers_flat[i * 2];
        double y = centers_flat[i * 2 + 1];
        radii_out[i] = std::min({x, y, 1.0 - x, 1.0 - y});
    }

    // Then, limit by distance to other circles
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            double dx = centers_flat[i * 2] - centers_flat[j * 2];
            double dy = centers_flat[i * 2 + 1] - centers_flat[j * 2 + 1];
            double dist_sq = dx * dx + dy * dy;
            double dist = std::sqrt(dist_sq);

            if (radii_out[i] + radii_out[j] > dist) {
                double current_sum_radii = radii_out[i] + radii_out[j];
                if (current_sum_radii > 1e-9) { // Avoid division by zero
                    double scale = dist / current_sum_radii;
                    radii_out[i] *= scale;
                    radii_out[j] *= scale;
                } else {
                    // Circles are at the same point, should not happen with clipped centers
                    radii_out[i] = 0;
                    radii_out[j] = 0;
                }
            }
        }
    }
}

} // extern "C"
// EVOLVE-BLOCK-END

