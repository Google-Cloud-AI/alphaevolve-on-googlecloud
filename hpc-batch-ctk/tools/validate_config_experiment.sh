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

USER_EXPERIMENT_NAME="$1"
CLOUD_BUILD_DIR="$2"
EXAMPLE_DIR="$3"
EVALUATION_MODE="$4"
EVALUATION_PROVISIONING_MODEL="$5"
EVALUATION_MACHINE_TYPE="$6"
ZONE="$7"
ACCELERATOR_COUNT="$8"
ACCELERATOR_TYPE="$9"
MAX_DURATION="${10}"
IDLE_TIMEOUT="${11}"
MODEL="${12}"

# Validation 1: user_experiment_name cannot contain underscores
case "${USER_EXPERIMENT_NAME}" in
  *_* )
    echo "ERROR: user_experiment_name '${USER_EXPERIMENT_NAME}' contains underscores. Only lowercase letters, numbers, and hyphens are allowed."
    exit 1
    ;;
esac

# Validation 1b: user_experiment_name length cannot exceed 25 characters
if [ ${#USER_EXPERIMENT_NAME} -gt 25 ]; then
  echo "ERROR: user_experiment_name '${USER_EXPERIMENT_NAME}' is too long (${#USER_EXPERIMENT_NAME} chars). The maximum allowed length is 25 characters to prevent Cloud Batch job name truncation."
  exit 1
fi

# Validation 2: Example directory must exist
if [ ! -d "${CLOUD_BUILD_DIR}/${EXAMPLE_DIR}" ]; then
  echo "ERROR: Example directory '${EXAMPLE_DIR}' does not exist."
  exit 1
fi

# Validation 3: evaluation_mode must be batch and evaluator.Dockerfile must exist
if [ "${EVALUATION_MODE}" != "batch" ]; then
  echo "ERROR: Invalid evaluation_mode '${EVALUATION_MODE}'. Only 'batch' mode is supported."
  exit 1
fi
if [ ! -f "${CLOUD_BUILD_DIR}/${EXAMPLE_DIR}/evaluator.Dockerfile" ]; then
  echo "ERROR: No evaluator.Dockerfile found in ${EXAMPLE_DIR}"
  exit 1
fi

# Validation 4: evaluation_provisioning_model must be valid
if [ "${EVALUATION_PROVISIONING_MODEL}" != "STANDARD" ] && \
   [ "${EVALUATION_PROVISIONING_MODEL}" != "SPOT" ] && \
   [ "${EVALUATION_PROVISIONING_MODEL}" != "FLEX_START" ]; then
  echo "ERROR: Invalid evaluation_provisioning_model '${EVALUATION_PROVISIONING_MODEL}'. Valid values are 'STANDARD', 'SPOT', 'FLEX_START'."
  exit 1
fi

# Validation 5: DWS FLEX_START specific rules
if [ "${EVALUATION_PROVISIONING_MODEL}" = "FLEX_START" ]; then
  case "${EVALUATION_MACHINE_TYPE}" in
    g2-* | g4-* | a2-* | a3-* | a4-* | a4x-* | n1-* | h4d-* )
      # Supported GPU DWS Flex machine types
      ;;
    * )
      echo "ERROR: DWS FLEX_START is not supported for machine family '${EVALUATION_MACHINE_TYPE}'. FLEX_START on Cloud Batch requires GPU accelerator-enabled VM or H4D instances (supported: G2, G4, A2, A3, A4, A4x, N1, H4D)."
      exit 1
      ;;
  esac

  if [ -z "${ZONE}" ]; then
    echo "ERROR: DWS FLEX_START requires a single, specific zone parameter for compact placement. Multi-zone region deployment is not allowed."
    exit 1
  fi
fi

# Validation 6: N1 specific accelerator rules
if [[ "${EVALUATION_MACHINE_TYPE}" == n1-* ]]; then
  if [ -z "${ACCELERATOR_COUNT}" ]; then
    echo "ERROR: N1 machine types require accelerator_count to be specified."
    exit 1
  fi
  # Verify that accelerator_count is a positive integer
  if ! [[ "${ACCELERATOR_COUNT}" =~ ^[0-9]+$ ]] || [ "${ACCELERATOR_COUNT}" -le 0 ]; then
    echo "ERROR: Invalid accelerator_count '${ACCELERATOR_COUNT}'. Must be a positive integer."
    exit 1
  fi
  if [ -z "${ACCELERATOR_TYPE}" ]; then
    echo "ERROR: N1 machine types require accelerator_type to be specified."
    exit 1
  fi
  # Verify valid accelerator types for N1
  case "${ACCELERATOR_TYPE}" in
    nvidia-tesla-t4 | nvidia-tesla-p4 | nvidia-tesla-v100 | nvidia-tesla-p100 )
      ;;
    * )
      echo "ERROR: Invalid accelerator_type '${ACCELERATOR_TYPE}' for N1 machine type. Supported types are: nvidia-tesla-t4, nvidia-tesla-p4, nvidia-tesla-v100, nvidia-tesla-p100."
      exit 1
      ;;
  esac
fi

# Validation 7: max_duration must be positive integer between 1 and 24
if [ -n "${MAX_DURATION}" ]; then
  if ! [[ "${MAX_DURATION}" =~ ^[0-9]+$ ]] || [ "${MAX_DURATION}" -lt 1 ] || [ "${MAX_DURATION}" -gt 24 ]; then
    echo "ERROR: Invalid max_duration '${MAX_DURATION}'. Must be an integer hour between 1 and 24 inclusive."
    exit 1
  fi
fi

# Validation 8: idle_timeout must be positive integer at least 1
if [ -n "${IDLE_TIMEOUT}" ]; then
  if ! [[ "${IDLE_TIMEOUT}" =~ ^[0-9]+$ ]] || [ "${IDLE_TIMEOUT}" -lt 1 ]; then
    echo "ERROR: Invalid idle_timeout '${IDLE_TIMEOUT}'. Must be an integer hour greater than or equal to 1."
    exit 1
  fi
fi

# Validation 9: idle_timeout must be strictly less than max_duration
if [ -n "${IDLE_TIMEOUT}" ]; then
  EFFECTIVE_MAX="${MAX_DURATION:-6}"
  if [ "${IDLE_TIMEOUT}" -ge "${EFFECTIVE_MAX}" ]; then
    echo "ERROR: idle_timeout (${IDLE_TIMEOUT}) must be strictly less than max_duration (${EFFECTIVE_MAX})."
    exit 1
  fi
fi

# Validation 10: Validate model parameter (mixture count and allowed names)
if [ -n "${MODEL}" ]; then
  IFS=',;+/' read -ra MODELS <<< "${MODEL}"
  if [ "${#MODELS[@]}" -gt 2 ]; then
    echo "ERROR: At most two models can be specified in the mixture (found ${#MODELS[@]})."
    exit 1
  fi
  for item in "${MODELS[@]}"; do
    if [[ "${item}" == *:* ]]; then
      weight="${item#*:}"
      weight="${weight#"${weight%%[![:space:]]*}"}" # trim leading whitespace
      weight="${weight%"${weight##*[![:space:]]}"}" # trim trailing whitespace
      if ! [[ "${weight}" =~ ^(0(\.[0-9]+)?|1(\.0+)?|\.[0-9]+)$ ]]; then
        echo "ERROR: Model weight '${weight}' must be a number between 0 and 1."
        exit 1
      fi
    fi
    name="${item%%:*}"
    name="${name#"${name%%[![:space:]]*}"}" # trim leading whitespace
    name="${name%"${name##*[![:space:]]}"}" # trim trailing whitespace
    case "${name}" in
      GEMINI_V2P5_FLASH | GEMINI_V2P5_PRO | GEMINI_V3P0_FLASH_PREVIEW | GEMINI_V3P1_PRO_PREVIEW | GEMINI_V3P5_FLASH)
        ;;
      * )
        echo "ERROR: Unsupported model '${name}' in model parameter. Supported models: GEMINI_V2P5_FLASH, GEMINI_V2P5_PRO, GEMINI_V3P0_FLASH_PREVIEW, GEMINI_V3P1_PRO_PREVIEW, GEMINI_V3P5_FLASH".
        exit 1
        ;;
    esac
  done
fi

echo "All experiment configurations are valid!"
