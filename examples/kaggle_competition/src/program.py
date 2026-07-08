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

"""Zillow Prize: Zestimate Logerror Prediction — seed algorithm for AlphaEvolve.

Predict the log-error between Zillow's Zestimate and the actual sale price for
homes in Los Angeles, Orange, and Ventura counties. The EVOLVE-BLOCK contains
``build_and_predict()`` which AlphaEvolve will evolve to minimise MAE.
"""

from typing import Any, Mapping

import numpy as np
import pandas as pd


# EVOLVE-BLOCK-START

def build_and_predict(
    train_df: pd.DataFrame,
    train_target: pd.Series,
    val_df: pd.DataFrame,
) -> np.ndarray:
    """Build an ML model and predict logerror for validation properties.

    Args:
        train_df: Property features for training samples. Contains numeric
            columns (bathroomcnt, bedroomcnt, calculatedfinishedsquarefeet,
            yearbuilt, latitude, longitude, taxvaluedollarcnt, etc.) and
            some categorical/string columns. Many values are NaN.
        train_target: logerror values for training samples (float, mean ~0).
        val_df: Property features for validation samples (same columns as
            train_df).

    Returns:
        numpy array of predicted logerror values, same length as val_df.
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    # Select numeric columns only
    numeric_cols = train_df.select_dtypes(include=[np.number]).columns.tolist()

    # Drop columns with too many missing values (>50%)
    keep_cols = [
        c for c in numeric_cols if train_df[c].isna().mean() < 0.5
    ]

    X_train = train_df[keep_cols].fillna(0).values
    X_val = val_df[keep_cols].fillna(0).values
    y_train = train_target.values

    # Scale features
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)

    # Train Ridge regression
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    return model.predict(X_val)

# EVOLVE-BLOCK-END


# ---------------------------------------------------------------------------
# Evaluation helpers — OUTSIDE the evolve block (never modified by the LLM)
# ---------------------------------------------------------------------------


def evaluate(eval_inputs: Mapping[str, Any]) -> dict[str, float]:
    """Evaluate the build_and_predict function on the validation set.

    Args:
        eval_inputs: dict with keys ``train_df``, ``train_target``,
            ``val_df``, and ``val_target``.

    Returns:
        Dictionary with metrics:
        - neg_mae: negative Mean Absolute Error (higher is better).
        - validity: 1.0 if predictions are well-formed, else 0.0.
    """
    train_df = eval_inputs["train_df"]
    train_target = eval_inputs["train_target"]
    val_df = eval_inputs["val_df"]
    val_target = eval_inputs["val_target"]

    predictions = build_and_predict(
        train_df.copy(), train_target.copy(), val_df.copy()
    )
    predictions = np.asarray(predictions, dtype=np.float64).ravel()

    # Validate predictions
    if len(predictions) != len(val_target):
        return {"neg_mae": -np.inf, "validity": 0.0}

    # Replace any NaN / inf with 0 (neutral prediction)
    valid_mask = np.isfinite(predictions)
    if not np.all(valid_mask):
        predictions = np.where(valid_mask, predictions, 0.0)

    mae = float(np.mean(np.abs(predictions - val_target)))
    return {"neg_mae": -mae, "validity": 1.0}
