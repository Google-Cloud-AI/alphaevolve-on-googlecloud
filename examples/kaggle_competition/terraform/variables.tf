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

variable "project_id" {
  description = "GCP project ID where resources will be created."
  type        = string
}

variable "region" {
  description = "GCP region for Artifact Registry and Cloud Run."
  type        = string
  default     = "us-central1"
}

variable "service_account_email" {
  description = "Email of the service account used to run AlphaEvolve experiments. Will be granted Cloud Run invoker permissions."
  type        = string
}

variable "run_invoker_members" {
  description = "Additional IAM members to grant Cloud Run invoker role. E.g., user:foo@example.com or serviceAccount:sa@project.iam.gserviceaccount.com."
  type        = list(string)
  default     = []
}

variable "repository_id" {
  description = "Artifact Registry repository ID for Docker images."
  type        = string
  default     = "alphaevolve"
}

variable "engine_id" {
  description = "Discovery Engine engine ID for AlphaEvolve experiments."
  type        = string
  default     = "alpha-evolve-experiment-engine"
}

variable "assistant_id" {
  description = "Discovery Engine assistant ID for AlphaEvolve experiments."
  type        = string
  default     = "default_assistant"
}
