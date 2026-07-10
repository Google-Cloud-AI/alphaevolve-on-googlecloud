# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for utility functions in utils.py."""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from alpha_evolve.utils import (
    unflatten_program_content,
    fix_multi_files_program,
    copy_local_file,
    run_make,
    _truncate_text,
    create_full_programs_path,
    archive_full_program_dir_local,
    archive_full_program_dir_gcs,
    get_program_candidate_file_path,
    get_program_candidate_result_path,
    get_job_id_from_program_name,
    read_file_from_gcs,
    write_file_to_gcs,
    delete_file_from_gcs,
    download_full_program_dir_gcs,
    upload_entire_payload_gcs,
    process_and_log_evaluation,
    get_positive_int_env,
    check_duplicate_evaluation,
)


def test_unflatten_program_content():
    flat = "File: main.py\nLanguage: python\n---\nprint('hello')\n---\nFile: helper.py\n---\ndef add(): pass\n---"
    files = unflatten_program_content(flat)
    assert len(files) == 2
    assert files[0]["path"] == "main.py"
    assert files[0]["content"] == "print('hello')"
    assert files[1]["path"] == "helper.py"


def test_fix_multi_files_program():
    prog = {
        "content": {
            "files": [
                {
                    "path": "flat.txt",
                    "content": "File: a.py\n---\nx=1\n---\nFile: b.py\n---\ny=2\n---",
                }
            ]
        }
    }
    fix_multi_files_program(prog)
    assert len(prog["content"]["files"]) == 2
    assert prog["content"]["files"][0]["path"] == "a.py"
    assert prog["content"]["files"][1]["path"] == "b.py"


def test_copy_local_file(tmp_path):
    src_file = tmp_path / "src.txt"
    src_file.write_text("content")
    dest_dir = tmp_path / "dest"

    assert copy_local_file(str(src_file), str(dest_dir))
    assert (dest_dir / "src.txt").exists()

    # Test non-existent
    assert not copy_local_file("non_existent.txt", str(dest_dir))


@patch("alpha_evolve.utils.subprocess.run")
def test_run_make(mock_run, tmp_path):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    
    mock_run.return_value = MagicMock(stdout="ok", stderr="")

    assert run_make(str(tmp_path), clean_first=True)
    assert mock_run.call_count == 2  # clean then build


def test_truncate_text():
    short = "hello\nworld"
    assert _truncate_text(short, 10) == short

    long_text = "\n".join(f"line {i}" for i in range(100))
    truncated = _truncate_text(long_text, 50)
    assert "truncated" in truncated


def test_paths_helpers():
    assert create_full_programs_path("base", "prog", "job1") == "base/prog/job1"
    assert get_program_candidate_file_path("dir") == "dir/program_candidate_data.json"
    assert get_program_candidate_result_path("dir") == "dir/program_candidate_result.json"
    assert get_job_id_from_program_name("projects/p/locations/l/programs/prog-1", "prefix") == "prefix-prog-1"


def test_get_positive_int_env(monkeypatch):
    monkeypatch.setenv("TEST_INT", "10")
    assert get_positive_int_env("TEST_INT", "5") == 10

    monkeypatch.setenv("TEST_INT", "-5")
    with pytest.raises(ValueError, match="must be a valid integer"):
        get_positive_int_env("TEST_INT", "5")

    monkeypatch.setenv("TEST_INT", "abc")
    with pytest.raises(ValueError, match="must be a valid integer"):
        get_positive_int_env("TEST_INT", "5")


@patch("alpha_evolve.utils.storage.Client")
def test_gcs_helpers(mock_client):
    mock_bucket = MagicMock()
    mock_client.return_value.bucket.return_value = mock_bucket

    # read_file_from_gcs
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = '{"key": "val"}'
    mock_bucket.blob.return_value = mock_blob
    assert read_file_from_gcs("bucket", "file.json") == {"key": "val"}

    # write_file_to_gcs
    write_file_to_gcs("bucket", "file.json", "data")
    mock_blob.upload_from_string.assert_called_once()

    # delete_file_from_gcs
    delete_file_from_gcs("bucket", "file.json")
    mock_blob.delete.assert_called_once()


@patch("alpha_evolve.utils.storage.Client")
def test_archive_gcs(mock_client):
    mock_bucket = MagicMock()
    mock_client.return_value.bucket.return_value = mock_bucket

    mock_blob1 = MagicMock(name="base/prog/job1/a.txt")
    mock_blob1.name = "base/prog/job1/a.txt"
    mock_bucket.list_blobs.return_value = [mock_blob1]

    archive_full_program_dir_gcs("bucket", "base", "prog", "job1")
    mock_bucket.copy_blob.assert_called_once()
    mock_blob1.delete.assert_called_once()


@patch("alpha_evolve.utils.storage.Client")
def test_process_and_log_evaluation(mock_client):
    mock_bucket = MagicMock()
    mock_client.return_value.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_blob.exists.return_value = False
    mock_bucket.blob.return_value = mock_blob

    eval_data = {
        "scores": {"scores": [{"metric": "acc", "score": 0.95}]},
        "insights": {"insights": [{"label": "INFO", "text": "ok"}]},
    }
    
    logger = MagicMock()
    process_and_log_evaluation("prog1", eval_data, 1.5, logger, "bucket", "exp1")
    mock_blob.upload_from_string.assert_called_once()


@patch("alpha_evolve.utils.storage.Client")
def test_check_duplicate_evaluation(mock_client):
    mock_bucket = MagicMock()
    mock_client.return_value.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    # Case 1: results.csv doesn't exist
    mock_blob.exists.return_value = False
    assert not check_duplicate_evaluation("bucket", "exp1", "prog1")

    # Case 2: results.csv exists but doesn't contain the candidate
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = "time,program_id,metric_name,score,eval_time,status,insights\n2026-05-27,ID_other,score,1.0,0.5,SUCCESS,ok"
    assert not check_duplicate_evaluation("bucket", "exp1", "prog1")

    # Case 3: results.csv exists and contains the candidate
    mock_blob.download_as_text.return_value = "time,program_id,metric_name,score,eval_time,status,insights\n2026-05-27,ID_prog1,score,1.0,0.5,SUCCESS,ok"
    assert check_duplicate_evaluation("bucket", "exp1", "prog1")
