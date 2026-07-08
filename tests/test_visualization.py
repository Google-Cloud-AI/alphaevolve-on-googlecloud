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

from alpha_evolve.visualization import get_score


def test_get_score_success():
    prog = {
        "evaluation": {
            "scores": {
                "scores": [
                    {"metric": "my_metric", "score": 0.85},
                    {"metric": "other_metric", "score": 0.1},
                ]
            }
        }
    }
    assert get_score(prog, "my_metric") == 0.85
    assert get_score(prog, "other_metric") == 0.1
    assert get_score(prog, "non_existent") == -float("inf")


def test_get_score_missing_keys():
    assert get_score({}, "metric") == -float("inf")
    assert get_score({"evaluation": {}}, "metric") == -float("inf")


def test_get_score_invalid_types():
    # Trigger TypeError or ValueError
    prog = {
        "evaluation": {
            "scores": {"scores": [{"metric": "my_metric", "score": "invalid_score"}]}
        }
    }
    assert get_score(prog, "my_metric") == -float("inf")

    prog_malformed = {"evaluation": {"scores": "not_a_dict"}}
    assert get_score(prog_malformed, "metric") == -float("inf")
