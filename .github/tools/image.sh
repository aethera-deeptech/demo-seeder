#!/usr/bin/env bash
# Prints the image of a stage in .github/tools/Dockerfile, so the workflows run the version that the update bot keeps current.
set -euo pipefail

stage="$1"

image="$(awk -v stage="$stage" 'toupper($1) == "FROM" && toupper($3) == "AS" && $4 == stage { print $2 }' "$(dirname "$0")/Dockerfile")"

if [ -z "$image" ]; then
  echo "no stage named ${stage} in .github/tools/Dockerfile" >&2
  exit 1
fi

echo "$image"
