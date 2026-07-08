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
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import functions_framework

# Use /tmp for writable directory in Cloud Functions
WORK_DIR = Path("/tmp/rust_eval")
PROJECT_DIR = WORK_DIR / "sort_test"
SRC_DIR = PROJECT_DIR / "src"


def _clean_and_create_workspace() -> None:
    """Cleans up the workspace and recreates necessary directories."""
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    WORK_DIR.mkdir(parents=True)
    PROJECT_DIR.mkdir()
    SRC_DIR.mkdir()


def _write_source_files(files: List[Dict[str, str]]) -> None:
    """Writes user provided source files to the src directory."""
    for file_obj in files:
        rel_path_str = file_obj["path"]
        # Remove 'src/' prefix if present to avoid nesting like src/src/lib.rs
        if rel_path_str.startswith("src/"):
            rel_path_str = rel_path_str[4:]

        file_path = SRC_DIR / rel_path_str
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_obj["content"])


def _setup_cargo_toml(cargo_toml_content: Optional[str]) -> bool:
    """
    Sets up Cargo.toml. Returns True if successful, False if missing.
    Prioritizes provided content, then falls back to /app/Cargo.toml.
    """
    target_path = PROJECT_DIR / "Cargo.toml"

    if cargo_toml_content:
        target_path.write_text(cargo_toml_content)
        return True

    # Fallback to pre-packaged Cargo.toml
    source_path = Path("/app/Cargo.toml")
    if source_path.exists():
        shutil.copy(source_path, target_path)
        return True

    return False


def _copy_cached_target() -> None:
    """Copies pre-built target directory if available to speed up compilation."""
    cached_target = Path("/app/target")
    if cached_target.exists():
        shutil.copytree(cached_target, PROJECT_DIR / "target")


def _run_cargo_command(
    args: List[str], env: Dict[str, str], timeout: int
) -> subprocess.CompletedProcess:
    """Runs a cargo command in the project directory."""
    return subprocess.run(
        args,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _parse_metrics(output: str) -> Dict[str, Any]:
    """Parses JSON metrics from the stdout."""
    try:
        start = output.find("{")
        end = output.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in output")

        json_str = output[start:end]
        results = json.loads(json_str)

        correctness = results.get("correctness", 0.0)
        performance = results.get("performance_score", 0.0)
        adaptability = results.get("adaptability_score", 0.0)

        overall_score = 0.0
        if correctness >= 1.0:
            overall_score = 0.6 * performance + 0.4 * adaptability

        return {
            "metrics": {
                "score": overall_score,
                "compile_success": 1.0,
                "correctness": correctness,
                "performance_score": performance,
                "adaptability_score": adaptability,
                "avg_time": results.get("avg_time"),
                "memory_safe": 1.0,
            },
            "artifacts": {
                "times": results.get("times"),
                "all_correct": results.get("all_correct"),
            },
        }
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "metrics": {"score": 0.0, "compile_success": 1.0},
            "artifacts": {
                "error": f"Failed to parse results: {str(e)}",
                "stdout": output,
            },
        }


def _create_response(
    data: Dict[str, Any], status_code: int = 200
) -> Tuple[str, int, Dict[str, str]]:
    """Helper to create the flask response tuple."""
    return (
        json.dumps(data),
        status_code,
        {"Content-Type": "application/json"},
    )


@functions_framework.http
def evaluate_rust_sort(request: Any) -> Tuple[str, int, Dict[str, str]]:
    """
    HTTP Cloud Function to evaluate Rust sorting algorithms.
    Expects JSON: {"files": [{"path": "...", "content": "..."}], "harness": "...", "cargo_toml": "..."}
    """
    try:
        request_json = request.get_json(silent=True)
        if not request_json:
            return _create_response({"error": "Invalid JSON"}, 400)

        source_files = request_json.get("files", [])
        harness_code = request_json.get("harness", "")
        cargo_toml = request_json.get("cargo_toml", "")

        if not source_files:
            return _create_response({"error": "Missing 'files' in request"}, 400)

        # Setup Workspace
        _clean_and_create_workspace()

        # Write Files
        _write_source_files(source_files)

        if harness_code:
            (SRC_DIR / "main.rs").write_text(harness_code)

        if not _setup_cargo_toml(cargo_toml):
            return _create_response({"error": "Missing Cargo.toml"}, 400)

        # Build
        env = os.environ.copy()
        _copy_cached_target()

        build_res = _run_cargo_command(["cargo", "build", "--release"], env, timeout=60)

        if build_res.returncode != 0:
            return _create_response(
                {
                    "metrics": {"score": 0.0, "compile_success": 0.0},
                    "artifacts": {
                        "error": "Compilation failed",
                        "stderr": build_res.stderr,
                        "stdout": build_res.stdout,
                    },
                }
            )

        # Run
        run_res = _run_cargo_command(["cargo", "run", "--release"], env, timeout=30)

        if run_res.returncode != 0:
            return _create_response(
                {
                    "metrics": {
                        "score": 0.0,
                        "compile_success": 1.0,
                        "correctness": 0.0,
                        "performance_score": 0.0,
                        "adaptability_score": 0.0,
                    },
                    "artifacts": {
                        "error": "Runtime error",
                        "stderr": run_res.stderr,
                        "stdout": run_res.stdout,
                    },
                }
            )

        # Parse & Return
        result = _parse_metrics(run_res.stdout)
        # Append build output to artifacts
        result["artifacts"]["build_output"] = build_res.stdout

        return _create_response(result)

    except subprocess.TimeoutExpired as e:
        return _create_response(
            {
                "metrics": {"score": 0.0, "compile_success": 1.0},
                "artifacts": {"error": f"Timeout: {str(e)}"},
            }
        )
    except Exception as e:
        return _create_response({"error": str(e)}, 500)