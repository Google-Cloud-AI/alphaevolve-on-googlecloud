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

"""Tests for the shared scoring helpers used by the example evaluators."""

import json
import logging
import math

import pytest

from alpha_evolve import scoring


# ---------------------------------------------------------------------------
# The band ordering, which is the whole point of the module
# ---------------------------------------------------------------------------


def test_bands_are_ordered_hard_then_soft_then_objective():
    ordered = [
        scoring.hard_penalty(),
        scoring.soft_penalty(9),
        scoring.soft_penalty(1),
        scoring.finite_score(-6.03),
        scoring.finite_score(12.4),
    ]
    assert ordered == sorted(ordered)


def test_failure_scores_are_never_zero():
    # A failure scoring 0.0 outranks every real score whenever good values are negative.
    assert scoring.hard_penalty() != 0.0
    assert scoring.soft_penalty(1) != 0.0
    assert scoring.finite_score(float("nan")) != 0.0


def test_hard_penalty_is_finite_and_negative():
    penalty = scoring.hard_penalty()
    assert penalty == scoring.HARD_PENALTY
    assert math.isfinite(penalty)
    assert penalty < 0


def test_hard_penalty_stays_below_a_large_soft_penalty():
    assert scoring.hard_penalty() < scoring.soft_penalty(10_000)


# ---------------------------------------------------------------------------
# soft_penalty
# ---------------------------------------------------------------------------


def test_soft_penalty_is_proportional_to_failures():
    assert scoring.soft_penalty(3) == 3 * scoring.SOFT_PENALTY_UNIT


def test_soft_penalty_is_monotone_so_fewer_failures_score_higher():
    assert scoring.soft_penalty(1) > scoring.soft_penalty(2) > scoring.soft_penalty(10)


def test_soft_penalty_accepts_weighted_failures():
    assert scoring.soft_penalty(0.5) == 0.5 * scoring.SOFT_PENALTY_UNIT


def test_soft_penalty_accepts_a_custom_unit():
    assert scoring.soft_penalty(2, unit=-5.0) == -10.0


@pytest.mark.parametrize("failures", [0, -1, float("nan"), float("inf")])
def test_soft_penalty_rejects_non_positive_or_non_finite_failures(failures):
    with pytest.raises(ValueError, match="failures must be"):
        scoring.soft_penalty(failures)


@pytest.mark.parametrize("unit", [0.0, 1.0])
def test_soft_penalty_rejects_a_non_negative_unit(unit):
    with pytest.raises(ValueError, match="unit must be negative"):
        scoring.soft_penalty(1, unit=unit)


# ---------------------------------------------------------------------------
# finite_score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0.0, 1.5, -6.03, 1e-9])
def test_finite_score_passes_finite_values_through(value):
    assert scoring.finite_score(value) == pytest.approx(value)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_finite_score_converts_non_finite_to_a_hard_penalty(value):
    # inf would win outright and NaN cannot be ranked, so neither may reach AlphaEvolve.
    assert scoring.finite_score(value) == scoring.HARD_PENALTY


def test_finite_score_returns_a_float_for_integer_input():
    assert isinstance(scoring.finite_score(3), float)


def test_finite_score_logs_the_metric_name_when_it_rejects_a_value(caplog):
    with caplog.at_level(logging.WARNING):
        scoring.finite_score(float("inf"), "eval_perplexity")
    assert "eval_perplexity" in caplog.text


# ---------------------------------------------------------------------------
# insight
# ---------------------------------------------------------------------------


def test_insight_builds_a_label_and_text_pair():
    assert scoring.insight("compile_error", "boom") == {
        "label": "compile_error",
        "text": "boom",
    }


def test_insight_leaves_short_text_untouched():
    text = "x" * scoring.MAX_INSIGHT_CHARS
    assert scoring.insight("stdout", text)["text"] == text


def test_insight_truncates_long_text():
    result = scoring.insight("stdout", "x" * (scoring.MAX_INSIGHT_CHARS + 500))
    assert len(result["text"]) < scoring.MAX_INSIGHT_CHARS + 500
    assert result["text"].endswith("[truncated]")


# ---------------------------------------------------------------------------
# build_evaluation
# ---------------------------------------------------------------------------


def test_build_evaluation_produces_the_submission_shape():
    evaluation = scoring.build_evaluation({"sum_of_radii": 2.63})
    assert evaluation == {"scores": {"scores": [{"metric": "sum_of_radii", "score": 2.63}]}}


def test_build_evaluation_keeps_a_none_score_as_none():
    # None marks an evaluator-side failure; it must survive rather than become 0.0 or vanish.
    evaluation = scoring.build_evaluation({"neg_eval_loss": None})
    assert evaluation["scores"]["scores"][0]["score"] is None


def test_build_evaluation_preserves_every_metric():
    scores = {"score": 0.5, "correctness": 1.0, "avg_time": 0.003}
    evaluation = scoring.build_evaluation(scores)
    reported = {entry["metric"] for entry in evaluation["scores"]["scores"]}
    assert reported == set(scores)


def test_build_evaluation_omits_insights_when_there_are_none():
    assert "insights" not in scoring.build_evaluation({"score": 1.0})
    assert "insights" not in scoring.build_evaluation({"score": 1.0}, [])


def test_build_evaluation_includes_insights_when_given():
    evaluation = scoring.build_evaluation(
        {"score": scoring.hard_penalty()},
        [scoring.insight("compile_error", "expected ';'")],
    )
    assert evaluation["insights"] == {
        "insights": [{"label": "compile_error", "text": "expected ';'"}]
    }


def test_build_evaluation_emits_only_the_keys_the_worker_forwards():
    # workers.py filters submissions to {"scores", "insights"}; anything else is dropped.
    evaluation = scoring.build_evaluation({"score": 1.0}, [scoring.insight("stdout", "hi")])
    assert set(evaluation) <= {"scores", "insights"}


def test_build_evaluation_output_is_json_serializable():
    evaluation = scoring.build_evaluation(
        {"score": scoring.soft_penalty(2), "latency": None},
        [scoring.insight("failed_cases", "2 of 10")],
    )
    assert json.loads(json.dumps(evaluation)) == evaluation


def test_build_evaluation_rejects_empty_scores():
    with pytest.raises(ValueError, match="at least one score"):
        scoring.build_evaluation({})


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_build_evaluation_rejects_non_finite_scores(value):
    # json.dumps would emit Infinity/NaN, which are not valid JSON.
    with pytest.raises(ValueError, match="finite_score"):
        scoring.build_evaluation({"score": value})
