#!/bin/bash

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Exit immediately if a command exits with a non-zero status
set -e

BUCKET_NAME="$1"
PROJECT_ID="$2"

if ! gcloud storage objects list gs://${BUCKET_NAME}/ --limit=1 --project=${PROJECT_ID} > /dev/null 2>&1; then
  echo "ERROR: GCS Bucket gs://${BUCKET_NAME} does not exist in project ${PROJECT_ID}."
  exit 1
fi

echo "Infrastructure GCS bucket validation passed successfully!"
