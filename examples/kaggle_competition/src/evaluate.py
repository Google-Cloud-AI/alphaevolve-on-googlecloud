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
"""Client-side evaluator for the Zillow Prize Kaggle competition.

Posts evolved ML pipeline code to a Cloud Run evaluator service, which
loads the Zillow dataset, executes the candidate code, and returns
evaluation metrics (neg_mae) + insights.
"""

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

METRIC_NAME = "neg_mae"

EVALUATOR_URL = os.getenv("EVALUATOR_URL")
if not EVALUATOR_URL:
    raise ValueError("The EVALUATOR_URL environment variable must be set.")


def zillow_evaluation_function(program_candidate) -> dict:
    """Evaluate a candidate program using the remote Cloud Run evaluator.

    Args:
        program_candidate: Dict with program content from AlphaEvolve.
            Expected structure: {"content": {"files": [{"path": ..., "content": ...}]}}

    Returns:
        Flat dict of metrics (e.g., {"neg_mae": -0.065, ...})
        compatible with AlphaEvolveExperiment.evaluator() auto-wrapping.
    """
    files = program_candidate.get("content", {}).get("files", [])
    if not files:
        return {
            "scores": {"scores": []},
            "insights": {
                "insights": [
                    {
                        "label": "Invalid Program",
                        "text": "No files found in the program candidate.",
                    }
                ]
            },
        }

    payload = {"files": files}

    # Get OIDC token for Cloud Run authentication
    try:
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
        logger.warning(f"Failed to fetch ID token: {e}")
        headers = {"Content-Type": "application/json"}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(EVALUATOR_URL, data=data, headers=headers)

    logger.debug(
        "Sending evaluation request to %s (payload size: %d bytes)",
        EVALUATOR_URL,
        len(data),
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            resp_body = response.read().decode("utf-8")
            result_json = json.loads(resp_body)

            # Check for top-level error
            if "error" in result_json and "metrics" not in result_json:
                return {
                    "scores": {"scores": []},
                    "insights": {
                        "insights": [
                            {
                                "label": "Evaluator Error",
                                "text": result_json["error"],
                            }
                        ]
                    },
                }

            # If the response contains insights (from failure), return structured
            if "insights" in result_json:
                metrics = result_json.get("metrics", {})
                scores = []
                for k, v in metrics.items():
                    try:
                        scores.append({"metric": k, "score": float(v) if v is not None else 0.0})
                    except (TypeError, ValueError):
                        scores.append({"metric": k, "score": 0.0})

                return {
                    "scores": {"scores": scores},
                    "insights": result_json["insights"],
                }

            # Success: return flat metrics dict
            metrics = result_json.get("metrics", {})
            flat_metrics = {}
            for k, v in metrics.items():
                try:
                    flat_metrics[k] = float(v) if v is not None else 0.0
                except (TypeError, ValueError):
                    flat_metrics[k] = 0.0

            return flat_metrics

    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        logger.error(f"HTTP Error {e.code}: {err_content}")
        return {
            "scores": {"scores": []},
            "insights": {
                "insights": [
                    {
                        "label": "HTTP Error",
                        "text": f"Evaluator returned HTTP {e.code}: {err_content[:500]}",
                    }
                ]
            },
        }
    except urllib.error.URLError as e:
        logger.error(f"URL Error: {e.reason}")
        return {
            "scores": {"scores": []},
            "insights": {
                "insights": [
                    {
                        "label": "Connection Error",
                        "text": f"Could not reach evaluator: {e.reason}",
                    }
                ]
            },
        }
    except Exception as e:
        logger.error(f"Client exception: {str(e)}")
        return {
            "scores": {"scores": []},
            "insights": {
                "insights": [
                    {
                        "label": "Client Error",
                        "text": f"Evaluation client error: {str(e)}",
                    }
                ]
            },
        }
