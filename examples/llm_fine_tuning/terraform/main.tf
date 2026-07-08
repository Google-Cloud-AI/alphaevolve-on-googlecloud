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

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.12.0"
    }
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = ">= 1.14.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.25.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {}
data "google_client_config" "default" {}

provider "helm" {
  kubernetes = {
    host                   = "https://${google_container_cluster.alphaevolve.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(google_container_cluster.alphaevolve.master_auth[0].cluster_ca_certificate)
  }
}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.alphaevolve.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.alphaevolve.master_auth[0].cluster_ca_certificate)
}

provider "kubectl" {
  host                   = "https://${google_container_cluster.alphaevolve.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.alphaevolve.master_auth[0].cluster_ca_certificate)
  load_config_file       = false
}

locals {
  training_image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}/alphaevolve-llm-training:latest"
  compute_sa     = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# --- Enable required APIs ---

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "discoveryengine" {
  service            = "discoveryengine.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "container" {
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

# --- Artifact Registry ---

resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "Docker repository for AlphaEvolve evaluator images"

  depends_on = [google_project_service.artifactregistry]
}

# --- GCS bucket for model and dataset artifacts ---

resource "google_storage_bucket" "artifacts" {
  name          = "${var.project_id}-ae-llm-artifacts"
  location      = var.region
  force_destroy = true
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  depends_on = [google_project_service.storage]
}

# --- IAM: Grant Cloud Build SA permissions ---

resource "google_project_iam_member" "cloudbuild_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"

  depends_on = [google_project_service.cloudbuild]
}

resource "google_project_iam_member" "cloudbuild_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"

  depends_on = [google_project_service.cloudbuild]
}

# --- IAM: Grant Cloud Build SA read/write access to artifacts bucket ---

resource "google_storage_bucket_iam_member" "cloudbuild_bucket_writer" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

# --- IAM: Grant Compute Engine default SA permissions for Cloud Build ---
# Cloud Build uses the Compute Engine default SA by default in newer projects.

resource "google_project_iam_member" "compute_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${local.compute_sa}"
}

resource "google_project_iam_member" "compute_sa_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${local.compute_sa}"
}

resource "google_project_iam_member" "compute_sa_container_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${local.compute_sa}"
}

resource "google_storage_bucket_iam_member" "compute_sa_bucket_writer" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.compute_sa}"
}

# --- IAM: Grant Discovery Engine Admin to experiment runner SA ---

resource "google_project_iam_member" "discoveryengine_admin" {
  project = var.project_id
  role    = "roles/discoveryengine.admin"
  member  = "serviceAccount:${var.service_account_email}"

  depends_on = [google_project_service.discoveryengine]
}

# --- Discovery Engine: Engine and Assistant for AlphaEvolve ---
# The terraform google provider does not support SOLUTION_TYPE_GENERATIVE_CHAT
# engines natively, so we use the REST API via local-exec provisioners.

locals {
  de_engines_url = "https://discoveryengine.googleapis.com/v1alpha/projects/${var.project_id}/locations/global/collections/default_collection/engines"
}

resource "terraform_data" "discovery_engine" {
  # Store the full engine URL so the destroy provisioner can reference via self.input
  input = "${local.de_engines_url}/${var.engine_id}"

  provisioner "local-exec" {
    command = <<-EOT
      curl -sf -X POST \
        "${local.de_engines_url}?engineId=${var.engine_id}" \
        -H "Content-Type: application/json" \
        -H "x-goog-user-project: ${var.project_id}" \
        -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
        -d '{"display_name": "${var.engine_id}", "data_store_ids": [], "solution_type": "SOLUTION_TYPE_GENERATIVE_CHAT"}'
      echo "Waiting for engine creation to complete..."
      sleep 30
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      curl -sf -X DELETE "${self.input}" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
      || true
    EOT
  }

  depends_on = [google_project_service.discoveryengine]
}

resource "terraform_data" "discovery_engine_assistant" {
  input = var.engine_id

  provisioner "local-exec" {
    command = <<-EOT
      curl -sf -X POST \
        "https://discoveryengine.googleapis.com/v1alpha/projects/${var.project_id}/locations/global/collections/default_collection/engines/${var.engine_id}/assistants?assistantId=${var.assistant_id}" \
        -H "Content-Type: application/json" \
        -H "x-goog-user-project: ${var.project_id}" \
        -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
        -d '{"display_name": "${var.assistant_id}", "description": null, "generation_config": null, "web_grounding_type": "WEB_GROUNDING_TYPE_UNSPECIFIED", "enabled_actions": null, "customer_policy": null}' \
      || true
    EOT
  }

  depends_on = [terraform_data.discovery_engine]
}
