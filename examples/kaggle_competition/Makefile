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

EXAMPLE_NAME = kaggle_competition

# Load environment variables from .env
-include .env
export

.DEFAULT_GOAL := help

.PHONY: help setup auth infra data deploy run clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install deps, copy .env template, print next steps
	@if [ ! -f .env ]; then \
		cp example.env .env; \
		echo "Created .env from template. Edit it with your GCP settings."; \
	else \
		echo ".env already exists, skipping copy."; \
	fi
	@echo "Installing AlphaEvolve package..."
	cd ../.. && uv pip install -e ".[dev]"
	@echo ""
	@echo "Done. Next steps:"
	@echo "  1. Edit .env with your PROJECT_ID and GE_APP_ID"
	@echo "  2. Run: make auth"
	@echo "  3. Run: make infra"
	@echo "  4. Download Kaggle data (see README) and run: make data"
	@echo "  5. Run: make deploy"
	@echo "  6. Update EVALUATOR_URL in .env and run: make run"

auth: ## Authenticate with GCP
	gcloud auth application-default login

infra: ## Provision GCP resources (APIs, AR, GCS bucket, IAM, Discovery Engine)
	cd terraform && terraform init -input=false && terraform apply

data: ## Upload local Kaggle CSV files to the GCS bucket created by 'make infra'
	@ARTIFACTS_BUCKET=$$(cd terraform && terraform output -raw artifacts_bucket 2>/dev/null); \
	if [ -z "$${ARTIFACTS_BUCKET}" ]; then \
		echo "ERROR: Could not read artifacts_bucket from Terraform. Run 'make infra' first."; \
		exit 1; \
	fi; \
	if [ ! -f data/properties_2016.csv ] || [ ! -f data/train_2016_v2.csv ]; then \
		echo "ERROR: Zillow data not found in data/. Download it first:"; \
		echo "  pip install kaggle"; \
		echo "  kaggle competitions download -c zillow-prize-1 -p data/"; \
		echo "  unzip data/zillow-prize-1.zip -d data/"; \
		exit 1; \
	fi; \
	echo "Uploading dataset to gs://$${ARTIFACTS_BUCKET}/data/ ..."; \
	gsutil -m cp data/properties_2016.csv data/train_2016_v2.csv \
		"gs://$${ARTIFACTS_BUCKET}/data/"; \
	echo "Dataset uploaded."

deploy: ## Build evaluator image and deploy to Cloud Run (via Cloud Build)
	@ARTIFACTS_BUCKET=$$(cd terraform && terraform output -raw artifacts_bucket 2>/dev/null); \
	AR_REGION=$$(cd terraform && terraform output -raw artifact_registry_url 2>/dev/null | cut -d'-' -f1-2); \
	REPO=$$(cd terraform && terraform output -raw artifact_registry_url 2>/dev/null | rev | cut -d'/' -f1 | rev); \
	echo "Submitting Cloud Build..."; \
	gcloud builds submit \
		--config=cloudbuild.yaml \
		--substitutions="_AR_REGION=$${AR_REGION:-us-central1},_DEPLOY_REGION=$${AR_REGION:-us-central1},_REPO=$${REPO:-alphaevolve},_ARTIFACTS_BUCKET=$${ARTIFACTS_BUCKET}"

run: ## Start the AlphaEvolve experiment
	cd ../.. && python -m examples.$(EXAMPLE_NAME).src.run_evolution

clean: ## Tear down all GCP infrastructure
	cd terraform && terraform destroy
