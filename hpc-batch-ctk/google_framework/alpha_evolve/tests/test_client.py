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

"""Unit tests for AlphaEvolveClient."""

import json
import pytest
from unittest.mock import MagicMock, patch
import requests

from alpha_evolve.client import AlphaEvolveClient


@pytest.fixture
def mock_auth():
    with patch("alpha_evolve.client.google.auth.default") as mock_default:
        mock_creds = MagicMock()
        mock_creds.token = "fake-token"
        mock_default.return_value = (mock_creds, "fake-project")
        yield mock_creds


@pytest.fixture
def client(mock_auth):
    return AlphaEvolveClient(
        project_id="test-project",
        location="us",
        collection="test_col",
        engine="test_engine",
        assistant="test_assistant",
        base_url="discoveryengine.googleapis.com",
    )


def test_init_url_formatting():
    # Test US location prefixing
    c1 = AlphaEvolveClient(location="us", base_url="discoveryengine.googleapis.com")
    assert c1.base_url == "https://us-discoveryengine.googleapis.com"

    # Test EU location prefixing
    c2 = AlphaEvolveClient(location="eu", base_url="discoveryengine.googleapis.com")
    assert c2.base_url == "https://eu-discoveryengine.googleapis.com"

    # Test existing https prefix
    c3 = AlphaEvolveClient(location="global", base_url="https://my-custom-endpoint.com")
    assert c3.base_url == "https://my-custom-endpoint.com"


def test_get_headers(client, mock_auth):
    headers = client._get_headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"] == "Bearer fake-token"


@patch("alpha_evolve.client.requests.post")
def test_post_request_success(mock_post, client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    res = client._post_request("https://example.com", {"key": "value"})
    assert res == {"status": "ok"}
    mock_post.assert_called_once()


@patch("alpha_evolve.client.requests.post")
def test_post_request_failure(mock_post, client):
    mock_resp = MagicMock()
    mock_resp.text = "Bad Request"
    mock_err = requests.exceptions.HTTPError("500 Server Error", response=mock_resp)
    mock_post.side_effect = mock_err

    with pytest.raises(Exception, match="API Error: Bad Request"):
        client._post_request("https://example.com", {"key": "value"})


@patch("alpha_evolve.client.requests.get")
def test_get_request_success(mock_get, client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": "item"}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    res = client._get_request("https://example.com", {"param": "1"})
    assert res == {"data": "item"}
    mock_get.assert_called_once()


@patch("alpha_evolve.client.requests.get")
def test_get_request_failure(mock_get, client):
    mock_err = requests.exceptions.RequestException("Connection Timeout")
    mock_get.side_effect = mock_err

    res = client._get_request("https://example.com")
    assert res is None


@patch("alpha_evolve.client.requests.get")
def test_get_request_failure_403(mock_get, client):
    mock_resp = MagicMock()
    mock_resp.text = "Forbidden"
    mock_resp.status_code = 403
    mock_err = requests.exceptions.HTTPError("403 Client Error: Forbidden", response=mock_resp)
    mock_get.side_effect = mock_err

    with pytest.raises(Exception, match="API Error: Forbidden"):
        client._get_request("https://example.com")


def test_get_endpoints(client):
    assert client.get_assistant_endpoint().endswith("assistants/test_assistant")
    assert client.get_sessions_endpoint().endswith("sessions")
    assert client.get_session_endpoint("sessions/123").endswith("sessions/123")
    assert client.get_alpha_evolve_experiments_endpoint("sessions/123").endswith("sessions/123/alphaEvolveExperiments")
    assert client.get_alpha_evolve_experiment_endpoint("exp/456").endswith("exp/456")
    assert client.get_alpha_evolve_programs_endpoint("exp/456").endswith("exp/456/alphaEvolvePrograms")
    assert client.get_alpha_evolve_program_endpoint("prog/789").endswith("prog/789")


@patch.object(AlphaEvolveClient, "_query_agentspace_assistant")
def test_create_session_success(mock_query, client):
    mock_query.return_value = [{"sessionInfo": {"session": "sessions/abc-123"}}]
    session_name = client.create_session()
    assert session_name == "sessions/abc-123"


@patch.object(AlphaEvolveClient, "_query_agentspace_assistant")
def test_create_session_failure(mock_query, client):
    mock_query.return_value = [{"otherInfo": {}}]
    session_name = client.create_session()
    assert session_name is None


@patch.object(AlphaEvolveClient, "_post_request")
def test_experiment_lifecycle_calls(mock_post, client):
    mock_post.return_value = {"name": "exp/123"}

    # Create experiment
    res = client.create_experiment({"title": "Test"}, "sessions/abc")
    assert res == {"name": "exp/123"}
    mock_post.assert_called_with(
        client.get_alpha_evolve_experiments_endpoint("sessions/abc"),
        data={"config": {"title": "Test"}},
    )

    # Start experiment
    client.start_experiment("exp/123")
    mock_post.assert_called_with(
        client.get_alpha_evolve_experiment_endpoint("exp/123") + ":start",
        data={"name": "exp/123"},
    )

    # Resume experiment
    client.resume_experiment("exp/123")
    mock_post.assert_called_with(
        client.get_alpha_evolve_experiment_endpoint("exp/123") + ":resume",
        data={"name": "exp/123"},
    )


@patch.object(AlphaEvolveClient, "_post_request")
def test_acquire_programs_and_submit(mock_post, client):
    mock_post.return_value = {"programs": [{"name": "prog/1", "files": []}]}

    # Acquire
    res = client.acquire_programs("exp/123", desired_programs_count=2)
    assert res == {"programs": [{"name": "prog/1", "files": []}]}
    mock_post.assert_called_with(
        client.get_alpha_evolve_experiment_endpoint("exp/123") + ":acquirePrograms",
        data={"parent": "exp/123", "desired_programs_count": 2},
    )

    # Submit evaluations
    client.submit_program_evaluations("exp/123", [{"program": "prog/1"}])
    mock_post.assert_called_with(
        client.get_alpha_evolve_experiment_endpoint("exp/123") + ":submitProgramsEvaluations",
        data={"parent": "exp/123", "evaluation_submissions": [{"program": "prog/1"}]},
    )
