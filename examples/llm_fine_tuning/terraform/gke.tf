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

# --- GKE infrastructure for parallel LLM fine-tuning evaluation ---
#
# Creates a GKE Standard cluster with:
# - Ray Operator addon (KubeRay — manages RayCluster CRD)
# - Default CPU node pool (for the gateway and Ray head)
# - GPU node pool with NVIDIA L4 (for Ray workers, autoscaling 0-N)
# - GCS FUSE CSI driver (mount model/dataset bucket into pods)
# - Workload Identity (pods authenticate as GCP service accounts)
# - Persistent RayCluster (head + GPU workers)
# - Namespace, ServiceAccounts, RBAC for gateway and training

# --- GKE Cluster ---

resource "google_container_cluster" "alphaevolve" {
  name     = var.gke_cluster_name
  location = var.region
  project  = var.project_id

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  addons_config {
    gcs_fuse_csi_driver_config {
      enabled = true
    }
    ray_operator_config {
      enabled = true
      ray_cluster_logging_config {
        enabled = true
      }
      ray_cluster_monitoring_config {
        enabled = true
      }
    }
  }

  release_channel {
    channel = "REGULAR"
  }

  depends_on = [google_project_service.container]
}

# --- CPU Node Pool (gateway + Ray head) ---

resource "google_container_node_pool" "default" {
  name       = "default-pool"
  cluster    = google_container_cluster.alphaevolve.name
  location   = var.region
  project    = var.project_id
  node_count = 1

  node_config {
    machine_type = "e2-standard-4"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# --- GPU Node Pool (Ray workers) ---

resource "google_container_node_pool" "gpu" {
  name     = "gpu-pool"
  cluster  = google_container_cluster.alphaevolve.name
  location = var.region
  project  = var.project_id

  # Restrict to zones that have A100 GPUs
  node_locations = ["us-central1-a", "us-central1-c"]

  autoscaling {
    min_node_count = var.min_gpu_nodes
    max_node_count = var.max_gpu_nodes
  }

  node_config {
    machine_type = "a2-highgpu-1g" # 12 vCPUs, 85 GB RAM, 1x NVIDIA A100 40GB

    guest_accelerator {
      type  = "nvidia-tesla-a100"
      count = 1

      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = {
      accelerator-type = "nvidia-a100"
    }

    taint {
      key    = "nvidia.com/gpu"
      value  = "present"
      effect = "NO_SCHEDULE"
    }
  }
}

# --- Namespace and ServiceAccounts ---

resource "kubernetes_namespace_v1" "alphaevolve" {
  metadata {
    name = "alphaevolve"
  }

  depends_on = [google_container_node_pool.default]
}

resource "kubernetes_service_account_v1" "training" {
  metadata {
    name      = "alphaevolve-training"
    namespace = kubernetes_namespace_v1.alphaevolve.metadata[0].name
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.gke_training.email
    }
  }

  depends_on = [google_service_account.gke_training]
}

resource "kubernetes_service_account_v1" "gateway" {
  metadata {
    name      = "alphaevolve-gateway"
    namespace = kubernetes_namespace_v1.alphaevolve.metadata[0].name
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.gke_gateway.email
    }
  }

  depends_on = [google_service_account.gke_gateway]
}

# --- RBAC: Allow gateway to manage RayJobs and read pods ---

resource "kubernetes_role_v1" "job_manager" {
  metadata {
    name      = "job-manager"
    namespace = kubernetes_namespace_v1.alphaevolve.metadata[0].name
  }

  rule {
    api_groups = ["ray.io"]
    resources  = ["rayjobs", "rayjobs/status"]
    verbs      = ["create", "get", "list", "watch", "delete"]
  }

  rule {
    api_groups = ["batch"]
    resources  = ["jobs", "jobs/status"]
    verbs      = ["create", "get", "list", "watch", "delete"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods", "pods/log"]
    verbs      = ["get", "list"]
  }
}

resource "kubernetes_role_binding_v1" "gateway_job_manager" {
  metadata {
    name      = "gateway-job-manager"
    namespace = kubernetes_namespace_v1.alphaevolve.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.gateway.metadata[0].name
    namespace = kubernetes_namespace_v1.alphaevolve.metadata[0].name
  }

  role_ref {
    kind      = "Role"
    name      = kubernetes_role_v1.job_manager.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

# --- Workload Identity: bind K8s SAs to GCP SAs ---

resource "google_service_account" "gke_training" {
  account_id   = "alphaevolve-gke-training"
  display_name = "AlphaEvolve GKE Training"
  project      = var.project_id
}

resource "google_storage_bucket_iam_member" "gke_training_bucket" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.gke_training.email}"
}

resource "google_service_account_iam_member" "training_workload_identity" {
  service_account_id = google_service_account.gke_training.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[alphaevolve/alphaevolve-training]"
}

resource "google_project_iam_member" "gke_training_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_training.email}"
}

resource "google_service_account" "gke_gateway" {
  account_id   = "alphaevolve-gke-gateway"
  display_name = "AlphaEvolve GKE Gateway"
  project      = var.project_id
}

resource "google_storage_bucket_iam_member" "gke_gateway_bucket" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.gke_gateway.email}"
}

resource "google_service_account_iam_member" "gateway_workload_identity" {
  service_account_id = google_service_account.gke_gateway.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[alphaevolve/alphaevolve-gateway]"
}

# --- Persistent RayCluster ---

resource "kubectl_manifest" "ray_cluster" {
  yaml_body = replace(
    replace(
      file("${path.module}/../deploy/ray-cluster.yaml"),
      "TRAINING_IMAGE_PLACEHOLDER",
      local.training_image
    ),
    "ARTIFACTS_BUCKET_PLACEHOLDER",
    google_storage_bucket.artifacts.name
  )

  depends_on = [
    google_container_node_pool.default,
    google_container_node_pool.gpu,
    kubernetes_service_account_v1.training,
  ]
}
