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

"""Baseline scoring helpers shared by the AlphaEvolve example evaluators.

AlphaEvolve maximizes every metric it is given, so what an evaluator reports on *failure*
matters as much as what it reports on success. These helpers implement one convention:

* ``hard_penalty()`` -- the candidate is at fault: it did not compile, has no entry point,
  returned the wrong shape, crashed, or timed out. A large *finite* negative number. Never
  ``0.0``, which outranks every real score whenever good values are negative, and never
  ``-inf``, which is not valid JSON and breaks downstream arithmetic.
* ``soft_penalty(failures)`` -- the candidate ran but is functionally wrong. Proportional to
  the failure count, so passing 9 of 10 checks outranks passing 1 of 10.
* A plain float -- the candidate worked. Pass it through ``finite_score`` so a NaN or inf
  cannot slip in; ``inf`` would otherwise win outright.
* ``None`` -- reserved for evaluator-side or infrastructure failure (service 5xx, storage
  error, job scheduling failure). The candidate is not at fault, so leave it unscored rather
  than penalize it.

Because ``hard_penalty() < soft_penalty(n) < 0``, a broken candidate cannot outrank a working
one on the same metric.

This is deliberately a small, unopinionated baseline. Examples have their own scoring logic and
will need to extend it -- adopting these helpers does not require changing which metrics an
example reports.

    from alpha_evolve import scoring

    if not compiled:
        evaluation = scoring.build_evaluation(
            {"score": scoring.hard_penalty()},
            [scoring.insight("compile_error", stderr)],
        )
    elif failed_cases:
        evaluation = scoring.build_evaluation(
            {"score": scoring.soft_penalty(len(failed_cases))},
        )
    else:
        evaluation = scoring.build_evaluation({"score": scoring.finite_score(value)})
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

# A failed candidate must sort below every working one, while staying finite so that averages,
# plots and Pareto comparisons downstream keep working.
HARD_PENALTY: float = -1.0e9

# Penalty per failed verification check. Well above HARD_PENALTY for any realistic count, so
# "ran but wrong" always outranks "did not run".
SOFT_PENALTY_UNIT: float = -1.0e3

# Insights compete for the LLM's context window; keep each one small.
MAX_INSIGHT_CHARS: int = 2000


def hard_penalty() -> float:
    """Returns the score for a candidate that failed validation.

    Use when the candidate itself is at fault. For a failure on our side of the fence, submit
    None instead so the candidate is left unscored.
    """
    return HARD_PENALTY


def soft_penalty(failures: float, unit: float = SOFT_PENALTY_UNIT) -> float:
    """Returns a penalty proportional to the number of failed checks.

    Proportionality is the point: it gives the model a gradient to climb toward correctness
    instead of a cliff where every wrong answer scores the same.

    Args:
        failures: How many checks failed. A float, so callers can weight by severity. Must be
            positive -- a penalty of zero would score a broken candidate as well as a working
            one.
        unit: Penalty per failure. Must be negative.

    Returns:
        The penalty, always below zero.

    Raises:
        ValueError: If failures is not positive and finite, or unit is not negative.
    """
    if not math.isfinite(failures) or failures <= 0:
        raise ValueError(f"failures must be a positive finite number, got {failures}")
    if unit >= 0:
        raise ValueError(f"unit must be negative, got {unit}")
    return unit * failures


def finite_score(value: float, metric: str = "") -> float:
    """Returns value, or a hard penalty when it is not finite.

    NaN cannot be ranked and inf would win outright, so neither may reach AlphaEvolve.

    Args:
        value: The measured score.
        metric: Optional metric name, used only to make the log message useful.

    Returns:
        The value as a float, or HARD_PENALTY if it is NaN or infinite.
    """
    if not math.isfinite(value):
        logger.warning(
            "Metric %s is not finite (%s); recording a hard penalty instead.",
            metric or "<unnamed>",
            value,
        )
        return HARD_PENALTY
    return float(value)


def insight(label: str, text: str) -> Dict[str, str]:
    """Builds an insight, truncating text that would crowd the LLM's context window.

    Args:
        label: Short category, such as "compile_error" or "failed_cases".
        text: The body. Truncated to MAX_INSIGHT_CHARS.

    Returns:
        An insight dict ready to pass to build_evaluation.
    """
    if len(text) > MAX_INSIGHT_CHARS:
        text = text[:MAX_INSIGHT_CHARS] + "\n[truncated]"
    return {"label": label, "text": text}


def build_evaluation(
    scores: Mapping[str, Optional[float]],
    insights: Optional[Sequence[Mapping[str, str]]] = None,
) -> Dict[str, Any]:
    """Assembles the evaluation payload submitted to AlphaEvolve.

    Args:
        scores: Metric name to score. A value of None marks the metric unscored, which is
            reserved for evaluator-side failures.
        insights: Optional feedback forwarded to the evolution prompt. Always include the
            reason on a failure; it is the model's only channel for learning what broke.

    Returns:
        A dict of the shape ``{"scores": {"scores": [...]}, "insights": {"insights": [...]}}``,
        with the insights key omitted when there are none.

    Raises:
        ValueError: If scores is empty, or any score is NaN or infinite. Pass measured values
            through finite_score first.
    """
    if not scores:
        raise ValueError("at least one score is required")

    entries: List[Dict[str, Any]] = []
    for metric, score in scores.items():
        if score is not None and not math.isfinite(score):
            raise ValueError(
                f"score for {metric} is {score}; pass it through finite_score() first"
            )
        entries.append({"metric": metric, "score": None if score is None else float(score)})

    evaluation: Dict[str, Any] = {"scores": {"scores": entries}}
    if insights:
        evaluation["insights"] = {"insights": [dict(item) for item in insights]}
    return evaluation
