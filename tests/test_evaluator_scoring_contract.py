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

"""Scoring-contract tests across the example evaluators.

Covers only what the minimal-adoption pass claims: a failed candidate is scored with a finite
penalty rather than None, 0.0 or +/-inf, and a successful one is unchanged.
"""

import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("EVALUATOR_URL", "http://localhost:9999")

from alpha_evolve import scoring
from examples.adaptive_sort import evaluator as rust_evaluator
from examples.adaptive_sort_cpp import evaluator as cpp_evaluator
from examples.circle_packing.src import evaluate as circle_packing
from examples.signal_processing.src import evaluate as signal_processing
from examples.tsp.src import evaluate as tsp

CRASHING_PROGRAM = 'def evaluate(eval_inputs): raise ValueError("boom")'
EMPTY_PROGRAM = "x = 1"


def candidate(source):
    return {"content": {"files": [{"path": "main.py", "content": source}]}}


def first_score(evaluation):
    return evaluation["scores"]["scores"][0]["score"]


def all_scores(evaluation):
    return {s["metric"]: s["score"] for s in evaluation["scores"]["scores"]}


LOCAL_EVALUATORS = [
    pytest.param(circle_packing.circle_packing_evaluation, id="circle_packing"),
    pytest.param(tsp.tsp_evaluation_function, id="tsp"),
    pytest.param(signal_processing.signal_processing_evaluation, id="signal_processing"),
]


# ---------------------------------------------------------------------------
# Local evaluators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("evaluate_fn", LOCAL_EVALUATORS)
@pytest.mark.parametrize("source", [CRASHING_PROGRAM, EMPTY_PROGRAM])
def test_local_failure_is_a_finite_penalty(evaluate_fn, source):
    score = first_score(evaluate_fn(candidate(source)))
    assert score is not None, "a failed candidate must be scored, not left unscored"
    assert score != 0.0, "0.0 outranks every real score when good values are negative"
    assert score == scoring.HARD_PENALTY


@pytest.mark.parametrize("evaluate_fn", LOCAL_EVALUATORS)
def test_local_evaluator_never_raises_on_a_broken_candidate(evaluate_fn):
    # signal_processing used to raise UnboundLocalError here, submitting nothing at all.
    evaluation = evaluate_fn(candidate(EMPTY_PROGRAM))
    assert "scores" in evaluation
    assert evaluation["scores"]["scores"]


@pytest.mark.parametrize("evaluate_fn", LOCAL_EVALUATORS)
def test_local_evaluator_emits_only_forwarded_keys(evaluate_fn):
    # workers.py filters a submission to {"scores", "insights"}; anything else is dropped.
    assert set(evaluate_fn(candidate(CRASHING_PROGRAM))) <= {"scores", "insights"}


def test_circle_packing_infeasible_packing_is_penalized_not_infinite():
    source = 'def evaluate(eval_inputs): return {"sum_of_radii": -float("inf")}'
    assert first_score(circle_packing.circle_packing_evaluation(candidate(source))) == (
        scoring.HARD_PENALTY
    )


def test_tsp_invalid_tour_is_penalized_not_infinite():
    source = 'def evaluate(eval_inputs): return {"neg_tour_length": -float("inf")}'
    assert first_score(tsp.tsp_evaluation_function(candidate(source))) == scoring.HARD_PENALTY


def test_successful_score_passes_through_unchanged():
    source = 'def evaluate(eval_inputs): return {"neg_tour_length": -6.25}'
    assert first_score(tsp.tsp_evaluation_function(candidate(source))) == pytest.approx(-6.25)


# ---------------------------------------------------------------------------
# Remote clients
# ---------------------------------------------------------------------------

REMOTE_EVALUATORS = [
    pytest.param(rust_evaluator.adaptive_sort_evaluation, id="adaptive_sort"),
    pytest.param(cpp_evaluator.adaptive_sort_evaluation, id="adaptive_sort_cpp"),
]


def respond_with(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    return patch("urllib.request.urlopen", return_value=response)


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
def test_remote_metrics_pass_through_unchanged(evaluate_fn):
    with respond_with({"metrics": {"score": 0.42, "avg_time": 0.003}}):
        scores = all_scores(evaluate_fn(candidate("x")))
    assert scores == {"score": 0.42, "avg_time": 0.003}


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
def test_remote_preserves_every_reported_metric(evaluate_fn):
    reported = {
        "score": 0.4,
        "compile_success": 1.0,
        "correctness": 1.0,
        "performance_score": 0.9,
        "adaptability_score": 0.8,
        "avg_time": 0.002,
        "memory_safe": 1.0,
    }
    with respond_with({"metrics": reported}):
        assert set(all_scores(evaluate_fn(candidate("x")))) == set(reported)


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
def test_remote_null_metric_is_penalized_not_zeroed(evaluate_fn):
    with respond_with({"metrics": {"score": 0.5, "avg_time": None}}):
        scores = all_scores(evaluate_fn(candidate("x")))
    assert scores["avg_time"] == scoring.HARD_PENALTY


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_remote_non_finite_metric_is_penalized(evaluate_fn, value):
    with respond_with({"metrics": {"score": value}}):
        assert all_scores(evaluate_fn(candidate("x")))["score"] == scoring.HARD_PENALTY


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
def test_compiler_stderr_reaches_the_prompt_as_an_insight(evaluate_fn):
    # The whole point of the artifacts -> insights move: workers.py drops "artifacts", so
    # build errors never reached the model.
    with respond_with(
        {
            "metrics": {"score": 0.0, "compile_success": 0.0},
            "artifacts": {"error": "Compilation failed", "stderr": "expected `;`"},
        }
    ):
        evaluation = evaluate_fn(candidate("x"))
    texts = " ".join(i["text"] for i in evaluation["insights"]["insights"])
    assert "expected `;`" in texts
    assert set(evaluation) <= {"scores", "insights"}


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
def test_unreachable_service_leaves_the_candidate_unscored(evaluate_fn):
    # An outage says nothing about the candidate, so it must not be penalized.
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        evaluation = evaluate_fn(candidate("x"))
    assert all_scores(evaluation) == {rust_evaluator.PRIMARY_METRIC: None}
    assert evaluation["insights"]["insights"][0]["label"] == "evaluator_error"


@pytest.mark.parametrize("evaluate_fn", REMOTE_EVALUATORS)
def test_missing_files_are_penalized_without_calling_the_service(evaluate_fn):
    with patch("urllib.request.urlopen") as urlopen:
        evaluation = evaluate_fn({"content": {"files": []}})
    urlopen.assert_not_called()
    assert first_score(evaluation) == scoring.HARD_PENALTY
