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
Evaluator for Rust adaptive sorting example using Cloud Functions.
"""

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from alpha_evolve import scoring

logger = logging.getLogger(__name__)

PRIMARY_METRIC = "score"

# Environment variable for the Cloud Function URL
EVALUATOR_URL = os.getenv("EVALUATOR_URL")
if not EVALUATOR_URL:
    raise ValueError("The EVALUATOR_URL environment variable must be set.")

THIS_FILE_DIR = Path(os.path.dirname(os.path.realpath(__file__)))


def _load_file_content(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, "r") as f:
        return f.read()


# Pre-load harness code
HARNESS_PATH = THIS_FILE_DIR / "sort_test" / "src" / "main.rs"
CARGO_TOML_PATH = THIS_FILE_DIR / "sort_test" / "Cargo.toml"

HARNESS_CODE = _load_file_content(HARNESS_PATH)
CARGO_TOML_CONTENT = _load_file_content(CARGO_TOML_PATH)


def adaptive_sort_evaluation(program_candidate) -> dict:
    """
    Evaluates a candidate program using the remote Cloud Function.
    Returns a dictionary structure compatible with AlphaEvolve checks.
    """
    logger.debug("Entering adaptive_sort_evaluation")
    # Extract code from the candidate
    files = program_candidate.get("content", {}).get("files", [])
    if not files:
        return _failure("No files in candidate")

    # We send the list of files directly to the Cloud Function
    payload = {
        "files": files,
        "harness": HARNESS_CODE,
        "cargo_toml": CARGO_TOML_CONTENT,
    }

    # Get OIDC token
    try:
        import google.auth
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        auth_req = GoogleRequest()
        target_audience = EVALUATOR_URL
        if target_audience != "http://localhost:8080":
            token = id_token.fetch_id_token(auth_req, target_audience)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            }
        else:
            headers = {"Content-Type": "application/json"}

    except ImportError:
        logger.warning("google-auth not installed, trying without auth header")
        headers = {"Content-Type": "application/json"}
    except Exception as e:
        logger.warning(f"Failed to fetch ID token: {e}, trying without auth header")
        headers = {"Content-Type": "application/json"}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(EVALUATOR_URL, data=data, headers=headers)

    logger.debug(
        "Sending evaluation request to %s (payload size: %d)", EVALUATOR_URL, len(data)
    )

    try:
        # Timeout set to 300s to match Cloud Function roughly
        with urllib.request.urlopen(req, timeout=300) as response:
            resp_body = response.read().decode("utf-8")
            logger.debug(f"Response Body (start): {resp_body[:500]}")
            result_json = json.loads(resp_body)

            if "error" in result_json:
                # Check if it is a top-level error
                if "metrics" not in result_json and "artifacts" not in result_json:
                    return _infra_failure(result_json["error"])

            # Convert metrics to the expected list format
            metrics_dict = result_json.get("metrics", {})
            logger.debug(f"metrics_dict keys: {list(metrics_dict.keys())}")

            scores = {}
            for k, v in metrics_dict.items():
                try:
                    scores[k] = (
                        scoring.finite_score(float(v), k)
                        if v is not None
                        else scoring.hard_penalty()
                    )
                except (TypeError, ValueError) as e:
                    logger.error(f"converting metric {k} with value {v}: {e}")
                    scores[k] = scoring.hard_penalty()

            return scoring.build_evaluation(scores, _build_insights(result_json))

    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        return _infra_failure(f"HTTP Error {e.code}: {err_content}")
    except urllib.error.URLError as e:
        return _infra_failure(f"URL Error: {e.reason}")
    except Exception as e:
        return _infra_failure(f"Client exception: {str(e)}")


def _build_insights(result_json: dict) -> list:
    """Surface the service's build and run output to the evolution prompt.

    The Cloud Function returns compiler stderr, stdout and error text under an ``artifacts``
    key, which ``workers.py`` drops when it filters a submission to scores and insights. Those
    same strings are re-emitted here as insights so the model can actually see why a candidate
    failed to compile.

    Args:
        result_json: The decoded Cloud Function response.

    Returns:
        Insights for every non-empty artifact, in a stable order.
    """
    artifacts = result_json.get("artifacts") or {}
    insights = []
    for label in ("error", "stderr", "stdout", "build_output"):
        text = artifacts.get(label)
        if text:
            insights.append(scoring.insight(label, str(text)))
    return insights


def _failure(reason: str) -> dict:
    """Build an evaluation for a candidate that could not be evaluated on its own merits.

    Args:
        reason: What went wrong, forwarded to the evolution prompt.

    Returns:
        An evaluation carrying a hard penalty on the primary metric and one insight.
    """
    logger.error("Evaluation failed: %s", reason)
    return scoring.build_evaluation(
        {PRIMARY_METRIC: scoring.hard_penalty()}, [scoring.insight("error", reason)]
    )


def _infra_failure(reason: str) -> dict:
    """Build an evaluation for a failure on our side of the fence.

    An unreachable service, an HTTP error, or a client-side exception says nothing about the
    candidate, so it is left unscored rather than penalized. Penalizing here would teach the
    search to avoid perfectly good candidates whenever the evaluator flakes.

    Args:
        reason: What went wrong, forwarded to the evolution prompt.

    Returns:
        An evaluation with the primary metric unscored and one insight.
    """
    logger.error("Evaluator unavailable: %s", reason)
    return scoring.build_evaluation(
        {PRIMARY_METRIC: None}, [scoring.insight("evaluator_error", reason)]
    )