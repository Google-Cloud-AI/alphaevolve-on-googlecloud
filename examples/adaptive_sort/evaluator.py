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

logger = logging.getLogger(__name__)

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
        return {
            "scores": {"scores": []},
            "artifacts": {"error": "No files in candidate"},
        }

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
                    return {
                        "scores": {"scores": []},
                        "artifacts": {"error": result_json["error"]},
                    }

            # Convert metrics to the expected list format
            metrics_dict = result_json.get("metrics", {})
            logger.debug(f"metrics_dict keys: {list(metrics_dict.keys())}")
            logger.debug(
                f"metrics_dict sample val type: {type(list(metrics_dict.values())[0]) if metrics_dict else 'Empty'}"
            )

            scores_list = []
            for k, v in metrics_dict.items():
                try:
                    val = float(v) if v is not None else 0.0
                    scores_list.append({"metric": k, "score": val})
                except Exception as e:
                    logger.error(f"converting metric {k} with value {v}: {e}")
                    # If we can't convert, skip or handle?
                    # For now, let's include it as 0.0 but log error to see what's happening
                    scores_list.append({"metric": k, "score": 0.0})

            # Simplify return to flat dict as expected by AlphaEvolveExperiment
            flat_metrics = {}
            for k, v in metrics_dict.items():
                try:
                    flat_metrics[k] = float(v) if v is not None else 0.0
                except Exception:
                    flat_metrics[k] = 0.0

            return flat_metrics

    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        return {
            "scores": {"scores": []},
            "artifacts": {"error": f"HTTP Error {e.code}: {err_content}"},
        }
    except urllib.error.URLError as e:
        return {
            "scores": {"scores": []},
            "artifacts": {"error": f"URL Error: {e.reason}"},
        }
    except Exception as e:
        return {
            "scores": {"scores": []},
            "artifacts": {"error": f"Client exception: {str(e)}"},
        }