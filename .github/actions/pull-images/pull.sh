#!/usr/bin/env bash
# Pulls an image through the Google mirror and falls back to Docker Hub when the mirror does not have it.
# Prints the reference that was pulled, so the caller can run it.
set -euo pipefail

image="$1"

if docker pull --quiet "mirror.gcr.io/${image}" >/dev/null; then
  echo "mirror.gcr.io/${image}"
else
  docker pull --quiet "${image}" >/dev/null
  echo "${image}"
fi
