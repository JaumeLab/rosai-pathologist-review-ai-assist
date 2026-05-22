#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="gs://rosai-100/review/rosai-ai-assist-correct-v1/assignments.json"
gsutil cp "${ROOT}/assignments.json" "${DEST}"
echo "Uploaded ${DEST}"
