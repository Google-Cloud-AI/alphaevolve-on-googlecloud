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

"""Utility functions for AlphaEvolve."""

import csv
from datetime import datetime
import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading

from google.cloud import storage
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Create the lock once when the module is loaded
_csv_write_lock = threading.Lock()


def unflatten_program_content(flat_content: str) -> List[Dict[str, Any]]:
  """Unflattens program content from a single string to a list of files.

  Args:
    flat_content: The flattened program content.

  Returns:
    A list of dictionaries, where each dictionary represents a file.
  """
  # 1. Extract Top-Level Description (appears before the first "File:")
  # We use a non-greedy match up to the first double newline or File start
  # top_desc_match = re.match(
  #     r"(?:Description: )?(?P<desc>.+?)\n\nFile:", flat_content, re.DOTALL
  # )
  # Program description extraction logic can be added here if needed.

  # 2. Extract Files
  # We use [^\n]+ for headers to ensure they stop at the end of the line.
  # We use re.DOTALL so the content capture (.*?) can span multiple lines.
  file_pattern = re.compile(
      r"""
      ^File:\s+(?P<path>[^\n]+)\n                 # Path: match non-newlines
      (?:Language:\s+(?P<language>[^\n]+)\n)?     # Language: match non-newlines
      (?:Description:\s+(?P<description>[^\n]+)\n)? # Desc: match non-newlines
      ---\n                                       # Start Separator
      (?P<content>.*?)
      \n---""",  # End Separator
      re.MULTILINE | re.VERBOSE | re.DOTALL,
  )

  files_data = []

  for match in file_pattern.finditer(flat_content):
    files_data.append(
        {"path": match.group("path").strip(), "content": match.group("content")}
    )

  return files_data


def fix_multi_files_program(program: Dict[str, Any]) -> None:
  """Fixes the program content if it's flattened into a single file."""
  if "content" not in program or "files" not in program["content"]:
    return

  if not program["content"]["files"]:
    return

  first_file_content = program["content"]["files"][0]["content"]
  if first_file_content.startswith("File:"):
    files = unflatten_program_content(first_file_content)
    # print("First file:", first_file_content)
    # print("FILES:", files)
    program["content"]["files"] = files


def copy_local_file(src_path, dest_dir):
  """Copies a file or directory to another local directory.

  Args:
    src_path (str): The path to the file or directory to copy.
    dest_dir (str): The path to the destination directory.

  Returns:
    bool: True if the copy was successful, False otherwise.
  """
  if not os.path.exists(src_path):
    logger.error("Source path %s does not exist.", src_path)
    return False
        
  os.makedirs(dest_dir, exist_ok=True)
    
  try:
    if os.path.isdir(src_path):
      dest_path = os.path.join(dest_dir, os.path.basename(os.path.normpath(src_path)))
      if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
      shutil.copytree(src_path, dest_path)
    else:
      shutil.copy2(src_path, dest_dir)
    logger.info("Successfully copied %s to %s", src_path, dest_dir)
    return True
  except Exception as e:
    logger.error("Failed to copy %s to %s: %s", src_path, dest_dir, e)
    return False


def run_make(makefile_dir=".", target=None, clean_first=False):
  """Runs the make command in the specified directory.

  Args:
    makefile_dir (str): The directory containing the Makefile. Defaults to current dir.
    target (str, optional): The make target to build (e.g., 'all', 'clean').
                                 Defaults to the default target in the Makefile.
    clean_first (bool): If True, run 'make clean' before building the target.

  Returns:
    bool: True if the make command(s) succeeded, False otherwise.
  """
  if not os.path.isdir(makefile_dir):
    logger.error("Error: Makefile directory not found: %s", makefile_dir)
    return False

  if not os.path.exists(os.path.join(makefile_dir, "Makefile")):
    logger.error("Error: Makefile not found in %s", makefile_dir)
    return False

  if clean_first:
    logger.info("Running 'make clean' in %s...", makefile_dir)
    clean_command = ["make", "clean"]
    try:
      clean_result = subprocess.run(
          clean_command,
          cwd=makefile_dir,
          check=True,  # Raise an exception for non-zero exit codes
          capture_output=True,
          text=True
      )
      logger.info("--- 'make clean' STDOUT ---")
      logger.info(clean_result.stdout)
      logger.info("--- 'make clean' STDERR ---")
      logger.info(clean_result.stderr)
      logger.info("'make clean' completed successfully.")
    except subprocess.CalledProcessError as e:
      logger.error("Error running 'make clean' in %s:", makefile_dir)
      logger.error("Command: %s", ' '.join(e.cmd))
      logger.error("Return Code: %s", e.returncode)
      logger.error("--- STDOUT ---")
      logger.error(_truncate_text(e.stdout))
      logger.error("--- STDERR ---")
      logger.error(_truncate_text(e.stderr))
      return False
    except FileNotFoundError:
      logger.error("Error: 'make' command not found. Ensure it's installed and in your PATH.")
      return False

  build_command = ["make"]
  if target:
    build_command.append(target)

  logger.info("Running '%s' in %s...", ' '.join(build_command), makefile_dir)
  try:
    result = subprocess.run(
        build_command,
        cwd=makefile_dir,
        check=True,  # Raise an exception for non-zero exit codes
        capture_output=True,
        text=True
    )
    logger.info("--- '%s' STDOUT ---", ' '.join(build_command))
    logger.info(result.stdout)
    logger.info("--- '%s' STDERR ---", ' '.join(build_command))
    logger.info("'%s' completed successfully.", ' '.join(build_command))
    return True
  except subprocess.CalledProcessError as e:
    logger.error("Error running '%s' in %s:", ' '.join(build_command), makefile_dir)
    logger.error("Command: %s", ' '.join(e.cmd))
    logger.error("Return Code: %s", e.returncode)
    logger.error("--- STDOUT ---")
    logger.error(_truncate_text(e.stdout))
    logger.error("--- STDERR ---")
    logger.error(_truncate_text(e.stderr))
    return False
  except FileNotFoundError:
    logger.error("Error: 'make' command not found. Ensure it's installed and in your PATH.")
    return False

def _truncate_text(text: str, max_lines: int = 50) -> str:
  """Truncates text to a maximum number of lines."""
  if not text:
    return text
  lines = text.splitlines()
  if len(lines) <= max_lines:
    return text
  keep_top = 10
  keep_bottom = 40
  return "\n".join(lines[:keep_top] + [f"... [truncated {len(lines) - keep_top - keep_bottom} lines] ..."] + lines[-keep_bottom:])

def create_full_programs_path(base_dir: str, programs_dir: str, job_id: str) -> str:
  """Creates the full path to the programs directory.

  Args:
    base_dir (str): The base directory.
    programs_dir (str): The programs directory.
    job_id (str): The job ID.

  Returns:
    str: The full path to the programs directory.
  """
  return os.path.join(base_dir, programs_dir, job_id)

def archive_full_program_dir_local(base_dir: str, programs_dir: str, job_id: str, archive_dir: str="archive") -> str:
  """Archives the full program directory by renaming it to a done directory.

  Args:
    base_dir (str): The base directory.
    programs_dir (str): The programs directory.
    job_id (str): The job ID.
    archive_dir (str): The archive directory.

  Returns:
    str: The path to the full archive directory.
  """
  original_path = create_full_programs_path(base_dir, programs_dir, job_id)
  archive_path = os.path.join(base_dir, archive_dir, programs_dir, job_id)  
  os.makedirs(os.path.dirname(archive_path), exist_ok=True)
  os.rename(original_path, archive_path)
  logger.info("Renamed %s to %s", original_path, archive_path)
  return archive_path

def archive_full_program_dir_gcs(bucket_name: str, base_dir: str, programs_dir: str, job_id: str, archive_dir: str="archive"):
  """Archives all files from a source prefix to a destination prefix within the same GCS bucket.
    
  Args:
    bucket_name: The name of the GCS bucket.
    base_dir: The base directory.
    programs_dir: The directory prefix for the programs.
    job_id: The ID of the job.
    archive_dir: The directory prefix for the archive.
  """
  storage_client = storage.Client()
    
  blob_name_dir = create_full_programs_path(base_dir, programs_dir, job_id)
  new_blob_name_dir = os.path.join(base_dir, archive_dir, programs_dir, job_id)
    
  source_prefix = blob_name_dir
  destination_prefix = new_blob_name_dir

  if not source_prefix.endswith('/'):
    source_prefix += '/'
  if not destination_prefix.endswith('/'):
    destination_prefix += '/'

  bucket = storage_client.bucket(bucket_name)

  logger.info("Attempting to move contents from gs://%s/%s to gs://%s/%s", bucket_name, source_prefix, bucket_name, destination_prefix)

  blobs = list(bucket.list_blobs(prefix=source_prefix))

  if not blobs:
    logger.warning("No files found under source prefix: gs://%s/%s", bucket_name, source_prefix)
    return

  moved_count = 0
  for blob in blobs:
    if blob.name == source_prefix:  # Skip any placeholder "directory" object if it exists
      continue

    logger.debug("Moving gs://%s/%s to gs://%s/%s", bucket_name, blob.name, bucket_name, destination_prefix)

    try:
      relative_path = blob.name[len(source_prefix):]
      destination_blob = bucket.blob(destination_prefix + relative_path)
      # Copy the blob to the new location
      bucket.copy_blob(blob, bucket, destination_prefix + relative_path)
      # Delete the original blob
      blob.delete()
      moved_count += 1
    except Exception as e:
      logger.error("Error moving %s to %s: %s", blob.name, destination_prefix, e)
    
  # Delete the source directory placeholder if it exists
  source_dir_blob = bucket.blob(source_prefix)
  if source_dir_blob.exists():
    source_dir_blob.delete()

  logger.info("Finished moving %s files from %s to %s", moved_count, source_prefix, destination_prefix)
    
def get_program_candidate_file_path(full_program_path: str) -> str:
  """Gets the path to the program candidate file.
  
  Args:
    full_program_path: The path to the full program directory.
    
  Returns:
    str: The path to the program candidate file.
  """
  return os.path.join(full_program_path, "program_candidate_data.json")

def get_program_candidate_result_path(full_program_path: str) -> str:
  """Gets the path to the program candidate result file.
  
  Args:
    full_program_path: The path to the full program directory.
    
  Returns:
    str: The path to the program candidate result file.
  """
  return os.path.join(full_program_path, "program_candidate_result.json")

def get_job_id_from_program_name(program_name: str, prefix: str) -> str:
  """Gets the job ID from the program name.
  
  Args:
    program_name: The name of the program.
    prefix: The prefix to use for the job ID.
    
  Returns:
    str: The job ID.
  """
  suffix = program_name.split('/')[-1]
  # Cloud Batch has a 63-character limit on Job IDs.
  # Truncate the prefix to ensure total length does not exceed 63 characters.
  max_prefix_len = 63 - len(suffix) - 1
  trimmed_prefix = prefix[:max_prefix_len].rstrip('-')
  return f"{trimmed_prefix}-{suffix}"


def read_file_from_gcs(bucket_name, blob_name):
  """Reads a file from GCS and returns its content as a Python dictionary.
    
  Args:
    bucket_name: The name of the GCS bucket.
    blob_name: The name of the file to read.
    
  Returns:
    dict: The content of the file as a Python dictionary.
  """
  # 1. Initialize the client (No keys needed on Cloudtop)
  storage_client = storage.Client()

  # 2. Get the bucket and the specific file (blob)
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(blob_name)

  if not blob.exists():
    logger.warning("File not found in GCS: gs://%s/%s", bucket_name, blob_name)
    return None

  # 3. Download the content as text
  json_string = blob.download_as_text()

  # 3. Parse the string into a Python dictionary
  try:
    data = json.loads(json_string)
    return data
  except json.JSONDecodeError as e:
    logger.error("Failed to parse JSON content. %s", e)
    return None

def write_file_to_gcs(bucket_name: str, blob_name: str, data: str):
  """Writes a string data payload directly to a GCS bucket file.
  
  Args:
    bucket_name: The name of the GCS bucket.
    blob_name: The name of the file to write.
    data: The string payload content.
  """
  storage_client = storage.Client()
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(blob_name)
  try:
    blob.upload_from_string(data, content_type="application/json")
    logger.info("Successfully wrote to GCS: gs://%s/%s", bucket_name, blob_name)
  except Exception as e:
    logger.error("Failed to write to GCS gs://%s/%s: %s", bucket_name, blob_name, e)

def delete_file_from_gcs(bucket_name: str, blob_name: str):
  """Deletes a file directly from a GCS bucket.
  
  Args:
    bucket_name: The name of the GCS bucket.
    blob_name: The name of the file to delete.
  """
  storage_client = storage.Client()
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(blob_name)
  if blob.exists():
    try:
      blob.delete()
      logger.info("Successfully deleted from GCS: gs://%s/%s", bucket_name, blob_name)
    except Exception as e:
      logger.error("Failed to delete from GCS gs://%s/%s: %s", bucket_name, blob_name, e)
  else:
    logger.info("Skipped deletion, file not found: gs://%s/%s", bucket_name, blob_name)

def download_full_program_dir_gcs(bucket_name: str, programs_dir: str, job_id: str, dest_dir: str, user_experiment_name: str):
  """Downloads all files from a source prefix to a destination prefix within the same GCS bucket.
    
  Args:
    bucket_name: The name of the GCS bucket.
    programs_dir: The directory prefix for the programs.
    job_id: The ID of the job.
    dest_dir: The local directory to download files to.
    user_experiment_name: The name of the user experiment.
  """
  storage_client = storage.Client()
  source_prefix = create_full_programs_path(user_experiment_name, programs_dir, job_id)
  if not source_prefix.endswith('/'):
    source_prefix += '/'

  bucket = storage_client.bucket(bucket_name)
  logger.info("Attempting to download contents from gs://%s/%s to %s", bucket_name, source_prefix, dest_dir)

  blobs = list(bucket.list_blobs(prefix=source_prefix))

  if not blobs:
    logger.warning("No files found under source prefix: gs://%s/%s", bucket_name, source_prefix)
    return

  downloaded_count = 0
  for blob in blobs:
    if blob.name == source_prefix: # Skip dir placeholder
      continue

    # Determine relative path
    relative_path = blob.name[len(source_prefix):]
    local_path = os.path.join(dest_dir, relative_path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:
      blob.download_to_filename(local_path)
      downloaded_count += 1
      logger.debug("Downloaded gs://%s/%s to %s", bucket_name, blob.name, local_path)
    except Exception as e:
      logger.error("Error downloading gs://%s/%s to %s: %s", bucket_name, blob.name, local_path, e)

  logger.info("Finished downloading %s files from gs://%s/%s to %s", downloaded_count, bucket_name, source_prefix, dest_dir)

def upload_entire_payload_gcs(bucket_name: str, programs_dir: str, job_id: str, candidate_program_id: str, program_candidate_data: Any, user_experiment_name: str):
    """Uploads the entire program payload to GCS Bucket.

    Args:
      bucket_name: The name of the GCS bucket.
      programs_dir: The directory to save the programs to.
      job_id: The job ID for the program.
      candidate_program_id: The program ID for the candidate program.
      program_candidate_data: The program candidate data to upload.
      user_experiment_name: The name of the user experiment.
    """
    logger.info("Uploading program %s to GCS Bucket name: %s with Job ID: %s", candidate_program_id, bucket_name, job_id)
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    blob_path = create_full_programs_path(user_experiment_name, programs_dir, job_id)

    program_candidate_data_blob_path = get_program_candidate_file_path(blob_path)
    blob = bucket.blob(program_candidate_data_blob_path)

    try:
      if isinstance(program_candidate_data, bytes):
        json_string = program_candidate_data.decode('utf-8')
      elif isinstance(program_candidate_data, str):
        json_string = program_candidate_data
      else:
        raise TypeError("program_candidate_data is not a string or bytes")
      data = json.loads(json_string)

      # Save only metadata to avoid duplication
      metadata = {"name": data.get("name"), "lockToken": data.get("lockToken")}
      blob.upload_from_string(
          json.dumps(metadata), 
          content_type="application/json"
      )
        
      logger.info("Successfully staged program metadata %s to %s", candidate_program_id, blob_path)

      # Upload individial files
      for file in data["content"]["files"]:
        logger.info(f"Uploading file {file['path']}")
        file_path = os.path.join(blob_path, file['path'])
        file_blob = bucket.blob(file_path)
        content_str = file["content"]

        if not isinstance(content_str, str):
            logger.error(f"Error: Content for {file['path']} is not a string, it's {type(content_str)}")
            continue
        file_blob.upload_from_string(content_str, content_type="text/plain")
        logger.info(f"Successfully staged file {file['path']} to {file_path}")

    except Exception as e:
      logger.error(f"Failed to stage payload: {e}")


def process_and_log_evaluation(
    program_id: str,
    evaluation: Any,
    eval_time: float,
    logger: logging.Logger,
    bucket_name: str,
    user_experiment_name: str,
    metrics_list: List[str] = None
):
  """Processes evaluation results and logs metrics.

  Args:
    program_id: The ID of the candidate program.
    evaluation: The raw evaluation result (usually a dict).
    eval_time: The duration of the evaluation.
    logger: The logger instance to use for output.
    bucket_name: The name of the GCS bucket to save the CSV to.
    user_experiment_name: The name of the user experiment.
    metrics_list: List of metrics to prioritize for logging.
  """
  score_value = None
  metric_name = "score"
  insights_text = ""
  scores_list = []

  if isinstance(evaluation, dict):
    insights_data = evaluation.get("insights")
    if isinstance(insights_data, dict):
      insights_list = insights_data.get("insights", [])
      if isinstance(insights_list, list):
        labels = [i.get("label", "") for i in insights_list if i.get("label")]
        insights_text = " | ".join(labels)

    scores_data = evaluation.get("scores", {})
    if isinstance(scores_data, dict):
      scores_list = scores_data.get("scores", [])
      if isinstance(scores_list, list) and len(scores_list) > 0:
        score_value = scores_list[0].get("score")
        metric_name = scores_list[0].get("metric", "score")

  # Override status based on score
  if score_value is not None and score_value != float("-inf"):
    status = "SUCCESS"
  else:
    status = "FAILURE"

  csv_blob_name = f"{user_experiment_name}/results.csv"
  with _csv_write_lock:
    try:
      storage_client = storage.Client()
      bucket = storage_client.bucket(bucket_name)
      blob = bucket.blob(csv_blob_name)
      
      csv_data = ""
      if blob.exists():
        csv_data = blob.download_as_text()
      
      output = io.StringIO()
      writer = csv.writer(output)
      
      if not csv_data:
        writer.writerow(["time", "program_id", "metric_name", "score", "eval_time", "status", "insights"])
      
      rows_written = 0
      for s in scores_list:
        if isinstance(s, dict):
          metric = s.get("metric")
          score = s.get("score")
          
          # Filter based on metrics_list if provided
          if metrics_list and metric not in metrics_list:
            continue
            
          writer.writerow([
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              f"ID_{program_id}",
              metric,
              str(score),
              str(eval_time),
              status,
              insights_text
          ])
          rows_written += 1
          
      # Fallback: if no rows written (e.g. empty scores or none matched filter),
      # log at least one row with the primary score_value determined above.
      if rows_written == 0:
          writer.writerow([
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              f"ID_{program_id}",
              metric_name,
              str(score_value),
              str(eval_time),
              status,
              insights_text
          ])
      
      csv_row_str = output.getvalue()
      
      if csv_data:
          csv_data += csv_row_str
      else:
          csv_data = csv_row_str
          
      blob.upload_from_string(csv_data, content_type="text/csv")
      logger.info("Successfully appended to CSV on GCS: gs://%s/%s", bucket_name, csv_blob_name)
    except Exception as e:
      logger.error("Failed to write CSV to GCS: %s", e)

def get_positive_int_env(env_name: str, default: str) -> int:
    """Reads an environment variable and ensures it is a strictly positive integer.
    
    Args:
        env_name: The name of the environment variable.
        default: The default value to use if the environment variable is not set.
        
    Returns:
        int: The validated integer value.
        
    Raises:
        ValueError: If the value is not a valid integer or is <= 0.
    """
    val_str = os.getenv(env_name) or default
    try:
        val = int(val_str)
        if val <= 0:
            raise ValueError(f"{env_name} must be a strictly positive integer, got {val}")
        return val
    except ValueError as e:
        raise ValueError(f"{env_name} must be a valid integer, got {val_str}") from e


def check_duplicate_evaluation(
    bucket_name: str,
    user_experiment_name: str,
    candidate_program_id: str
) -> bool:
  """Checks if a candidate program has already been evaluated and recorded in results.csv.

  Args:
    bucket_name: The name of the GCS bucket.
    user_experiment_name: The name of the user experiment.
    candidate_program_id: The ID of the candidate program.

  Returns:
    bool: True if the program has already been evaluated, False otherwise.
  """
  csv_blob_name = f"{user_experiment_name}/results.csv"
  try:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(csv_blob_name)
    if blob.exists():
      csv_content = blob.download_as_text()
      f = io.StringIO(csv_content)
      reader = csv.reader(f)
      header = next(reader, None)
      if header and "program_id" in header:
        prog_id_idx = header.index("program_id")
        for row in reader:
          if len(row) > prog_id_idx and row[prog_id_idx] == f"ID_{candidate_program_id}":
            return True
  except Exception as e:
    logger.warning("Failed to check duplicate evaluation in results.csv: %s", e)
  return False


def sanitize_score_value(val: Any) -> Any:
  if val is None:
    return None
  try:
    f_val = float(val)
    if math.isinf(f_val) or math.isnan(f_val):
      return -1e12
    return val
  except (ValueError, TypeError):
    return val


def sanitize_evaluation_scores(evaluation: Dict[str, Any]) -> Dict[str, Any]:
  if not isinstance(evaluation, dict):
    return evaluation
      
  # Structured format: evaluation["scores"]["scores"] = [{"metric": ..., "score": ...}]
  if "scores" in evaluation and isinstance(evaluation["scores"], dict):
    scores_dict = evaluation["scores"]
    if "scores" in scores_dict and isinstance(scores_dict["scores"], list):
      for item in scores_dict["scores"]:
        if isinstance(item, dict) and "score" in item:
          item["score"] = sanitize_score_value(item["score"])
                  
  # Support for flat/legacy structures
  for k, v in list(evaluation.items()):
    if k not in ["scores", "insights"]:
      evaluation[k] = sanitize_score_value(v)
          
  return evaluation