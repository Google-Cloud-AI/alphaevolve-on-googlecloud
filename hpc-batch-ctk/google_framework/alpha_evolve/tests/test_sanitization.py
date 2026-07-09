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

"""Unit tests for evaluation score sanitization."""

import math
import pytest
from alpha_evolve.utils import sanitize_score_value, sanitize_evaluation_scores


def test_sanitize_score_value():
    # Sanitization checks
    assert sanitize_score_value(float("inf")) == -1e12
    assert sanitize_score_value(float("-inf")) == -1e12
    assert sanitize_score_value(float("nan")) == -1e12
    
    # Finite values should remain unchanged
    assert sanitize_score_value(0.0) == 0.0
    assert sanitize_score_value(1.23) == 1.23
    assert sanitize_score_value(-45.67) == -45.67
    assert sanitize_score_value(100) == 100
    assert sanitize_score_value(None) is None
    
    # Non-numeric types should be returned unmodified
    assert sanitize_score_value("string_value") == "string_value"
    assert sanitize_score_value([1, 2]) == [1, 2]


def test_sanitize_structured_evaluation():
    evaluation = {
        "scores": {
            "scores": [
                {"metric": "my_custom_score", "score": float("inf")},
                {"metric": "another_score", "score": 12.34},
                {"metric": "error_score", "score": float("nan")}
            ]
        },
        "insights": {
            "insights": [{"label": "ERROR", "text": "Diverged"}]
        }
    }
    
    sanitized = sanitize_evaluation_scores(evaluation)
    
    scores = sanitized["scores"]["scores"]
    assert scores[0]["metric"] == "my_custom_score"
    assert scores[0]["score"] == -1e12
    
    assert scores[1]["metric"] == "another_score"
    assert scores[1]["score"] == 12.34  # Unchanged
    
    assert scores[2]["metric"] == "error_score"
    assert scores[2]["score"] == -1e12


def test_sanitize_legacy_evaluation():
    evaluation = {
        "custom_metric": float("inf"),
        "secondary_metric": -0.05,
        "null_metric": float("-inf"),
        "insights": "should not be touched"
    }
    
    sanitized = sanitize_evaluation_scores(evaluation)
    
    assert sanitized["custom_metric"] == -1e12
    assert sanitized["secondary_metric"] == -0.05  # Unchanged
    assert sanitized["null_metric"] == -1e12
    assert sanitized["insights"] == "should not be touched"  # Unchanged
