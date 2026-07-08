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

# --- Monitoring stack: Prometheus + Grafana ---
#
# Deploys kube-prometheus-stack via Helm, PodMonitors for Ray head/workers,
# and a ServiceMonitor for the gateway.
#
# Only created when var.enable_monitoring = true.

# --- Prometheus + Grafana ---

resource "kubernetes_namespace_v1" "monitoring" {
  count = var.enable_monitoring ? 1 : 0

  metadata {
    name = "monitoring"
  }

  depends_on = [google_container_node_pool.default]
}

resource "helm_release" "prometheus" {
  count = var.enable_monitoring ? 1 : 0

  name       = "kube-prometheus-stack"
  namespace  = kubernetes_namespace_v1.monitoring[0].metadata[0].name
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"

  values = [templatefile("${path.module}/prometheus-values.yaml", {
    grafana_password = var.grafana_password
  })]

  timeout = 600

  depends_on = [kubernetes_namespace_v1.monitoring]
}

# --- Ray PodMonitors for Prometheus ---

resource "kubectl_manifest" "ray_head_podmonitor" {
  count     = var.enable_monitoring ? 1 : 0
  yaml_body = file("${path.module}/../deploy/ray-head-podmonitor.yaml")

  depends_on = [helm_release.prometheus]
}

resource "kubectl_manifest" "ray_workers_podmonitor" {
  count     = var.enable_monitoring ? 1 : 0
  yaml_body = file("${path.module}/../deploy/ray-workers-podmonitor.yaml")

  depends_on = [helm_release.prometheus]
}

# --- Gateway ServiceMonitor ---

resource "kubectl_manifest" "gateway_service_monitor" {
  count = var.enable_monitoring ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: monitoring.coreos.com/v1
    kind: ServiceMonitor
    metadata:
      name: alphaevolve-gateway
      namespace: alphaevolve
      labels:
        app: alphaevolve-gateway
        release: kube-prometheus-stack
    spec:
      selector:
        matchLabels:
          app: alphaevolve-gateway
      endpoints:
        - port: http
          path: /metrics
          interval: 15s
  YAML

  depends_on = [
    helm_release.prometheus,
    kubernetes_namespace_v1.alphaevolve,
  ]
}

