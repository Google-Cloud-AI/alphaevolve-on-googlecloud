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

output "artifact_registry_url" {
  description = "Docker image registry URL for the evaluator."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}"
}

output "artifacts_bucket" {
  description = "GCS bucket storing the pre-downloaded model and dataset."
  value       = google_storage_bucket.artifacts.name
}

output "engine_id" {
  description = "Discovery Engine engine ID for AlphaEvolve experiments."
  value       = var.engine_id
}

output "assistant_id" {
  description = "Discovery Engine assistant ID for AlphaEvolve experiments."
  value       = var.assistant_id
}

output "gke_cluster_name" {
  description = "GKE cluster name. Use: gcloud container clusters get-credentials <name> --region <region>"
  value       = google_container_cluster.alphaevolve.name
}

output "gke_training_sa" {
  description = "GCP service account for GKE training pods (Workload Identity)."
  value       = google_service_account.gke_training.email
}

output "gke_gateway_sa" {
  description = "GCP service account for GKE gateway pods (Workload Identity)."
  value       = google_service_account.gke_gateway.email
}

output "cloudbuild_command" {
  description = "Command to build images and deploy gateway using Cloud Build."
  value       = "cd examples/llm_fine_tuning && gcloud builds submit --config=cloudbuild.yaml --substitutions=_AR_REGION=${var.region},_REPO=${var.repository_id},_ARTIFACTS_BUCKET=${google_storage_bucket.artifacts.name},_HF_TOKEN=<YOUR_HF_TOKEN>,_GKE_CLUSTER=${google_container_cluster.alphaevolve.name},_GKE_REGION=${var.region}"
}

# --- Monitoring outputs (only when enable_monitoring = true) ---

output "grafana_port_forward" {
  description = "Command to access Grafana via port-forward."
  value       = var.enable_monitoring ? "kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80" : null
}

output "grafana_url" {
  description = "Grafana URL (after port-forward). Login: admin / <grafana_password>."
  value       = var.enable_monitoring ? "http://localhost:3000 (admin / <grafana_password>)" : null
}

