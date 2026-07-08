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
Evaluator for C++ adaptive sorting example using Cloud Functions.
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
HARNESS_PATH = THIS_FILE_DIR / "src" / "main.cpp"
HARNESS_CODE = _load_file_content(HARNESS_PATH)


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

    payload = {
        "files": files,
        "harness": HARNESS_CODE,
    }

    headers = {"Content-Type": "application/json"}

    try:
        import google.auth
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        auth_req = GoogleRequest()
        target_audience = EVALUATOR_URL
        if target_audience != "http://localhost:8080":
            # Only attempt to get token if we have credentials
            # This avoids noise in logs if running locally/unauthenticated
            try:
                token = id_token.fetch_id_token(auth_req, target_audience)
                headers["Authorization"] = f"Bearer {token}"
            except Exception as e:
                logger.debug(
                    f"Could not fetch ID token (safe to ignore if unauthenticated allowed): {e}"
                )

    except ImportError:
        logger.debug("google-auth not installed, using unauthenticated request")
    except Exception as e:
        logger.debug(f"Auth setup failed: {e}")

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
