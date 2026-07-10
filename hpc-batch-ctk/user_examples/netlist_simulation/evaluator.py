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

import os
import subprocess
import logging
import re

logger = logging.getLogger(__name__)

EVALUATION_METRIC = "voltage_gain"

# Define the "Safe Zone" (10% to 90% of the rail)
V_MAX_SAFE = 4.5
V_MIN_SAFE = 0.5

def evaluate() -> dict:
    logger.info("Entering enhanced netlist evaluation")
    
    try:
        result = subprocess.run(
            ["ngspice", "-b", "main.cir"],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout
    except subprocess.CalledProcessError as e:
        # Physics Check: If the circuit is so broken it won't simulate (e.g. short circuit)
        return {
            "scores": {"scores": [{"metric": EVALUATION_METRIC, "score": 0.0}]},
            "insights": {"insights": [{"label": "Simulation Error", "text": "Circuit failed to converge (invalid physics)"}]}
        }

    # Regex for parsing measurements
    max_match = re.search(r"max_out\s*=\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)", output)
    min_match = re.search(r"min_out\s*=\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)", output)
    pwr_match = re.search(r"avg_current\s*=\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)", output)

    if max_match and min_match and pwr_match:
        max_v = float(max_match.group(1))
        min_v = float(min_match.group(1))
        # Current from VDD is usually negative in SPICE (flowing out), so take absolute
        avg_pwr = abs(float(pwr_match.group(1)) * 5.0) 
        
        pk_to_pk = max_v - min_v
        gain = pk_to_pk / 0.02
        
        # --- PHYSICAL INTEGRITY CHECKS ---
        
        # 1. Clipping Check: If output hits 4.9V or 0.1V, the gain is fake/distorted.
        if max_v > V_MAX_SAFE or min_v < V_MIN_SAFE:
            # Calculate how much it "poked" out of the safe zone
            over_top = max(0, max_v - V_MAX_SAFE)
            under_bottom = max(0, V_MIN_SAFE - min_v)
            clipping_severity = over_top + under_bottom
            
            # Dynamic Penalty: The more it clips, the lower the score.
            # We use an exponential penalty so it drops off quickly.
            penalty = 0.1 / (1 + clipping_severity**2)
            score = gain * penalty
            
            label = "Clipping Detected"
            text = f"Output hit rails (Severity: {clipping_severity:.2f}). Penalty applied."
        
        # 2. Dead Circuit Check: If gain is effectively zero
        elif gain < 0.1:
            score = None
            label = "No Amplification"
            text = "Circuit is powered but provides no gain."
            
        else:
            # 3. Efficiency Check: We want high gain, but lower power consumption.
            # We divide gain by (1 + power_in_milliwatts) to reward efficiency.
            efficiency_factor = 1 + (avg_pwr * 1000) 
            score = gain / efficiency_factor
            label = "Success"
            text = f"Gain: {gain:.2f}, Power: {avg_pwr*1000:.2f}mW"

    else:
        score = None
        label = "Parse Error"
        text = "Could not find measurements in ngspice output."

    return {
        "scores": {"scores": [{"metric": EVALUATION_METRIC, "score": score}]},
        "insights": {"insights": [{"label": label, "text": text}]}
    }
