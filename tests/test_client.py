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
from unittest.mock import MagicMock, patch

import pytest

from alpha_evolve.client import AlphaEvolveClient


@pytest.fixture
def client():
    return AlphaEvolveClient(
        project_id="test-project",
        location="global",
        collection="test-collection",
        engine="test-engine",
        assistant="test-assistant",
    )


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_create_experiment(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "projects/test/locations/global/collections/test/engines/test/alphaEvolveExperiments/exp1"
    }
    mock_post.return_value = mock_response

    config = {"title": "Test Experiment"}
    response = client.create_experiment(config, "test-session")

    assert (
        response["name"]
        == "projects/test/locations/global/collections/test/engines/test/alphaEvolveExperiments/exp1"
    )
    mock_post.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_create_experiment_with_generation_settings(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "projects/test/locations/global/collections/test/engines/test/alphaEvolveExperiments/exp2"
    }
    mock_post.return_value = mock_response

    config = {
        "title": "Test Experiment with Generation Settings",
        "generation_settings": {
            "models": [{"name": "gemini-2.5-flash"}]
        }
    }
    response = client.create_experiment(config, "test-session")

    assert (
        response["name"]
        == "projects/test/locations/global/collections/test/engines/test/alphaEvolveExperiments/exp2"
    )
    mock_post.assert_called_once()
    # Check that the posted data contains generation_settings
    call_args = mock_post.call_args
    posted_data = json.loads(call_args.kwargs["data"])
    assert "generation_settings" in posted_data["config"]
    assert posted_data["config"]["generation_settings"]["models"] == [
        {"name": "gemini-2.5-flash"}
    ]


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_start_experiment(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = {"name": "operations/op1"}
    mock_post.return_value = mock_response

    experiment_name = (
        "projects/test/locations/global/collections/test/engines/test/"
        "sessions/s1/alphaEvolveExperiments/exp1"
    )
    client.start_experiment(experiment_name)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    posted_data = json.loads(call_args.kwargs["data"])
    assert posted_data == {"name": experiment_name}


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_resume_experiment(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = {"name": "operations/op2"}
    mock_post.return_value = mock_response

    experiment_name = (
        "projects/test/locations/global/collections/test/engines/test/"
        "sessions/s1/alphaEvolveExperiments/exp1"
    )
    client.resume_experiment(experiment_name)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    posted_data = json.loads(call_args.kwargs["data"])
    assert posted_data == {}


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.get")
def test_list_programs(mock_get, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = {"alphaEvolvePrograms": []}
    mock_get.return_value = mock_response

    client.list_alpha_evolve_programs("test-experiment")
    mock_get.assert_called_once()


def test_client_init_locations():
    client_eu = AlphaEvolveClient(location="eu")
    assert client_eu.base_url.startswith("https://eu-")

    client_us = AlphaEvolveClient(location="US")
    assert client_us.base_url.startswith("https://us-")

    client_global = AlphaEvolveClient(location="global")
    assert client_global.base_url == "https://discoveryengine.googleapis.com"


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.logger")
def test_get_access_token(mock_logger, mock_auth, client):
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.token = "fake-token"
    mock_creds.quota_project_id = None
    mock_auth.return_value = (mock_creds, "project")

    token = client._get_access_token()

    assert token == "fake-token"
    mock_creds.refresh.assert_called_once()
    mock_logger.warning.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
@patch("alpha_evolve.client.logger")
def test_post_request_error(mock_logger, mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    from requests.exceptions import RequestException
    response_mock = MagicMock()
    response_mock.text = "Error details"
    mock_post.side_effect = RequestException(response=response_mock)

    res = client._post_request("http://test", {})
    assert res is None
    mock_logger.error.assert_called()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.get")
@patch("alpha_evolve.client.logger")
def test_get_request_error(mock_logger, mock_get, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    from requests.exceptions import RequestException
    mock_get.side_effect = RequestException(response=None)

    res = client._get_request("http://test")
    assert res is None
    mock_logger.error.assert_called()


def test_endpoints(client):
    assert client.get_assistant_endpoint().endswith("assistants/test-assistant")
    assert client.get_sessions_endpoint().endswith("sessions")
    assert client.get_session_endpoint("s1").endswith("s1")
    assert client.get_alpha_evolve_experiments_endpoint("s1").endswith("s1/alphaEvolveExperiments")
    assert client.get_alpha_evolve_experiment_endpoint("e1").endswith("e1")
    assert client.get_alpha_evolve_programs_endpoint("e1").endswith("e1/alphaEvolvePrograms")
    assert client.get_alpha_evolve_program_endpoint("p1").endswith("p1")


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_create_session(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"sessionInfo": {"session": "projects/p/locations/l/collections/c/engines/e/sessions/s1"}}
    ]
    mock_post.return_value = mock_response

    session = client.create_session()
    assert session == "projects/p/locations/l/collections/c/engines/e/sessions/s1"

    # Test None response (by triggering an exception in post)
    from requests.exceptions import RequestException
    mock_post.return_value = None
    mock_post.side_effect = RequestException()
    assert client.create_session() is None



def test_get_session_name_edges(client):
    # Missing sessionInfo
    assert client._get_session_name([{}]) is None
    # Missing session
    assert client._get_session_name([{"sessionInfo": {}}]) is None


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.get")
def test_get_session_info(mock_get, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")
    client.get_session_info("s1")
    mock_get.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.get")
def test_get_alpha_evolve_experiment(mock_get, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")
    client.get_alpha_evolve_experiment("e1")
    mock_get.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.get")
def test_list_alpha_evolve_experiments(mock_get, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")
    client.list_alpha_evolve_experiments("s1")
    mock_get.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_create_initial_program(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")
    client.create_initial_program("e1", {"content": "foo"})
    mock_post.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.get")
def test_get_alpha_evolve_program(mock_get, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")
    client.get_alpha_evolve_program("p1")
    mock_get.assert_called_once()


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_acquire_programs(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "programs": [
            {"content": {"files": [{"content": "File: main.py\n---\nprint(1)\n---"}]}}
        ]
    }
    mock_post.return_value = mock_response

    res = client.acquire_programs("e1", 1)
    mock_post.assert_called_once()
    assert res["programs"][0]["content"]["files"][0]["path"] == "main.py"


@patch("alpha_evolve.client.google.auth.default")
@patch("alpha_evolve.client.requests.post")
def test_submit_program_evaluations(mock_post, mock_auth, client):
    mock_auth.return_value = (MagicMock(), "project")
    client.submit_program_evaluations("e1", [])
    mock_post.assert_called_once()

