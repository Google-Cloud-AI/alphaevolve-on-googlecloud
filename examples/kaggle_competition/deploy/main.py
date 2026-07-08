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
"""Cloud Run evaluator for the Zillow Prize Kaggle competition.

Receives evolved ML pipeline code via HTTP POST, loads the Zillow dataset
from a GCS volume mount, executes the candidate code in a sandboxed
namespace, and returns evaluation metrics (neg_mae) + insights.
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Mapping, Tuple

import functions_framework
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

METRIC_NAME = "neg_mae"
EVAL_TIMEOUT = 180  # seconds

# GCS volume mount path (set via Cloud Run --add-volume-mount)
ARTIFACTS_PATH = os.environ.get("ARTIFACTS_PATH", "/mnt/artifacts")
DATA_PATH = os.path.join(ARTIFACTS_PATH, "data")

# ---------------------------------------------------------------------------
# Data loading (cached in memory across requests)
# ---------------------------------------------------------------------------

_CACHED_DATA: dict | None = None


def _load_data() -> dict:
    """Load and cache the Zillow dataset with a time-based train/val split.

    Train: transactions before 2016-10-01.
    Val:   transactions from 2016-10-01 to 2016-12-31.

    Reads from the GCS-mounted volume at ARTIFACTS_PATH/data/.
    """
    global _CACHED_DATA
    if _CACHED_DATA is not None:
        return _CACHED_DATA

    logger.info("Loading Zillow dataset from %s ...", DATA_PATH)

    # --- Properties ---
    props_path = os.path.join(DATA_PATH, "properties_2016.csv")
    if not os.path.exists(props_path):
        raise FileNotFoundError(
            f"Properties file not found: {props_path}\n"
            "Ensure the Zillow dataset is uploaded to the GCS artifacts "
            "bucket under the data/ prefix."
        )
    props = pd.read_csv(props_path, low_memory=False)

    # --- Transactions (v2 preferred, fallback to original) ---
    train_path = os.path.join(DATA_PATH, "train_2016_v2.csv")
    if not os.path.exists(train_path):
        train_path = os.path.join(DATA_PATH, "train_2016.csv")
    if not os.path.exists(train_path):
        raise FileNotFoundError(
            f"Training transactions not found in {DATA_PATH}. "
            "Expected train_2016_v2.csv or train_2016.csv."
        )
    train = pd.read_csv(train_path, parse_dates=["transactiondate"])

    # --- Merge ---
    merged = train.merge(props, on="parcelid", how="left")

    # --- Drop string/object columns ---
    for col in merged.select_dtypes(include=["object"]).columns:
        uniq = merged[col].dropna().unique()
        if set(uniq).issubset({"Y", "N", "true", "false", "1", "0", True, False}):
            merged[col] = merged[col].map(
                {"Y": 1, "N": 0, "true": 1, "false": 0, "1": 1, "0": 0}
            )
        else:
            merged = merged.drop(columns=[col])

    # --- Time-based split ---
    train_mask = merged["transactiondate"] < "2016-10-01"
    val_mask = ~train_mask

    feature_cols = [c for c in merged.columns if c != "logerror"]

    train_split = merged[train_mask]
    val_split = merged[val_mask]

    _CACHED_DATA = {
        "train_df": train_split[feature_cols].reset_index(drop=True),
        "train_target": train_split["logerror"].reset_index(drop=True),
        "val_df": val_split[feature_cols].reset_index(drop=True),
        "val_target": val_split["logerror"].values,
    }

    logger.info(
        "Data loaded: %d train, %d val samples, %d feature columns",
        len(train_split),
        len(val_split),
        len(feature_cols),
    )
    return _CACHED_DATA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_response(
    data: Dict[str, Any], status_code: int = 200
) -> Tuple[str, int, Dict[str, str]]:
    """Helper to create the flask response tuple."""
    return (
        json.dumps(data),
        status_code,
        {"Content-Type": "application/json"},
    )


def _failure_response(
    neg_mae: float | None, insight: str
) -> Tuple[str, int, Dict[str, str]]:
    """Return a structured failure response with an insight for the LLM."""
    return _create_response({
        "metrics": {
            "neg_mae": neg_mae,
        },
        "insights": {
            "insights": [
                {"label": "Evaluation Error", "text": insight}
            ]
        },
    })


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


@functions_framework.http
def evaluate_zillow(request: Any) -> Tuple[str, int, Dict[str, str]]:
    """HTTP endpoint to evaluate Zillow prediction program candidates.

    Expects JSON:
        {"files": [{"path": "main.py", "content": "..."}]}

    Returns JSON with metrics and optional insights.
    """
    try:
        request_json = request.get_json(silent=True)
        if not request_json:
            return _create_response({"error": "Invalid JSON"}, 400)

        files = request_json.get("files", [])
        if not files:
            return _create_response(
                {"error": "Missing 'files' in request"}, 400
            )

        # Find the main.py file
        main_file = None
        for f in files:
            if f.get("path", "").endswith("main.py"):
                main_file = f
                break
        if not main_file:
            main_file = files[0]

        code = main_file["content"]

        # Load data (cached across requests)
        try:
            data = _load_data()
        except FileNotFoundError as e:
            return _failure_response(
                None,
                f"Data loading error: {str(e)}",
            )

        # Execute evolved code in sandboxed namespace
        insights_list: List[Dict[str, str]] = []
        score_value = None

        try:
            exec_namespace: Dict[str, Any] = {
                "np": np,
                "pd": pd,
                "Any": Any,
                "Mapping": Mapping,
            }
            exec(code, exec_namespace)

            eval_func = exec_namespace.get("evaluate")
            if not callable(eval_func):
                return _failure_response(
                    None,
                    "The program must define a callable 'evaluate' function. "
                    f"Found: {type(exec_namespace.get('evaluate'))}",
                )

            # Run with timeout to guard against long-running models
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(eval_func, data)
                result = future.result(timeout=EVAL_TIMEOUT)

            neg_mae = result.get(METRIC_NAME)

            if neg_mae is not None and np.isfinite(neg_mae):
                score_value = float(neg_mae)
                mae = -score_value
                insights_list.append({
                    "label": "MAE",
                    "text": f"Validation MAE = {mae:.6f}",
                })
            else:
                insights_list.append({
                    "label": "Invalid Score",
                    "text": (
                        f"Score for '{METRIC_NAME}' is None or non-finite. "
                        f"Got: {neg_mae}"
                    ),
                })

            validity = result.get("validity")
            if validity is not None and validity < 1.0:
                insights_list.append({
                    "label": "Invalid Predictions",
                    "text": (
                        "Predictions have wrong length or contain "
                        "non-finite values."
                    ),
                })

        except FuturesTimeoutError:
            return _failure_response(
                None,
                f"Evaluation exceeded {EVAL_TIMEOUT}s time limit. "
                "Try a simpler model or reduce data size.",
            )
        except Exception as e:
            return _failure_response(
                None,
                f"Runtime error: {str(e)}",
            )

        response_data: Dict[str, Any] = {
            "metrics": {
                "neg_mae": score_value,
            },
        }
        if insights_list:
            response_data["insights"] = {"insights": insights_list}

        return _create_response(response_data)

    except Exception as e:
        return _create_response({"error": str(e)}, 500)
