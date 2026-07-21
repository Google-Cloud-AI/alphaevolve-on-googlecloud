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

"""REST client for the AlphaEvolve Discovery Engine API.

Thin wrapper around requests + google-auth ADC for the
discoveryengine.googleapis.com/v1alpha HTTP API.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import time
import typing
import warnings

import google.auth
import google.auth.transport.requests
import requests

from . import config


class ApiError(Exception):
  """Structured API error."""

  def __init__(
      self,
      status_code: int,
      message: str,
      details: typing.Any = None,
  ):
    """Initializes a structured API error.

    Args:
      status_code: The HTTP status code returned by the API.
      message: A descriptive error message.
      details: Optional extended error details (e.g., JSON structure).
    """
    self.status_code = status_code
    self.message = message
    self.details = details
    super().__init__(f"[{status_code}] {message}")


def build_base_url(location: str) -> str:
  """Builds the API base URL for the given location.

  Args:
    location: The GCP location (e.g., 'us-central1', 'global').

  Returns:
    The full HTTPS base URL for the API.
  """
  loc = location.lower()
  if loc in ("us", "us-central1"):
    return "https://us-discoveryengine.googleapis.com"
  elif loc in ("eu", "europe-west1"):
    return "https://eu-discoveryengine.googleapis.com"
  return "https://discoveryengine.googleapis.com"


class AlphaEvolveClient:
  """REST client for the AlphaEvolve Discovery Engine API."""

  API_VERSION = "v1alpha"

  def __init__(
      self,
      cfg: config.Config,
      verbose: bool = False,
  ):
    """Initializes the AlphaEvolveClient.

    Args:
      cfg: The Config object containing project, location, etc.
      verbose: If True, enables debug logging for HTTP requests/responses.
    """
    self._config = cfg
    self._verbose = verbose

    # The Discovery Engine API requires a numeric project number in resource
    # paths.  A non-numeric project ID (e.g. "my-project") causes cryptic
    # "invalid argument" errors from the API.
    if cfg.project and not cfg.project.isdigit():
      raise ValueError(
          f"Project '{cfg.project}' is not a numeric project number. "
          "The Discovery Engine API requires a numeric project number. "
          "Set it with: ae config --project=<NUMERIC_PROJECT_NUMBER>\n"
          "You can find your project number in the Google Cloud Console "
          "or by running: gcloud projects describe <PROJECT_ID> "
          "--format='value(projectNumber)'"
      )

    self._session = requests.Session()
    self._base_url = cfg.base_url or build_base_url(cfg.location)
    if self._base_url and not self._base_url.startswith(
        ("http://", "https://")
    ):
      self._base_url = f"https://{self._base_url}"

    # Authenticate via ADC.
    self._credentials, self._gcp_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    self._auth_request = google.auth.transport.requests.Request()
    self._resolved_session = None  # Cache for resolved session ID

  # -----------------------------------------------------------------
  # URL construction
  # -----------------------------------------------------------------

  @property
  def _parent(self) -> str:
    """Builds the parent resource path, resolving session dynamically.

    Returns:
      The full resource path string for the active session target layer.
    """
    session = self._resolve_session_id()
    return (
        f"projects/{self._config.project}"
        f"/locations/{self._config.location}"
        f"/collections/{self._config.collection}"
        f"/engines/{self._config.engine}"
        f"/sessions/{session}"
    )

  def _resolve_session_id(self) -> str:
    """Resolves template-style Session ID or creates a new one.

    If the session is set to '[create new]', it triggers CreateSession to
    provision a fresh numerical session ID from the server.

    Returns:
      The resolved Session ID string.
    """
    val = self._config.session
    if val == "[create new]":
      if not self._resolved_session:
        try:
          self._resolved_session = self.create_session()
        except Exception as e:  # pylint: disable=broad-exception-caught
          if self._verbose:
            print(f"Session creation failed: {e}")
          return val
      return self._resolved_session
    return val

  def create_session(self) -> str:
    """Creates a new Session explicitly via CreateSession RPC.

    Returns:
      The extracted Session ID string from response.

    Raises:
      ApiError: If the CreateSession call fails.
    """
    parent = (
        f"projects/{self._config.project}"
        f"/locations/{self._config.location}"
        f"/collections/{self._config.collection}"
        f"/engines/{self._config.engine}"
    )
    if self._verbose:
      print("Provisioning a new session ID from the server...")

    resp = self._request(
        "POST",
        f"{parent}/sessions",
        json_body={"display_name": "AlphaEvolve Session"},
    )

    session_name = resp.get("name")
    if session_name:
      return session_name.split("/")[-1]

    raise ApiError(
        500, "Failed to extract session name from CreateSession response."
    )

  def list_sessions(
      self,
      page_size: int = 100,
      **extra_params: typing.Any,
  ) -> Iterator[dict[str, typing.Any]]:
    """Lists Sessions for the configured Engine tier.

    Args:
      page_size: Max number of items to return per page request.
      **extra_params: Optional parameters to pass into query URL.

    Returns:
      An Iterator yielding dict objects representing Session details.
    """
    # Remove '/sessions/...' part from parent to get engine parent
    path = (
        f"projects/{self._config.project}"
        f"/locations/{self._config.location}"
        f"/collections/{self._config.collection}"
        f"/engines/{self._config.engine}"
        "/sessions"
    )
    return self._list_all(
        path,
        "sessions",
        pageSize=page_size,
        **extra_params,
    )

  def list_engines(
      self,
      page_size: int = 100,
      **extra_params: typing.Any,
  ) -> Iterator[dict[str, typing.Any]]:
    """Lists Engines for the configured project/location/collection."""
    path = (
        f"projects/{self._config.project}"
        f"/locations/{self._config.location}"
        f"/collections/{self._config.collection}"
        "/engines"
    )
    return self._list_all(
        path,
        "engines",
        pageSize=page_size,
        **extra_params,
    )

  def _url(self, path: str) -> str:
    """Builds a full API URL from a relative path.

    Args:
      path: The relative endpoint path (e.g., 'alphaEvolveExperiments').

    Returns:
      Full string URL targeting the API surface.
    """
    return f"{self._base_url}/{self.API_VERSION}/{path}"

  # -----------------------------------------------------------------
  # HTTP helpers
  # -----------------------------------------------------------------

  def _refresh_credentials(self) -> None:
    """Refresh ADC credentials if needed."""
    if not self._credentials.valid:
      self._credentials.refresh(self._auth_request)

  def _headers(self) -> dict[str, str]:
    """Build request headers with auth + quota attribution."""
    self._refresh_credentials()
    headers = {
        "Authorization": f"Bearer {self._credentials.token}",
        "Content-Type": "application/json",
    }
    project = self._config.project or self._gcp_project
    if project:
      headers["x-goog-user-project"] = project
    return headers

  def _request(
      self,
      method: str,
      path: str,
      params: dict[str, typing.Any] | None = None,
      json_body: dict[str, typing.Any] | None = None,
  ) -> dict[str, typing.Any]:
    """Makes an authenticated HTTP request to the API surface.

    Args:
      method: The HTTP method (e.g. 'GET', 'POST').
      path: The relative endpoint path target.
      params: Optional dictionary of URL query parameters.
      json_body: Optional dictionary of JSON request payload body.

    Returns:
      A dictionary representation of the JSON response body.

    Raises:
      ApiError: If the response status code is 400 or above.
    """
    url = self._url(path)
    headers = self._headers()

    if self._verbose:
      print(f"  → {method} {url}")
      if json_body:
        print(f"    body: {json.dumps(json_body, indent=2)[:500]}")

    resp = self._session.request(
        method, url, headers=headers, params=params, json=json_body, timeout=60
    )

    if self._verbose:
      print(f"  ← {resp.status_code}")
      if resp.status_code >= 400:
        print(f"  ← BODY: {resp.text[:2000]}")

    if resp.status_code >= 400:
      try:
        err = resp.json()
        msg = err.get("error", {}).get("message", resp.text)
        details = err.get("error", {}).get("details")
      except Exception:  # pylint: disable=broad-exception-caught
        msg = resp.text
        details = None
      raise ApiError(resp.status_code, msg, details)

    if resp.status_code == 204 or not resp.content:
      return {}
    try:
      return resp.json()
    except Exception:  # pylint: disable=broad-exception-caught
      return {}

  def _get(
      self,
      path: str,
      **params: typing.Any,
  ) -> dict[str, typing.Any]:
    return self._request("GET", path, params=params or None)

  def _post(
      self,
      path: str,
      body: dict[str, typing.Any] | None = None,
  ) -> dict[str, typing.Any]:
    return self._request("POST", path, json_body=body)

  def _delete(self, path: str) -> dict[str, typing.Any]:
    return self._request("DELETE", path)

  # -----------------------------------------------------------------
  # Pagination
  # -----------------------------------------------------------------

  def _list_all(
      self,
      path: str,
      key: str,
      **params: typing.Any,
  ) -> Iterator[dict[str, typing.Any]]:
    """Auto-paginates through all results for a list-type endpoint.

    Args:
      path: The relative endpoint path.
      key: The response dict key containing the items array.
      **params: URL query parameters forwarded to each page request.

    Yields:
      Individual item dictionaries from each page.
    """
    while True:
      resp = self._get(path, **params)
      yield from resp.get(key, [])
      token = resp.get("nextPageToken")
      if not token:
        break
      params["pageToken"] = token

  # -----------------------------------------------------------------
  # LRO handling
  # -----------------------------------------------------------------

  def get_operation(self, operation_name: str) -> dict[str, typing.Any]:
    """Gets the current state of a long-running operation.

    Args:
      operation_name: The full resource name of the operation.

    Returns:
      A dictionary representation of the Operation resource.
    """
    return self._get(operation_name)

  def poll_operation(
      self,
      operation_name: str,
      poll_interval: float = 5.0,
      timeout: float = 3600.0,
  ) -> dict[str, typing.Any]:
    """Polls a long-running operation until done or timeout.

    Args:
      operation_name: The full resource name of the operation.
      poll_interval: Seconds to sleep between poll requests.
      timeout: Maximum seconds to wait before timing out.

    Returns:
      The response object if successful.

    Raises:
      ApiError: If the operation fails or times out.
    """
    start = time.time()
    while time.time() - start < timeout:
      result = self._get(operation_name)
      if result.get("done"):
        if "error" in result:
          err = result["error"]
          raise ApiError(
              err.get("code", 500),
              err.get("message", "Operation failed"),
          )
        return result.get("response", result)
      time.sleep(poll_interval)
    raise ApiError(
        408, f"Operation timed out after {timeout}s: {operation_name}"
    )

  # -----------------------------------------------------------------
  # Experiments
  # -----------------------------------------------------------------

  def create_experiment(
      self,
      body: dict[str, typing.Any],
  ) -> dict[str, typing.Any]:
    """Creates a new AlphaEvolve experiment.

    Args:
      body: The JSON payload dict specifying experiment configurations.

    Returns:
      The created Experiment resource representation.
    """
    path = f"{self._parent}/alphaEvolveExperiments"
    return self._post(path, body)

  def get_experiment(self, experiment_name: str) -> dict[str, typing.Any]:
    """Gets an existing AlphaEvolve experiment.

    Args:
      experiment_name: The full resource name of the experiment.

    Returns:
      The Experiment resource representation.
    """
    return self._get(experiment_name)

  def list_experiments(
      self,
      session_id: str | None = None,
      page_size: int = 100,
      **extra_params: typing.Any,
  ) -> Iterator[dict[str, typing.Any]]:
    """Lists AlphaEvolveExperiments (auto-paginated).

    Args:
      session_id: Optional session ID to scope the listing.
      page_size: Max items per page.
      **extra_params: Additional URL query parameters.

    Returns:
      An iterator yielding Experiment dictionaries.
    """
    if session_id:
      parent = (
          f"projects/{self._config.project}"
          f"/locations/{self._config.location}"
          f"/collections/{self._config.collection}"
          f"/engines/{self._config.engine}"
          f"/sessions/{session_id}"
      )
    else:
      parent = self._parent
    path = f"{parent}/alphaEvolveExperiments"
    return self._list_all(
        path,
        "alphaEvolveExperiments",
        pageSize=page_size,
        **extra_params,
    )

  def start_experiment(
      self,
      experiment_name: str,
  ) -> dict[str, typing.Any]:
    """Starts an experiment cycle (returns an LRO).

    The seed program is the one created via ``create_program``; the server
    uses it automatically, so no program is passed here.

    Args:
      experiment_name: The full resource name string target.

    Returns:
      The Long Running Operation (LRO) state representation.
    """
    return self._post(f"{experiment_name}:start", {"name": experiment_name})

  def resume_experiment(self, experiment_name: str) -> dict[str, typing.Any]:
    """Resumes an experiment cycle (returns an LRO).

    Args:
      experiment_name: The full resource name string target.

    Returns:
      The Long Running Operation (LRO) state representation.
    """
    return self._post(f"{experiment_name}:resume", {"name": experiment_name})

  def delete_experiment(self, experiment_name: str) -> dict[str, typing.Any]:
    """Deletes an AlphaEvolve experiment and its programs.

    Args:
      experiment_name: The full resource name of the experiment.

    Returns:
      The deletion response dictionary.
    """
    return self._delete(experiment_name)

  # -----------------------------------------------------------------
  # Programs
  # -----------------------------------------------------------------

  def create_program(
      self,
      experiment_name: str,
      body: dict[str, typing.Any],
  ) -> dict[str, typing.Any]:
    """Creates a new AlphaEvolveProgram.

    Args:
      experiment_name: The full resource name target.
      body: The JSON payload dict configuration.

    Returns:
      The created Program dictionary state.
    """
    path = f"{experiment_name}/alphaEvolvePrograms"
    return self._post(path, body)

  def get_program(self, program_name: str) -> dict[str, typing.Any]:
    """Gets an existing AlphaEvolveProgram.

    The backend endpoint GetAlphaEvolveProgram may not be routed on v1alpha,
    so callers should prefer the CLI-layer workaround if they need reliable
    retrieval.

    Args:
      program_name: The full resource name of the program.

    Returns:
      The Program dictionary.
    """


    return self._get(program_name)

  def list_programs(
      self,
      experiment_name: str,
      order_by: str | None = None,
      state_filter: str | None = None,
      page_size: int = 100,
  ) -> Iterator[dict[str, typing.Any]]:
    """Lists AlphaEvolvePrograms (auto-paginated).

    Args:
      experiment_name: The full experiment resource name.
      order_by: Optional sort expression (e.g., 'evaluation.scores desc').
      state_filter: Optional state filter (e.g., 'COMPLETED').
      page_size: Max items per page.

    Returns:
      An iterator yielding Program dictionaries.
    """
    path = f"{experiment_name}/alphaEvolvePrograms"
    params: dict[str, typing.Any] = {"pageSize": page_size}
    if order_by:
      params["orderBy"] = order_by
    if state_filter:
      params["filter"] = f'state="{state_filter}"'
    return self._list_all(path, "alphaEvolvePrograms", **params)

  def acquire_programs(
      self,
      experiment_name: str,
      desired_count: int = 1,
  ) -> dict[str, typing.Any]:
    """Acquires programs for processing or evaluations.

    Args:
      experiment_name: The full experiment resource name.
      desired_count: Number of programs to acquire.

    Returns:
      The acquisition response dictionary.
    """
    path = f"{experiment_name}:acquirePrograms"
    return self._post(
        path,
        {
            "parent": experiment_name,
            "desiredProgramsCount": desired_count,
        },
    )

  # -----------------------------------------------------------------
  # Evaluations
  # -----------------------------------------------------------------

  def submit_evaluations(
      self,
      experiment_name: str,
      submissions: list[dict[str, typing.Any]],
  ) -> dict[str, typing.Any]:
    """Submits evaluation results back to the backend.

    Note: The API only supports one submission per call. Submissions are
    issued one at a time; any failure raises ApiError.

    Args:
      experiment_name: The full experiment resource name.
      submissions: A list of evaluation submission dictionaries.

    Returns:
      An empty dict, matching the empty SubmitProgramsEvaluationsResponse.
    """
    path = f"{experiment_name}:submitProgramsEvaluations"
    for submission in submissions:
      resp = self._post(
          path,
          {
              "parent": experiment_name,
              "evaluationSubmissions": [submission],
          },
      )
      if resp:
        warnings.warn(
            "Expected submitProgramsEvaluations to return an empty response; "
            f"got {resp}",
            stacklevel=2,
        )
    return {}
