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
  description = "GCP region for Artifact Registry and GKE."
  type        = string
  default     = "us-central1"
}

variable "service_account_email" {
  description = "Email of the service account used to run AlphaEvolve experiments."
  type        = string
}

variable "hf_token" {
  description = "HuggingFace access token for downloading Gemma 4 model (if gated)."
  type        = string
  sensitive   = true
  default     = ""
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

# --- GKE variables ---

variable "gke_cluster_name" {
  description = "Name of the GKE cluster."
  type        = string
  default     = "alphaevolve-llm-cluster"
}

variable "min_gpu_nodes" {
  description = "Minimum number of GPU nodes to keep warm. Set to 1+ to avoid cold-start provisioning delay (~3-5 min). Costs ~$3.67/hr per idle A100 node."
  type        = number
  default     = 0
}

variable "max_gpu_nodes" {
  description = "Maximum number of GPU nodes in the autoscaling pool. Each node has 1x NVIDIA A100 40GB."
  type        = number
  default     = 4
}

# --- Monitoring variables ---

variable "enable_monitoring" {
  description = "Set to true to deploy Prometheus + Grafana for real-time evolution monitoring."
  type        = bool
  default     = false
}

variable "grafana_password" {
  description = "Admin password for the Grafana dashboard."
  type        = string
  sensitive   = true
  default     = "alphaevolve"
}
