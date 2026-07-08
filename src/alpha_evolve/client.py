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
import logging
import threading
import warnings
from typing import Any, Dict, List, Optional

import google.auth
import google.auth.transport.requests
import requests

from .utils import fix_multi_files_program

logger = logging.getLogger(__name__)


class AlphaEvolveClient:
    """Client for interacting with AlphaEvolve experiments."""

    def __init__(
        self,
        project_id: str = "",
        location: str = "global",
        collection: str = "default_collection",
        engine: str = "",
        assistant: str = "default_assistant",
        base_url: str = "discoveryengine.googleapis.com",
    ):
        """Initializes the AlphaEvolveClient.

        Args:
          project_id: Google Cloud project ID.
          location: Location of the discovery engine resources.
          collection: Discovery engine collection ID.
          engine: Discovery engine engine ID.
          assistant: Discovery engine assistant ID.
        """
        self.project_id = project_id
        self.location = location
        self.collection = collection
        self.engine = engine
        self.assistant = assistant
        self.base_url = base_url

        if location.upper() == "EU":
            self.base_url = "eu-" + self.base_url
        elif location.upper() == "US":
            self.base_url = "us-" + self.base_url

        if not self.base_url.startswith("https://"):
            self.base_url = "https://" + self.base_url

        self.base_path = f"projects/{self.project_id}/locations/{self.location}/collections/{self.collection}/engines/{self.engine}"

        self._credentials = None
        self._auth_request = None
        self._auth_lock = threading.Lock()

    def _get_access_token(self):
        with self._auth_lock:
            if self._credentials is None:
                # Discover credentials once and reuse them across requests. The
                # verbose per-call ADC warning is silenced; instead we surface a
                # single actionable message below when no quota project is set.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="Your application has authenticated using end user credentials",
                    )
                    self._credentials, _ = google.auth.default()
                self._auth_request = google.auth.transport.requests.Request()
                if not getattr(self._credentials, "quota_project_id", None):
                    logger.warning(
                        "No quota project set on your credentials; API usage is "
                        "attributed to '%s'. If you hit quota or 'API not "
                        "enabled' errors, run: "
                        "gcloud auth application-default set-quota-project %s",
                        self.project_id,
                        self.project_id,
                    )
            if not self._credentials.valid:
                self._credentials.refresh(self._auth_request)
            return self._credentials.token

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

    def _post_request(self, url: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        headers = self._get_headers()
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making POST request to {url}: {e}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return None

    def _get_request(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        headers = self._get_headers()
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making GET request to {url}: {e}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return None

    def get_assistant_endpoint(self) -> str:
        return f"{self.base_url}/v1alpha/{self.base_path}/assistants/{self.assistant}"

    def get_sessions_endpoint(self) -> str:
        return f"{self.base_url}/v1alpha/{self.base_path}/sessions"

    def get_session_endpoint(self, session_name: str) -> str:
        return f"{self.base_url}/v1alpha/{session_name}"

    def get_alpha_evolve_experiments_endpoint(self, session_name: str) -> str:
        return f"{self.base_url}/v1alpha/{session_name}/alphaEvolveExperiments"

    def get_alpha_evolve_experiment_endpoint(self, experiment_name: str) -> str:
        return f"{self.base_url}/v1alpha/{experiment_name}"

    def get_alpha_evolve_programs_endpoint(self, experiment_name: str) -> str:
        return f"{self.base_url}/v1alpha/{experiment_name}/alphaEvolvePrograms"

    def get_alpha_evolve_program_endpoint(self, program_name: str) -> str:
        return f"{self.base_url}/v1alpha/{program_name}"

    def _query_agentspace_assistant(self, query: str) -> Optional[Dict[str, Any]]:
        """Queries the agentspace assistant."""
        return self._post_request(
            self.get_assistant_endpoint() + ":streamAssist",
            data={
                "query": {"text": query},
                "assistSkippingMode": "REQUEST_ASSIST",
            },
        )

    def create_session(self) -> Optional[str]:
        """Creates a new session."""
        placeholder_query = "starting alpha evolve query"
        assistant_response = self._query_agentspace_assistant(placeholder_query)
        if assistant_response:
            session_name = self._get_session_name(assistant_response)
            return session_name
        return None

    def _get_session_name(
        self, assistant_response: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Extracts session name from assistant response."""
        # The response structure from streamAssist can be a list of messages.
        # We handle it as a list here as per the original code.
        answers = assistant_response
        for answer in answers:
            if "sessionInfo" in answer:
                if "session" in answer["sessionInfo"]:
                    session_name = answer["sessionInfo"]["session"]
                    return session_name
        return None

    def get_session_info(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Gets information about a session."""
        return self._get_request(
            self.get_session_endpoint(session_name),
        )

    def create_experiment(
        self, exp_config: Dict[str, Any], session_name: str
    ) -> Optional[Dict[str, Any]]:
        """Creates an AlphaEvolve experiment."""
        logger.info(f"Creating AlphaEvolve experiment on session: {session_name}.")
        req = {"config": exp_config}
        response = self._post_request(
            self.get_alpha_evolve_experiments_endpoint(session_name),
            data=req,
        )
        return response

    def start_experiment(self, experiment_name: str) -> Optional[Dict[str, Any]]:
        """Starts an AlphaEvolve experiment."""
        logger.info(f"Starting AlphaEvolve experiment: {experiment_name}.")
        req = {"name": experiment_name}
        response = self._post_request(
            self.get_alpha_evolve_experiment_endpoint(experiment_name) + ":start",
            data=req,
        )
        return response

    def resume_experiment(self, experiment_name: str) -> Optional[Dict[str, Any]]:
        """Resumes an AlphaEvolve experiment."""
        logger.info(f"Resuming AlphaEvolve experiment: {experiment_name}.")
        req = {}
        response = self._post_request(
            self.get_alpha_evolve_experiment_endpoint(experiment_name) + ":resume",
            data=req,
        )
        return response

    def get_alpha_evolve_experiment(
        self, experiment_name: str
    ) -> Optional[Dict[str, Any]]:
        """Gets information about an AlphaEvolve experiment."""
        return self._get_request(
            self.get_alpha_evolve_experiment_endpoint(experiment_name),
        )

    def list_alpha_evolve_experiments(
        self, session_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Lists AlphaEvolve experiments for a session."""
        return self._get_request(
            self.get_alpha_evolve_experiments_endpoint(session_name), params=params
        )

    def create_initial_program(
        self, experiment_name: str, alpha_evolve_program: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Creates an initial program for an experiment."""
        logger.info(f"Creating initial program for experiment: {experiment_name}")

        request_data = alpha_evolve_program
        return self._post_request(
            self.get_alpha_evolve_programs_endpoint(experiment_name),
            data=request_data,
        )

    def get_alpha_evolve_program(self, program_name: str) -> Optional[Dict[str, Any]]:
        """Gets information about an AlphaEvolve program."""
        return self._get_request(
            self.get_alpha_evolve_program_endpoint(program_name),
        )

    def list_alpha_evolve_programs(
        self, experiment_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        return self._get_request(
            self.get_alpha_evolve_programs_endpoint(experiment_name), params=params
        )

    def acquire_programs(
        self, experiment_name: str, desired_programs_count: Optional[int] = 1
    ):
        logger.debug(
            "Requesting up to %d programs from experiment %s",
            desired_programs_count,
            experiment_name,
        )
        request_data = {
            "parent": experiment_name,
            "desired_programs_count": desired_programs_count,
        }
        response = self._post_request(
            self.get_alpha_evolve_experiment_endpoint(experiment_name)
            + ":acquirePrograms",
            data=request_data,
        )
        # TODO: remove when fix is in.
        if response and "programs" in response:
            for program in response["programs"]:
                fix_multi_files_program(program)
        return response

    def submit_program_evaluations(
        self, experiment_name: str, evaluation_submissions: List[Dict[str, Any]]
    ):
        logger.debug(
            "Submitting %d evaluation(s) for experiment %s",
            len(evaluation_submissions),
            experiment_name,
        )
        request_data = {
            "parent": experiment_name,
            "evaluation_submissions": evaluation_submissions,
        }
        return self._post_request(
            self.get_alpha_evolve_experiment_endpoint(experiment_name)
            + ":submitProgramsEvaluations",
            data=request_data,
        )
