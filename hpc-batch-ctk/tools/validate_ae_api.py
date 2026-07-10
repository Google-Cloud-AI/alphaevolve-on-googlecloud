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

"""Standalone AlphaEvolve API validation script.

Executed automatically during gcluster deploy of alpha-evolve-experiment.yaml.
"""

import os
import sys
import json
import requests
import google.auth

def log_msg(severity, message):
    print(f"[{severity}] {message}")

def check_alpha_evolve_api(credentials):
    log_msg("INFO", "Checking AlphaEvolve API (Discovery Engine) connectivity...")
    try:
        if not credentials.token:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())

        project_id = os.environ.get("_PROJECT_ID")
        base_url = os.environ.get("_BASE_URL")
        location = os.getenv("_LOCATION")
        collection = os.getenv("_COLLECTION")
        engine = os.getenv("_ENGINE")
        assistant = os.getenv("_ASSISTANT")
        url = f"https://{base_url}/v1alpha/projects/{project_id}/locations/{location}/collections/{collection}/engines/{engine}/assistants/{assistant}:streamAssist"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {credentials.token}"}
        data = {"query": {"text": "starting alpha evolve query"}, "assistSkippingMode": "REQUEST_ASSIST"}
        log_msg("INFO", f"Sending POST request to {url}")
        resp = requests.post(url, headers=headers, data=json.dumps(data))
        log_msg("INFO", f"Received response status code: {resp.status_code}")
        if resp.status_code == 200:
            log_msg("INFO", "AlphaEvolve API session creation mock successful.")
            return True
        elif resp.status_code == 403 or resp.status_code == 404:
            log_msg("ERROR", "AlphaEvolve API returned 403 Forbidden or 404 Not Found. Permission issue or project not allowlisted for early access.")
            return False
        else:
            log_msg("ERROR", f"AlphaEvolve API check failed with status code: {resp.status_code}")
            if resp.text:
                log_msg("ERROR", f"Response: {resp.text}")
            return False
    except Exception as e:
        log_msg("ERROR", f"AlphaEvolve API check failed: {e}")
        return False

def main():
    log_msg("INFO", "=== Starting AlphaEvolve API Validation ===")

    try:
        credentials, project = google.auth.default()
    except Exception as e:
        log_msg("ERROR", f"Failed to acquire Google Cloud credentials: {e}")
        sys.exit(1)

    if not check_alpha_evolve_api(credentials):
        log_msg("ERROR", "AlphaEvolve API validation failed. Please check permissions or EAP allowlisting.")
        sys.exit(1)

    log_msg("INFO", "=== AlphaEvolve API Validation Completed Successfully ===")
    sys.exit(0)

if __name__ == "__main__":
    main()
