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

import numpy as np
import sys
from pathlib import Path
from typing import Any, Mapping

# Import optimization functions from our local src/ directory
from third_party.optimization.optimization import funct, Parameters

# Define standard search bounds for 6 CST parameters
BOUNDS = np.array([
    [-1.4400, -0.1027], # x0
    [-1.2552, 1.2923],  # x1
    [-0.8296, 0.4836],  # x2
    [0.0359, 1.3246],   # x3
    [-0.1423, 1.4558],  # x4
    [-0.3631, 1.4440]   # x5
])

# Best performing airfoil found during previous optimization runs (Cl/Cd ~ 17.54)
BEST_KNOWN_X = np.array([
    -0.5516626232694845,
    0.2364855050246478,
    -0.3662099033519582,
    0.8358341172343055,
    0.5441437820641782,
    1.31593469417802
])

def optimize_airfoil(parameters: Parameters, max_successful_simulations: int = 10, max_total_simulations: int = 100) -> tuple[np.ndarray, float]:
    """Evolved optimization loop for airfoil CST parameters.

    Args:
        parameters: The OpenFOAM simulation parameters (defines cases folder, fluid velocity, etc).
        max_successful_simulations: Maximum allowed ACTUAL OpenFOAM simulations.
        max_total_simulations: Maximum allowed TOTAL simulations (including failed ones).

    Returns:
        Tuple of (best_x, best_score) where best_score is the minimum value of funct.
    """
    best_x = None
    best_score = float('inf')
    successful_simulations_count = 0
    total_simulation_counts=0
    
# EVOLVE-BLOCK-START
    # Baseline: Evaluate the best known airfoil first, then perform Random Search.
    # Evolution should replace this loop with a smart, physics-aware optimization heuristic.
    
    # 1. Evaluate the best known airfoil first
    score = funct(BEST_KNOWN_X, parameters)
    if score != float('inf'):
        successful_simulations_count += 1
        if score < best_score:
            best_score = score
            best_x = BEST_KNOWN_X.copy()
    total_simulation_counts += 1

    # 2. Continue with Random Search
    while successful_simulations_count < max_successful_simulations or total_simulation_counts < max_total_simulations:
        # 2.1. Sample candidate shape
        x = np.zeros(6)
        for i in range(6):
            x[i] = np.random.uniform(BOUNDS[i, 0], BOUNDS[i, 1])
            
        # 2.2. [CFD-Aware Pre-Screening] 
        # Evolve custom geometric or physics checks here to reject bad shapes before calling funct!
        # Discarding invalid shapes early preserves the valuable 20-simulation budget.
        # If shape is rejected, use 'continue' to skip funct and sample a new candidate.
        
        # 2.3. Evaluate candidate via actual CFD simulation
        score = funct(x, parameters)
        
        # 2.4. Process result (only count if it didn't fail immediately before running)
        # Note: funct returns inf if clipping or mesh checks fail.
        if score != float('inf'):
            successful_simulations_count += 1
            if score < best_score:
                best_score = score
                best_x = x
        total_simulation_counts += 1
# EVOLVE-BLOCK-END
                
    return best_x, best_score


def evaluate(parameters: Parameters, max_successful_simulations: int = 10, max_total_simulations: int = 100) -> tuple[np.ndarray, float]:
    """Utility function to run the airfoil optimization loop.
    
    This method provides the AI agent with context on how the optimization 
    loop is called and executed during evaluation.

    Args:
        parameters: The OpenFOAM simulation parameters (defines cases folder, fluid velocity, etc).
        max_successful_simulations: Maximum allowed ACTUAL OpenFOAM simulations.
        max_total_simulations: Maximum allowed TOTAL simulations (including failed ones).

    Returns:
        Tuple of (best_x, best_score) where best_score is the minimum value of funct.
    """
    return optimize_airfoil(parameters, max_successful_simulations=max_successful_simulations, max_total_simulations=max_total_simulations)
