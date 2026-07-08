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

EXAMPLE_NAME = llm_fine_tuning

# Load environment variables from .env
-include .env
export

.DEFAULT_GOAL := help

.PHONY: help setup auth infra deploy deploy-gateway ray-dashboard monitoring-portforward run clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and copy env template
	@if [ ! -f .env ]; then \
		cp example.env .env; \
		echo "Created .env from template. Edit it with your GCP settings."; \
	else \
		echo ".env already exists, skipping copy."; \
	fi
	@echo "Installing AlphaEvolve package..."
	cd ../.. && uv pip install -e ".[dev]"
	@echo "Installing kubectl and GKE auth plugin..."
	gcloud components install kubectl gke-gcloud-auth-plugin --quiet
	@echo ""
	@echo "Done. Next steps:"
	@echo "  1. Edit .env with your PROJECT_ID, GE_APP_ID, and EVALUATOR_URL"
	@echo "  2. Run: make auth"
	@echo "  3. Run: make infra"
	@echo "  4. Run: make deploy"
	@echo "  5. Run: make ray-dashboard  (cluster monitoring)"
	@echo "  6. Run: make run"

auth: ## Authenticate with GCP
	gcloud auth application-default login

infra: ## Provision GCP resources with Terraform (GKE, RayCluster, monitoring)
	cd terraform && ~/bin/terraform init -input=false && ~/bin/terraform apply

deploy: ## Build images and deploy gateway to GKE via Cloud Build
	@ARTIFACTS_BUCKET=$$(cd terraform && ~/bin/terraform output -raw artifacts_bucket 2>/dev/null); \
	GKE_CLUSTER=$$(cd terraform && ~/bin/terraform output -raw gke_cluster_name 2>/dev/null); \
	echo "Submitting Cloud Build..."; \
	gcloud builds submit \
		--config=cloudbuild.yaml \
		--substitutions="_AR_REGION=$${REGION:-us-central1},_GKE_REGION=$${REGION:-us-central1},_REPO=alphaevolve,_ARTIFACTS_BUCKET=$${ARTIFACTS_BUCKET},_HF_TOKEN=$${HF_TOKEN},_GKE_CLUSTER=$${GKE_CLUSTER}"

deploy-gateway: ## Apply gateway manifest and set env vars from Terraform outputs
	@ARTIFACTS_BUCKET=$$(cd terraform && ~/bin/terraform output -raw artifacts_bucket 2>/dev/null); \
	AR_REGION=$${REGION:-us-central1}; \
	REPO=alphaevolve; \
	echo "Applying gateway manifest..."; \
	kubectl apply -f deploy/gateway.yaml; \
	echo "Setting gateway image..."; \
	kubectl set image deployment/gateway \
		gateway=$${AR_REGION}-docker.pkg.dev/$${PROJECT_ID}/$${REPO}/alphaevolve-llm-gateway:latest \
		-n alphaevolve; \
	echo "Setting gateway env vars..."; \
	kubectl set env deployment/gateway -n alphaevolve \
		ARTIFACTS_BUCKET=$${ARTIFACTS_BUCKET} \
		NAMESPACE=alphaevolve \
		ARTIFACTS_PATH=/mnt/artifacts \
		RAY_CLUSTER_NAME=alphaevolve-ray-cluster \
		JOB_TIMEOUT_SECONDS=2400 \
		JOB_POLL_INTERVAL=10; \
	echo "Waiting for rollout..."; \
	kubectl rollout status deployment/gateway -n alphaevolve --timeout=120s; \
	echo ""; \
	echo "=== Gateway Ready ==="; \
	echo "kubectl port-forward svc/gateway -n alphaevolve 8080:80"

ray-dashboard: ## Port-forward Ray Dashboard (http://localhost:8265)
	kubectl port-forward -n alphaevolve svc/alphaevolve-ray-cluster-head-svc 8265:8265

monitoring-portforward: ## Port-forward Grafana (http://localhost:3000)
	kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

run: ## Run the AlphaEvolve experiment
	cd ../.. && python -m examples.$(EXAMPLE_NAME).src.run_evolution

clean: ## Tear down all infrastructure
	cd terraform && ~/bin/terraform destroy
