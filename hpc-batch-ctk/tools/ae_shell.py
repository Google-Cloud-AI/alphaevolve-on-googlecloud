#!/usr/bin/env python3

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

import cmd
import json
import os
import subprocess
import urllib.error
import urllib.request

class AeShell(cmd.Cmd):
    prompt = 'ae> '
    intro = 'Welcome to the Alpha Evolve Shell. Type help or ? to list commands.\n'

    def __init__(self):
        super().__init__()
        # Update these with your project id and project number from https://console.cloud.google.com/home/dashboard?project=my_project
        self.project_id = os.environ.get('_PROJECT_ID', 'my_project')
        self.project_number = os.environ.get('_PROJECT_NUMBER', '123456789012')
        self.engine_id = os.environ.get('_ENGINE', 'alpha-evolve-experiment-engine')
        self.assistant_id = os.environ.get('_ASSISTANT', 'default_assistant')
        self.session_id = os.environ.get('_SESSION', '')
        self.experiment_id = os.environ.get('_EXPERIMENT', '')
        self.datastore_id = os.environ.get('_DATASTORE', '')

    def get_auth_token(self):
        try:
          result = subprocess.run(
                ["gcloud", "auth", "application-default", "print-access-token"],
                stdout=subprocess.PIPE,   # Replaces capture_output=True (for stdout)
                stderr=subprocess.PIPE,   # Replaces capture_output=True (for stderr)
                universal_newlines=True,  # Replaces text=True
                check=True,
            )
          return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error getting auth token: {e}")
            return None
        except FileNotFoundError:
            print("Error: gcloud command not found. Please ensure Google Cloud SDK is installed.")
            return None

    def make_request(self, method, url, data=None):
        token = self.get_auth_token()
        if not token:
            return

        headers = {
            'Content-Type': 'application/json',
            'x-goog-user-project': self.project_id,
            'Authorization': f'Bearer {token}'
        }

        req = urllib.request.Request(url, headers=headers, method=method)
        if data:
            req.data = json.dumps(data).encode('utf-8')

        try:
            with urllib.request.urlopen(req) as response:
                resp_text = response.read().decode('utf-8')
                try:
                    # Try to pretty print JSON
                    parsed = json.loads(resp_text)
                    print(json.dumps(parsed, indent=2))
                    return parsed
                except json.JSONDecodeError:
                    print(resp_text)
                    return resp_text
        except urllib.error.HTTPError as e:
            print(f"HTTP Error: {e.code} - {e.reason}")
            try:
                print(e.read().decode('utf-8'))
            except Exception:
                pass
        except Exception as e:
            print(f"Error: {e}")
        return None

    def do_create_engine(self, arg):
        """Create Engine"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines?engineId={self.engine_id}"
        data = {
            "display_name": self.engine_id,
            "data_store_ids": [],
            "solution_type": "SOLUTION_TYPE_GENERATIVE_CHAT"
        }
        print(f"Creating Engine '{self.engine_id}'...")
        self.make_request('POST', url, data)

    def do_delete_engine(self, arg):
        """Delete Engine"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.engine_id}"
        print(f"Deleting Engine '{self.engine_id}'...")
        self.make_request('DELETE', url)

    def do_list_engines(self, arg):
        """List Engines"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines"
        print(f"Listing Engines for Project '{self.project_id}'...")
        self.make_request('GET', url)

    def do_create_assistant(self, arg):
        """Create Assistant"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.engine_id}/assistants?assistantId={self.assistant_id}"
        data = {
            "display_name": self.assistant_id,
            "description": None,
            "generation_config": None,
            "web_grounding_type": "WEB_GROUNDING_TYPE_UNSPECIFIED",
            "enabled_actions": None,
            "customer_policy": None
        }
        print(f"Creating Assistant '{self.assistant_id}' for Engine '{self.engine_id}'...")
        self.make_request('POST', url, data)

    def do_delete_assistant(self, arg):
        """Delete Assistant"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.engine_id}/assistants/{self.assistant_id}"
        print(f"Deleting Assistant '{self.assistant_id}' from Engine '{self.engine_id}'...")
        self.make_request('DELETE', url)

    def do_list_assistants(self, arg):
        """List Assistants"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.engine_id}/assistants"
        print(f"Listing Assistants for Engine '{self.engine_id}'...")
        resp = self.make_request('GET', url)
        if resp and isinstance(resp, dict):
            assistants = resp.get('assistants', [])
            if assistants:
                assistant_path = assistants[0].get('name')
                if assistant_path:
                    self.assistant_id = assistant_path.split('/')[-1]
                    print(f"Captured Assistant ID: {self.assistant_id}")

    def do_create_session(self, arg):
        """Create Session"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.engine_id}/assistants/default_assistant:streamAssist"
        data = {
            "query": {"text": "starting alpha evolve query"},
            "assistSkippingMode": "REQUEST_ASSIST"
        }
        print(f"Creating Session for Engine '{self.engine_id}' using 'default_assistant'...")
        resp = self.make_request('POST', url, data)
        if resp and isinstance(resp, dict):
            session_path = resp.get('session')
            if session_path:
                self.session_id = session_path.split('/')[-1]
                print(f"Captured Session ID: {self.session_id}")
                print(f"Full Session Path: {session_path}")

    def do_list_sessions(self, arg):
        """List Sessions"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/engines/{self.engine_id}/sessions"
        print(f"Listing Sessions for Engine '{self.engine_id}'...")
        resp = self.make_request('GET', url)
        if resp and isinstance(resp, dict):
            sessions = resp.get('sessions', [])
            if sessions:
                session_path = sessions[0].get('name')
                if session_path:
                    self.session_id = session_path.split('/')[-1]
                    print(f"Captured Session ID: {self.session_id}")

    def do_list_datastores(self, arg):
        """List Data Stores"""
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_id}/locations/global/collections/default_collection/dataStores"
        print(f"Listing Data Stores for Project '{self.project_id}'...")
        resp = self.make_request('GET', url)
        if resp and isinstance(resp, dict):
            datastores = resp.get('dataStores', [])
            if datastores:
                datastore_path = datastores[0].get('name')
                if datastore_path:
                    self.datastore_id = datastore_path.split('/')[-1]
                    print(f"Captured Data Store ID: {self.datastore_id}")

    def do_list_experiments(self, arg):
        """List Experiments (requires SESSION_ID)"""
        if not self.session_id:
            print("Error: SESSION_ID is not set. Run create_session or set it.")
            return
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_number}/locations/global/collections/default_collection/engines/{self.engine_id}/sessions/{self.session_id}/alphaEvolveExperiments"
        print(f"Listing Alpha Evolve Experiments for Session '{self.session_id}'...")
        self.make_request('GET', url)

    def do_list_programs(self, arg):
        """List Programs (requires SESSION_ID and EXPERIMENT_ID)"""
        if not self.session_id:
            print("Error: SESSION_ID is not set.")
            return
        if not self.experiment_id:
            print("Error: EXPERIMENT_ID is not set. Set it using 'set experiment_id <id>'.")
            return
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{self.project_number}/locations/global/collections/default_collection/engines/{self.engine_id}/sessions/{self.session_id}/alphaEvolveExperiments/{self.experiment_id}/alphaEvolvePrograms"
        print(f"Listing Alpha Evolve Programs for Experiment '{self.experiment_id}' in Session '{self.session_id}'...")
        self.make_request('GET', url)

    def do_set(self, arg):
        """Set a variable. Usage: set <variable> <value>
        Variables: project_id, project_number, engine_id, assistant_id, session_id, experiment_id
        """
        parts = arg.split()
        if len(parts) != 2:
            print("Usage: set <variable> <value>")
            return
        var, val = parts
        var = var.lower()
        allowed_vars = ['project_id', 'project_number', 'engine_id', 'assistant_id', 'session_id', 'experiment_id']
        if var in allowed_vars:
            setattr(self, var, val)
            print(f"{var} set to {val}")
        else:
            print(f"Unknown variable: {var}")

    def do_show(self, arg):
        """Show current variables"""
        print(f"PROJECT_ID: {self.project_id}")
        print(f"PROJECT_NUMBER: {self.project_number}")
        print(f"ENGINE_ID: {self.engine_id}")
        print(f"ASSISTANT_ID: {self.assistant_id}")
        print(f"SESSION_ID: {self.session_id}")
        print(f"EXPERIMENT_ID: {self.experiment_id}")

    def do_exit(self, arg):
        """Exit the shell"""
        print("Exiting.")
        return True

    def do_EOF(self, arg):
        """Exit on Ctrl-D"""
        print()
        return self.do_exit(arg)

if __name__ == '__main__':
    AeShell().cmdloop()
