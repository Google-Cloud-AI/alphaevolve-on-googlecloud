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
  description = "GCS bucket storing the Zillow competition dataset."
  value       = google_storage_bucket.artifacts.name
}

output "cloudbuild_command" {
  description = "Command to build and deploy the evaluator using Cloud Build."
  value       = "cd examples/kaggle_competition && gcloud builds submit --config=cloudbuild.yaml --substitutions=_AR_REGION=${var.region},_DEPLOY_REGION=${var.region},_REPO=${var.repository_id},_ARTIFACTS_BUCKET=${google_storage_bucket.artifacts.name}"
}

output "data_upload_command" {
  description = "Command to upload Zillow dataset to the GCS artifacts bucket."
  value       = "gsutil -m cp examples/kaggle_competition/data/properties_2016.csv examples/kaggle_competition/data/train_2016_v2.csv gs://${google_storage_bucket.artifacts.name}/data/"
}

output "engine_id" {
  description = "Discovery Engine engine ID for AlphaEvolve experiments."
  value       = var.engine_id
}

output "assistant_id" {
  description = "Discovery Engine assistant ID for AlphaEvolve experiments."
  value       = var.assistant_id
}
