#!/bin/bash

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


# Check for the correct number of arguments
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <filename> <release_tag>"
    exit 1
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "Error: git is not installed. Please install git to use this script."
    exit 1
fi

FILENAME=$1
RELEASE_TAG=$2
RELEASE_DIR="releases"

# Handle the case where FILENAME is 'all'
if [ "$FILENAME" == "all" ]; then
    ARCHIVE_FILENAME="alphaevolve-on-cloud"
    FILENAME="."
else
    ARCHIVE_FILENAME="$FILENAME"
fi

ARCHIVE_NAME="${ARCHIVE_FILENAME}-${RELEASE_TAG}.tar.gz"
TAR_NAME="${ARCHIVE_FILENAME}-${RELEASE_TAG}.tar"

# Get the commit ID of the release tag
TAG_COMMIT_ID=$(git rev-parse "$RELEASE_TAG")
echo "Release Tag ($RELEASE_TAG) Commit ID: $TAG_COMMIT_ID"

# Create the releases directory if it doesn't exist
mkdir -p "$RELEASE_DIR"

# Create the archive using git archive (tar format)
if [ "$FILENAME" == "." ]; then
    echo "Running: git archive --format=tar -o \"${RELEASE_DIR}/${TAR_NAME}\" $RELEASE_TAG"
    git archive --format=tar -o "${RELEASE_DIR}/${TAR_NAME}" $RELEASE_TAG
else
    echo "Running: git archive --format=tar -o \"${RELEASE_DIR}/${TAR_NAME}\" $RELEASE_TAG -- \"$FILENAME\""
    git archive --format=tar -o "${RELEASE_DIR}/${TAR_NAME}" $RELEASE_TAG -- "$FILENAME"
fi

# Extract and display the commit ID from the tar header
COMMIT_ID=$(git get-tar-commit-id < "${RELEASE_DIR}/${TAR_NAME}")
echo "Archive Commit ID: $COMMIT_ID"

# Gzip the tar file to create the final .tar.gz
gzip -f "${RELEASE_DIR}/${TAR_NAME}"

echo "Release created: ${RELEASE_DIR}/${ARCHIVE_NAME}"
echo "To view the archive contents, run:"
echo "tar -tvf ${RELEASE_DIR}/${ARCHIVE_NAME}"
