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

EXAMPLE_NAME = tsp

# Load environment variables from .env
-include .env
export

.DEFAULT_GOAL := help

.PHONY: help setup auth run clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and copy env template
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
	@echo "  3. Run: make run"

auth: ## Authenticate with GCP
	gcloud auth application-default login

run: ## Run the AlphaEvolve experiment
	cd ../.. && python -m examples.$(EXAMPLE_NAME).src.run_evolution

clean: ## Remove generated reports and evolved programs
	rm -rf report/*.png
	rm -rf evolved_program/main.py
