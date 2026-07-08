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
"""
Evaluator for the Real-Time Adaptive Signal Processing Algorithm

This evaluator implements the multi-objective optimization function defined in the specification:
J(θ) = α₁·S(θ) + α₂·L_recent(θ) + α₃·L_avg(θ) + α₄·R(θ)

Where:
- S(θ): Slope change penalty - counts directional reversals
- L_recent(θ): Instantaneous lag error - |y[n] - x[n]|
- L_avg(θ): Average tracking error over window
- R(θ): False reversal penalty - mismatched trend changes
- α₁=0.3, α₂=α₃=0.2, α₄=0.3: Weighting coefficients
"""

import concurrent.futures
import json
import logging
import os
import re
import time
from collections import deque

import numpy as np
from scipy import signal
from scipy.stats import pearsonr

logger = logging.getLogger(__name__)


def run_with_timeout(func, args=(), kwargs={}, timeout_seconds=30):
    """
    Run a function with a timeout using concurrent.futures
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            result = future.result(timeout=timeout_seconds)
            return result
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Function timed out after {timeout_seconds} seconds")


def safe_float(value):
    """Convert a value to float safely"""
    try:
        if np.isnan(value) or np.isinf(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def calculate_slope_changes(signal_data):
    """
    Calculate slope change penalty S(θ) - counts directional reversals

    Args:
        signal_data: 1D array of signal values

    Returns:
        Number of slope changes (directional reversals)
    """
    if len(signal_data) < 3:
        return 0

    # Calculate differences
    diffs = np.diff(signal_data)

    # Count sign changes in consecutive differences
    sign_changes = 0
    for i in range(1, len(diffs)):
        if np.sign(diffs[i]) != np.sign(diffs[i - 1]) and diffs[i - 1] != 0:
            sign_changes += 1

    return sign_changes


def calculate_lag_error(filtered_signal, original_signal, window_size):
    """
    Calculate instantaneous lag error L_recent(θ) = |y[n] - x[n]|

    Args:
        filtered_signal: Output of the filter
        original_signal: Original input signal
        window_size: Size of the processing window

    Returns:
        Instantaneous lag error at the most recent sample
    """
    if len(filtered_signal) == 0:
        return 1.0  # Maximum penalty

    # Account for processing delay
    delay = window_size - 1
    if len(original_signal) <= delay:
        return 1.0

    # Compare the last filtered sample with the corresponding original sample
    recent_filtered = filtered_signal[-1]
    match_index = min(delay + len(filtered_signal) - 1, len(original_signal) - 1)
    recent_original = original_signal[match_index]

    return abs(recent_filtered - recent_original)


def calculate_average_tracking_error(filtered_signal, original_signal, window_size):
    """
    Calculate average tracking error L_avg(θ) over the window

    Args:
        filtered_signal: Output of the filter
        original_signal: Original input signal
        window_size: Size of the processing window

    Returns:
        Average absolute error over the processed samples
    """
    if len(filtered_signal) == 0:
        return 1.0  # Maximum penalty

    # Account for processing delay
    delay = window_size - 1
    if len(original_signal) <= delay:
        return 1.0

    # Align signals
    aligned_original = original_signal[delay : delay + len(filtered_signal)]

    # Ensure same length
    min_length = min(len(filtered_signal), len(aligned_original))
    if min_length == 0:
        return 1.0

    filtered_aligned = filtered_signal[:min_length]
    original_aligned = aligned_original[:min_length]

    # Calculate mean absolute error
    return np.mean(np.abs(filtered_aligned - original_aligned))


def calculate_false_reversal_penalty(filtered_signal, clean_signal, window_size):
    """
    Calculate false reversal penalty R(θ) - mismatched trend changes

    Args:
        filtered_signal: Output of the filter
        clean_signal: Ground truth clean signal
        window_size: Size of the processing window

    Returns:
        Penalty for trend changes that don't match the clean signal
    """
    if len(filtered_signal) < 3 or len(clean_signal) < 3:
        return 0

    # Account for processing delay
    delay = window_size - 1
    if len(clean_signal) <= delay:
        return 1.0

    # Align signals
    aligned_clean = clean_signal[delay : delay + len(filtered_signal)]
    min_length = min(len(filtered_signal), len(aligned_clean))

    if min_length < 3:
        return 0

    filtered_aligned = filtered_signal[:min_length]
    clean_aligned = aligned_clean[:min_length]

    # Calculate trend changes for both signals
    filtered_diffs = np.diff(filtered_aligned)
    clean_diffs = np.diff(clean_aligned)

    # Count mismatched trend changes
    false_reversals = 0
    for i in range(1, len(filtered_diffs)):
        # Check if there's a trend change in filtered signal
        filtered_change = (
            np.sign(filtered_diffs[i]) != np.sign(filtered_diffs[i - 1])
            and filtered_diffs[i - 1] != 0
        )

        # Check if there's a corresponding trend change in clean signal
        clean_change = (
            np.sign(clean_diffs[i]) != np.sign(clean_diffs[i - 1]) and clean_diffs[i - 1] != 0
        )

        # Count as false reversal if filtered has change but clean doesn't
        if filtered_change and not clean_change:
            false_reversals += 1

    return false_reversals


def calculate_composite_score(S, L_recent, L_avg, R, alpha=[0.3, 0.2, 0.2, 0.3]):
    """
    Calculate the composite metric J(θ) = α₁·S(θ) + α₂·L_recent(θ) + α₃·L_avg(θ) + α₄·R(θ)

    All metrics are normalized and converted to penalties (higher = worse)
    The final score is converted to a maximization problem (higher = better)
    """
    # Normalize slope changes (typical range 0-100)
    S_norm = min(S / 50.0, 2.0)

    # Lag errors are already in reasonable range (0-10 typically)
    L_recent_norm = min(L_recent, 2.0)
    L_avg_norm = min(L_avg, 2.0)

    # Normalize false reversals (typical range 0-50)
    R_norm = min(R / 25.0, 2.0)

    # Calculate weighted penalty
    penalty = (
        alpha[0] * S_norm + alpha[1] * L_recent_norm + alpha[2] * L_avg_norm + alpha[3] * R_norm
    )

    # Convert to maximization score (higher is better)
    score = 1.0 / (1.0 + penalty)

    return score


def generate_test_signals(num_signals=5):
    """
    Generate multiple test signals with different characteristics
    """
    test_signals = []

    for i in range(num_signals):
        np.random.seed(42 + i)  # Different seed for each signal
        length = 500 + i * 100  # Varying lengths
        noise_level = 0.2 + i * 0.1  # Varying noise levels

        t = np.linspace(0, 10, length)

        # Different signal characteristics
        if i == 0:
            # Smooth sinusoidal with trend
            clean = 2 * np.sin(2 * np.pi * 0.5 * t) + 0.1 * t
        elif i == 1:
            # Multiple frequency components
            clean = (
                np.sin(2 * np.pi * 0.5 * t)
                + 0.5 * np.sin(2 * np.pi * 2 * t)
                + 0.2 * np.sin(2 * np.pi * 5 * t)
            )
        elif i == 2:
            # Non-stationary with changing frequency
            clean = np.sin(2 * np.pi * (0.5 + 0.2 * t) * t)
        elif i == 3:
            # Step changes
            clean = np.concatenate(
                [
                    np.ones(length // 3),
                    2 * np.ones(length // 3),
                    0.5 * np.ones(length - 2 * (length // 3)),
                ]
            )
        else:
            # Random walk with trend
            clean = np.cumsum(np.random.randn(length) * 0.1) + 0.05 * t

        # Add noise
        noise = np.random.normal(0, noise_level, length)
        noisy = clean + noise

        test_signals.append((noisy, clean))

    return test_signals


def evaluate(process_signal_func):
    """
    Evaluate the signal processing function on multiple test signals
    and calculate the composite performance metric.
    """
    # Generate test signals
    test_signals = generate_test_signals(5)

    # Collect metrics across all test signals
    all_scores = []
    all_metrics = []
    successful_runs = 0
    # Calculate metrics using the generated test signal
    window_size = 20

    insights = []
    for i, (noisy_signal, clean_signal) in enumerate(test_signals):
        try:
            # Run the algorithm with timeout
            start_time = time.time()

            # Call the program's main function
            filtered_signal = run_with_timeout(
                process_signal_func,
                kwargs={
                    "input_signal": noisy_signal,
                    "window_size": window_size,
                },
                timeout_seconds=10,
            )

            execution_time = time.time() - start_time

            # Validate result format
            if not isinstance(filtered_signal, np.ndarray):
                logger.error(f"Signal {i}: Invalid result format. Must be a numpy array.")
                insights.append(
                    {
                        "label": "evaluation_error",
                        "text": f"Signal {i}: Invalid result format. Must be a numpy array.",
                    }
                )
                continue

            if len(filtered_signal) == 0:
                logger.error(f"Signal {i}: Empty filtered signal")
                insights.append(
                    {"label": "evaluation_error", "text": f"Signal {i}: Empty filtered signal"}
                )
                continue

            # Calculate all penalty components
            S = calculate_slope_changes(filtered_signal)
            L_recent = calculate_lag_error(filtered_signal, noisy_signal, window_size)
            L_avg = calculate_average_tracking_error(filtered_signal, noisy_signal, window_size)
            R = calculate_false_reversal_penalty(filtered_signal, clean_signal, window_size)

            # Calculate composite score
            composite_score = calculate_composite_score(S, L_recent, L_avg, R)

            # Additional quality metrics
            correlation = 0.0
            noise_reduction = 0.0

            try:
                # Calculate correlation with clean signal
                delay = window_size - 1
                aligned_clean = clean_signal[delay : delay + len(filtered_signal)]
                min_length = min(len(filtered_signal), len(aligned_clean))

                if min_length > 1:
                    corr_result = pearsonr(filtered_signal[:min_length], aligned_clean[:min_length])
                    correlation = corr_result[0] if not np.isnan(corr_result[0]) else 0.0

                # Calculate noise reduction
                aligned_noisy = noisy_signal[delay : delay + len(filtered_signal)]
                aligned_noisy = aligned_noisy[:min_length]
                aligned_clean = aligned_clean[:min_length]

                if min_length > 0:
                    noise_before = np.var(aligned_noisy - aligned_clean)
                    noise_after = np.var(filtered_signal[:min_length] - aligned_clean)
                    noise_reduction = (
                        (noise_before - noise_after) / noise_before if noise_before > 0 else 0
                    )
                    noise_reduction = max(0, noise_reduction)  # Ensure non-negative

            except Exception as e:
                logger.error(f"Signal {i}: Error calculating additional metrics: {e}")
                insights.append(
                    {
                        "label": "evaluation_error",
                        "text": f"Signal {i}: Error calculating additional metrics: {e}",
                    }
                )

            # Store metrics
            metrics = {
                "slope_changes": safe_float(S),
                "lag_error": safe_float(L_recent),
                "avg_error": safe_float(L_avg),
                "false_reversals": safe_float(R),
                "composite_score": safe_float(composite_score),
                "correlation": safe_float(correlation),
                "noise_reduction": safe_float(noise_reduction),
                "execution_time": safe_float(execution_time),
                "signal_length": len(filtered_signal),
            }

            all_scores.append(composite_score)
            all_metrics.append(metrics)
            successful_runs += 1

        except TimeoutError:
            logger.error(f"Signal {i}: Timeout")
            insights.append({"label": "evaluation_error", "text": f"Signal {i}: Timeout"})
            continue
        except Exception as e:
            logger.error(f"Signal {i}: Error - {str(e)}")
            insights.append({"label": "evaluation_error", "text": f"Signal {i}: Error - {str(e)}"})
            continue

    # If no successful runs, return minimal scores
    if successful_runs == 0:
        insights.append(
            {"label": "evaluation_error", "text": "All test signals failed during evaluation."}
        )
        return {"overall_score": None}, insights

    # Calculate aggregate metrics
    avg_composite_score = np.mean(all_scores)
    avg_slope_changes = np.mean([m["slope_changes"] for m in all_metrics])
    avg_lag_error = np.mean([m["lag_error"] for m in all_metrics])
    avg_avg_error = np.mean([m["avg_error"] for m in all_metrics])
    avg_false_reversals = np.mean([m["false_reversals"] for m in all_metrics])
    avg_correlation = np.mean([m["correlation"] for m in all_metrics])
    avg_noise_reduction = np.mean([m["noise_reduction"] for m in all_metrics])
    avg_execution_time = np.mean([m["execution_time"] for m in all_metrics])
    success_rate = successful_runs / len(test_signals)

    # Calculate additional derived scores
    smoothness_score = 1.0 / (1.0 + avg_slope_changes / 20.0)  # Higher is better
    responsiveness_score = 1.0 / (1.0 + avg_lag_error)  # Higher is better
    accuracy_score = max(0, avg_correlation)  # 0-1, higher is better
    efficiency_score = min(1.0, 1.0 / max(0.001, avg_execution_time))  # Speed bonus

    # Overall score combining multiple factors
    overall_score = (
        0.4 * avg_composite_score  # Primary metric
        + 0.2 * smoothness_score  # Smoothness
        + 0.2 * accuracy_score  # Correlation with clean signal
        + 0.1 * avg_noise_reduction  # Noise reduction capability
        + 0.1 * success_rate  # Reliability
    )

    insights.append(
        {
            "label": "evaluation_success",
            "text": f"Successful runs: {successful_runs} / {len(test_signals)}",
        }
    )
    return {
        "composite_score": safe_float(avg_composite_score),
        "overall_score": safe_float(overall_score),  # Primary selection metric
        "slope_changes": safe_float(avg_slope_changes),
        "lag_error": safe_float(avg_lag_error),
        "avg_error": safe_float(avg_avg_error),
        "false_reversals": safe_float(avg_false_reversals),
        "correlation": safe_float(avg_correlation),
        "noise_reduction": safe_float(avg_noise_reduction),
        "smoothness_score": safe_float(smoothness_score),
        "responsiveness_score": safe_float(responsiveness_score),
        "accuracy_score": safe_float(accuracy_score),
        "efficiency_score": safe_float(efficiency_score),
        "execution_time": safe_float(avg_execution_time),
        "success_rate": safe_float(success_rate),
    }, insights


def save_program(evaluation: dict, program_candidate: dict, programs_dir: str = "./programs"):
    """
    Save the evaluated program candidate and its evaluation to a JSON file
    """
    archive = program_candidate.copy()
    archive["evaluation"] = evaluation

    program_uri = archive.get("name", "unknown_program_id")
    program_id = program_uri.split("/")[-1]
    match = re.search(r"alphaEvolveExperiments/([^/]+)", program_uri)
    experiment_id = match.group(1) if match else "unknown_experiment_id"

    # Save archive of evaluated program
    os.makedirs(f"{programs_dir}/{experiment_id}", mode=0o777, exist_ok=True)
    file_path = f"{programs_dir}/{experiment_id}/{program_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=True, indent=4)
        logger.info(f"Saved program and evaluation to {file_path}")


def signal_processing_evaluation(program_candidate) -> dict:
    """
    Main evaluation function that tests the signal processing algorithm
    on multiple test signals and calculates the composite performance metric.

    Args:
        program_candidate: The candidate program to evaluate

    Returns a dictionary structure compatible with AlphaEvolve checks.
    """
    logger.debug("Entering signal_processing_evaluation")
    save_program_dir = os.getenv("SAVE_PROGRAM_DIR")

    # Extract code from the candidate
    files = program_candidate.get("content", {}).get("files", [])
    if not files:
        return {
            "scores": {"scores": [{"metric": "overall_score", "score": None}]},
            "insights": {
                "insights": [{"label": "program_error", "text": "No program files in candidate"}]
            },
        }

    code = files[0]["content"]
    logger.debug("Code length: %d", len(code))

    try:
        exec_namespace = {"deque": deque, "signal": signal, "np": np}
        exec(code, exec_namespace)

        process_signal_func = exec_namespace.get("process_signal")
        if not callable(process_signal_func):
            raise Exception("Missing process_signal function")

        result_dict, insights = evaluate(process_signal_func)
        evaluation_scores = [
            {
                "metric": key,
                "score": value,
            }
            for key, value in result_dict.items()
        ]
        evaluation = {
            "scores": {"scores": evaluation_scores},
            "insights": {"insights": insights},
        }
        logger.debug("Evaluation completed with scores: %s", evaluation_scores)

        if save_program_dir:
            save_program(evaluation, program_candidate, programs_dir=save_program_dir)

    except Exception as e:
        logger.error(f"Evaluation failed: {str(e)}")
        insights.append({"label": "evaluation_error", "text": f"Evaluation failed: {str(e)}"})
        evaluation = {
            "scores": {"scores": [{"metric": "overall_score", "score": None}]},
            "insights": {"insights": insights},
        }

        if save_program_dir:
            save_program(evaluation, program_candidate, programs_dir=save_program_dir)

    finally:
        return evaluation
