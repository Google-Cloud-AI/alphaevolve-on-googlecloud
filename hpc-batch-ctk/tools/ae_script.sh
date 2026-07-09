#!/bin/bash

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

PROJECT_ID=hpc-solutions-04
PROJECT_NUMBER=771474336186
ENGINE_ID=alpha-evolve-infra-experiment-engine
ASSISTANT_ID=default_assistant
# Ensure required environment variables are set
if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: PROJECT_ID environment variable is not set."
  exit 1
fi
if [[ -z "${ENGINE_ID}" ]]; then
  echo "Error: ENGINE_ID environment variable is not set."
  exit 1
fi
if [[ -z "${ASSISTANT_ID}" ]]; then
  echo "Error: ASSISTANT_ID environment variable is not set."
  exit 1
fi
if [[ -z "${SESSION_ID}" ]]; then
  echo "Warning: SESSION_ID environment variable is not set. It is required for 'list_programs'."
  echo "Hint: Run '$0 list_sessions' to find existing IDs or '$0 create_session' to create one."
fi
# Function to get the authorization token
get_auth_token() {
  gcloud auth application-default print-access-token
}
# --- Curl Commands ---
# Create Engine
create_engine() {
  echo "Creating Engine '${ENGINE_ID}'..."
  curl -X POST "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines?engineId=${ENGINE_ID}" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)" \
    -d "{\"display_name\": \"${ENGINE_ID}\", \"data_store_ids\": [], \"solution_type\": \"SOLUTION_TYPE_GENERATIVE_CHAT\"}"
  echo ""
}
# Delete Engine
delete_engine() {
  echo "Deleting Engine '${ENGINE_ID}'..."
  curl -X DELETE "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines/${ENGINE_ID}" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)"
  echo ""
}
# List Engines
list_engines() {
  echo "Listing Engines for Project '${PROJECT_ID}'..."
  curl -X GET "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)"
  echo ""
}
# Create Assistant
create_assistant() {
  echo "Creating Assistant '${ASSISTANT_ID}' for Engine '${ENGINE_ID}'..."
  curl -X POST "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines/${ENGINE_ID}/assistants?assistantId=${ASSISTANT_ID}" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)" \
    -d "{\"display_name\": \"${ASSISTANT_ID}\", \"description\": null, \"generation_config\": null, \"web_grounding_type\": \"WEB_GROUNDING_TYPE_UNSPECIFIED\", \"enabled_actions\": null, \"customer_policy\": null}"
  echo ""
}
# Delete Assistant
delete_assistant() {
  echo "Deleting Assistant '${ASSISTANT_ID}' from Engine '${ENGINE_ID}'..."
  curl -X DELETE "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines/${ENGINE_ID}/assistants/${ASSISTANT_ID}" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)"
  echo ""
}
# List Assistants
list_assistants() {
  echo "Listing Assistants for Engine '${ENGINE_ID}'..."
  curl -X GET "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines/${ENGINE_ID}/assistants" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)"
  echo ""
}
# List Alpha Evolve Programs
list_alpha_evolve_programs() {
  if [[ -z "${SESSION_ID}" ]]; then
    echo "Error: SESSION_ID environment variable is not set."
    exit 1
  fi
  if [[ -z "${EXPERIMENT_ID}" ]]; then
    echo "Error: EXPERIMENT_ID environment variable is not set."
    exit 1
  fi
  echo "Listing Alpha Evolve Programs for Experiment '${EXPERIMENT_ID}' in Session '${SESSION_ID}'..."
  curl -X GET "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/${ENGINE_ID}/sessions/${SESSION_ID}/alphaEvolveExperiments/${EXPERIMENT_ID}/alphaEvolvePrograms" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)"
  echo ""
}
# List Sessions
list_sessions() {
  echo "Listing Sessions for Engine '${ENGINE_ID}'..."
  RESPONSE=$(curl -s -X GET "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines/${ENGINE_ID}/sessions" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)")
  
  echo "${RESPONSE}"
  
  echo "----------------------------------------"
  echo "Extracted Session IDs:"
  echo "${RESPONSE}" | grep -o '"name": "[^"]*sessions/[^"]*"' | sed 's|.*/sessions/||;s/"//'
  echo "----------------------------------------"
}
# List Experiments
list_experiments() {
  if [[ -z "${SESSION_ID}" ]]; then
    echo "Error: SESSION_ID environment variable is not set."
    exit 1
  fi
  echo "Listing Alpha Evolve Experiments for Session '${SESSION_ID}'..."
  curl -X GET "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/${ENGINE_ID}/sessions/${SESSION_ID}/alphaEvolveExperiments" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)"
  echo ""
}
# Create Session
create_session() {
  echo "Creating Session for Engine '${ENGINE_ID}' using 'default_assistant'..."
  RESPONSE=$(curl -s -X POST "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection/engines/${ENGINE_ID}/assistants/default_assistant:streamAssist" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Authorization: Bearer $(get_auth_token)" \
    -d "{\"query\": {\"text\": \"starting alpha evolve query\"}, \"assistSkippingMode\": \"REQUEST_ASSIST\"}")
  
  echo "${RESPONSE}"
  
  SESSION_PATH=$(echo "${RESPONSE}" | grep -o '"session": "[^"]*"' | head -1 | sed 's/"session": "//;s/"//')
  if [[ -n "${SESSION_PATH}" ]]; then
    SESSION_ID=$(echo "${SESSION_PATH}" | sed 's|.*/sessions/||')
    echo "Captured Session ID: ${SESSION_ID}"
    echo "Full Session Path: ${SESSION_PATH}"
  else
    echo "Failed to capture Session ID from response."
  fi
}
# --- Main Logic ---
case "$1" in
  "create_engine")
    create_engine
    ;;
  "delete_engine")
    delete_engine
    ;;
  "list_engines")
    list_engines
    ;;
  "create_assistant")
    create_assistant
    ;;
  "delete_assistant")
    delete_assistant
    ;;
  "list_assistants")
    list_assistants
    ;;
  "list_programs")
    list_alpha_evolve_programs
    ;;
  "list_sessions")
    list_sessions
    ;;
  "create_session")
    create_session
    ;;
  "list_experiments")
    list_experiments
    ;;
  *)
    echo "Usage: $0 {create_engine|delete_engine|list_engines|create_assistant|delete_assistant|list_assistants|list_programs|list_sessions|create_session|list_experiments}"
    echo "Environment variables required: PROJECT_ID, ENGINE_ID, ASSISTANT_ID (and SESSION_ID, EXPERIMENT_ID for list_programs)"
    exit 1
    ;;
esac
