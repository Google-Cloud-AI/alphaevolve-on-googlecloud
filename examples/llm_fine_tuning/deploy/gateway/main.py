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
"""Gateway service for GKE-based LLM fine-tuning evaluation.

Receives HTTP POST requests with evolved hyperparameter configurations,
creates RayJobs on a persistent RayCluster for training, polls for
completion, and returns metrics to the AlphaEvolve client.
"""

import json
import logging
import os
import time
import uuid

import yaml
from flask import Flask, Response, jsonify, request
from google.cloud import storage
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

# Evolution metrics (existing)
EVAL_SCORE = Gauge(
    "alphaevolve_eval_score",
    "Score of the latest evaluated candidate",
    ["job_id"],
)
BEST_SCORE = Gauge("alphaevolve_best_score", "Best score seen so far")
EVAL_TOTAL = Counter(
    "alphaevolve_eval_total", "Total number of evaluations completed"
)
EVAL_ERRORS = Counter(
    "alphaevolve_eval_errors", "Total number of failed evaluations"
)
EVAL_DURATION = Histogram(
    "alphaevolve_eval_duration_seconds",
    "Training job duration in seconds",
    buckets=[60, 120, 180, 300, 600, 900],
)
JOB_ACTIVE = Gauge(
    "alphaevolve_jobs_active", "Number of currently running training jobs"
)

# Training metrics (new — populated from training output)
TRAIN_LOSS = Gauge(
    "alphaevolve_train_loss",
    "Training loss of the latest evaluation",
    ["job_id"],
)
EVAL_PERPLEXITY = Gauge(
    "alphaevolve_eval_perplexity",
    "Eval perplexity of the latest evaluation",
    ["job_id"],
)
TRAINING_TIME = Histogram(
    "alphaevolve_training_time_seconds",
    "Training time reported by the training job",
    buckets=[60, 120, 180, 300, 600, 900, 1200],
)

_best_score_value = float("-inf")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

ARTIFACTS_BUCKET = os.environ.get("ARTIFACTS_BUCKET", "")
NAMESPACE = os.environ.get("NAMESPACE", "alphaevolve")
ARTIFACTS_PATH = os.environ.get("ARTIFACTS_PATH", "/mnt/artifacts")
RAY_CLUSTER_NAME = os.environ.get(
    "RAY_CLUSTER_NAME", "alphaevolve-ray-cluster"
)

# Job configuration
JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", "2400"))
JOB_POLL_INTERVAL = int(os.environ.get("JOB_POLL_INTERVAL", "10"))

# ---------------------------------------------------------------------------
# Kubernetes client
# ---------------------------------------------------------------------------

try:
    k8s_config.load_incluster_config()
except k8s_config.ConfigException:
    k8s_config.load_kube_config()

custom_api = k8s_client.CustomObjectsApi()
gcs_client = storage.Client()


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------


def _upload_input(job_id: str, files: list) -> None:
    """Upload training input to GCS."""
    bucket = gcs_client.bucket(ARTIFACTS_BUCKET)
    blob = bucket.blob(f"jobs/{job_id}/input.json")
    blob.upload_from_string(
        json.dumps({"files": files}), content_type="application/json"
    )


def _read_output(job_id: str) -> dict:
    """Read training output from GCS."""
    bucket = gcs_client.bucket(ARTIFACTS_BUCKET)
    blob = bucket.blob(f"jobs/{job_id}/output.json")
    return json.loads(blob.download_as_text())


def _cleanup_gcs(job_id: str) -> None:
    """Delete job input/output from GCS."""
    bucket = gcs_client.bucket(ARTIFACTS_BUCKET)
    for suffix in ("input.json", "output.json"):
        blob = bucket.blob(f"jobs/{job_id}/{suffix}")
        try:
            blob.delete()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# RayJob management
# ---------------------------------------------------------------------------


def _create_rayjob(job_id: str) -> dict:
    """Create a RayJob custom resource on the persistent RayCluster."""
    rayjob = {
        "apiVersion": "ray.io/v1",
        "kind": "RayJob",
        "metadata": {
            "name": f"training-{job_id}",
            "namespace": NAMESPACE,
            "labels": {
                "app": "alphaevolve-training",
                "job-id": job_id,
            },
        },
        "spec": {
            "entrypoint": f"python -m src --job-id {job_id}",
            "shutdownAfterJobFinishes": False,
            "clusterSelector": {
                "ray.io/cluster": RAY_CLUSTER_NAME,
            },
            "runtimeEnvYAML": yaml.dump({
                "env_vars": {
                    "JOB_ID": job_id,
                    "ARTIFACTS_BUCKET": ARTIFACTS_BUCKET,
                    "ARTIFACTS_PATH": ARTIFACTS_PATH,
                },
            }),
        },
    }

    return custom_api.create_namespaced_custom_object(
        group="ray.io",
        version="v1",
        namespace=NAMESPACE,
        plural="rayjobs",
        body=rayjob,
    )


def _wait_for_rayjob(job_name: str) -> str:
    """Poll RayJob status until completion.

    Returns 'succeeded', 'failed', or 'timeout'.
    RayJob statuses: PENDING, RUNNING, SUCCEEDED, FAILED, STOPPED.
    """
    deadline = time.time() + JOB_TIMEOUT_SECONDS + 60
    while time.time() < deadline:
        try:
            job = custom_api.get_namespaced_custom_object(
                group="ray.io",
                version="v1",
                namespace=NAMESPACE,
                plural="rayjobs",
                name=job_name,
            )
        except k8s_client.ApiException as e:
            if e.status == 404:
                logger.warning(f"[{job_name}] RayJob not found (deleted?)")
                return "failed"
            logger.warning(f"Failed to read RayJob status: {e}")
            time.sleep(JOB_POLL_INTERVAL)
            continue

        status = job.get("status", {})
        job_status = status.get("jobStatus", "")

        if job_status == "SUCCEEDED":
            return "succeeded"
        if job_status in ("FAILED", "STOPPED"):
            return "failed"

        elapsed = int(time.time() - (deadline - JOB_TIMEOUT_SECONDS - 60))
        logger.debug(
            f"[{job_name}] Polling — status: {job_status}, "
            f"elapsed: {elapsed}s"
        )
        time.sleep(JOB_POLL_INTERVAL)

    return "timeout"


def _delete_rayjob(job_name: str) -> None:
    """Delete the RayJob custom resource."""
    try:
        custom_api.delete_namespaced_custom_object(
            group="ray.io",
            version="v1",
            namespace=NAMESPACE,
            plural="rayjobs",
            name=job_name,
        )
    except Exception as e:
        logger.warning(f"Failed to delete RayJob {job_name}: {e}")


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


@app.route("/evaluate", methods=["POST"])
def evaluate():
    """Handle evaluation request: create RayJob, wait, return results."""
    global _best_score_value

    request_json = request.get_json(silent=True)
    if not request_json:
        return jsonify({"error": "Invalid JSON"}), 400

    files = request_json.get("files", [])
    if not files:
        return jsonify({"error": "Missing 'files' in request"}), 400

    job_id = uuid.uuid4().hex[:12]
    job_name = f"training-{job_id}"

    logger.info(
        f"[{job_name}] Received evaluation request — "
        f"{len(files)} file(s), "
        f"payload size: {sum(len(f.get('content', '')) for f in files)} chars"
    )

    # Upload input to GCS
    try:
        _upload_input(job_id, files)
        logger.info(
            f"[{job_name}] Input uploaded to "
            f"gs://{ARTIFACTS_BUCKET}/jobs/{job_id}/input.json"
        )
    except Exception as e:
        logger.error(f"Failed to upload input: {e}")
        EVAL_ERRORS.inc()
        return jsonify({
            "metrics": {"neg_eval_loss": -100.0},
            "insights": {"insights": [
                {"label": "Gateway Error",
                 "text": f"Failed to upload input to GCS: {e}"}
            ]},
        }), 500

    # Create RayJob on the persistent RayCluster
    try:
        _create_rayjob(job_id)
    except Exception as e:
        logger.error(f"Failed to create RayJob: {e}")
        _cleanup_gcs(job_id)
        EVAL_ERRORS.inc()
        return jsonify({
            "metrics": {"neg_eval_loss": -100.0},
            "insights": {"insights": [
                {"label": "Gateway Error",
                 "text": f"Failed to create RayJob: {e}"}
            ]},
        }), 500

    logger.info(
        f"[{job_name}] RayJob created on cluster {RAY_CLUSTER_NAME}, "
        f"timeout: {JOB_TIMEOUT_SECONDS}s"
    )

    # Track active job and timing
    JOB_ACTIVE.inc()
    start_time = time.time()

    try:
        # Wait for completion
        status = _wait_for_rayjob(job_name)
        logger.info(f"[{job_name}] RayJob finished — status: {status}")
        duration = time.time() - start_time

        if status == "timeout":
            # Training may have written metrics before a slow post-step
            # (e.g. model merge) caused the timeout. Check GCS first.
            try:
                result = _read_output(job_id)
                logger.info(
                    f"[{job_name}] Timed out but found output in GCS"
                )
            except Exception:
                result = {
                    "metrics": {"neg_eval_loss": -100.0},
                    "insights": {"insights": [
                        {"label": "Evaluation Error",
                         "text": f"Training job timed out after "
                                 f"{JOB_TIMEOUT_SECONDS}s."}
                    ]},
                }
            _cleanup_gcs(job_id)
            _delete_rayjob(job_name)
            EVAL_ERRORS.inc()
            return jsonify(result)

        if status == "failed":
            try:
                result = _read_output(job_id)
            except Exception:
                result = {
                    "metrics": {"neg_eval_loss": -100.0},
                    "insights": {"insights": [
                        {"label": "Evaluation Error",
                         "text": "Training RayJob failed. Check Ray Dashboard "
                                 "for logs."}
                    ]},
                }
            _cleanup_gcs(job_id)
            _delete_rayjob(job_name)
            EVAL_ERRORS.inc()
            return jsonify(result)

        # Read results
        try:
            result = _read_output(job_id)
        except Exception as e:
            logger.error(f"Failed to read output: {e}")
            result = {
                "metrics": {"neg_eval_loss": -100.0},
                "insights": {"insights": [
                    {"label": "Gateway Error",
                     "text": f"Job succeeded but failed to read output: {e}"}
                ]},
            }

        metrics = result.get("metrics", {})
        insights = result.get("insights", {}).get("insights", [])
        logger.info(
            f"[{job_name}] Returning metrics — "
            + ", ".join(f"{k}: {v}" for k, v in metrics.items())
        )
        if insights:
            for insight in insights:
                logger.info(
                    f"[{job_name}] Insight: {insight.get('label', '')}: "
                    f"{insight.get('text', '')}"
                )

        # Record Prometheus metrics
        EVAL_TOTAL.inc()
        EVAL_DURATION.observe(duration)

        neg_eval_loss = metrics.get("neg_eval_loss")
        if neg_eval_loss is not None:
            score = float(neg_eval_loss)
            EVAL_SCORE.labels(job_id=job_id).set(score)
            if score > _best_score_value:
                _best_score_value = score
                BEST_SCORE.set(score)

        # Training-specific metrics
        train_loss = metrics.get("train_loss")
        if train_loss is not None:
            TRAIN_LOSS.labels(job_id=job_id).set(float(train_loss))

        eval_perplexity = metrics.get("eval_perplexity")
        if eval_perplexity is not None and eval_perplexity != float("inf"):
            EVAL_PERPLEXITY.labels(job_id=job_id).set(float(eval_perplexity))

        training_time = metrics.get("training_time_seconds")
        if training_time is not None:
            TRAINING_TIME.observe(float(training_time))

        _cleanup_gcs(job_id)
        _delete_rayjob(job_name)
        return jsonify(result)
    finally:
        JOB_ACTIVE.dec()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for GKE readiness/liveness probes."""
    return jsonify({"status": "ok"})


@app.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
