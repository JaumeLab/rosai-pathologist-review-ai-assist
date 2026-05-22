#!/usr/bin/env bash
# Deploy AI-assist review API to Cloud Run (Firestore + reviewer passcodes).
set -euo pipefail

PROJECT="${GCP_PROJECT:-jaumelab}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${SERVICE_NAME:-rosai-review-api-ai-assist}"
IMAGE="gcr.io/${PROJECT}/${SERVICE}"
ASSIGNMENTS_URL="https://raw.githubusercontent.com/JaumeLab/rosai-pathologist-review-ai-assist/main/assignments.json"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PASSCODES_ENV="${SCRIPT_DIR}/reviewer_passcodes.env"
if [[ ! -f "$PASSCODES_ENV" ]]; then
  echo "No reviewer_passcodes.env — generating passcodes…"
  python3 "${SCRIPT_DIR}/generate_passcodes.py"
fi
# shellcheck disable=SC1090
source "$PASSCODES_ENV"

ENV_VARS="^@^REVIEW_DB_BACKEND=firestore@STUDY_ID=rosai-ai-assist-correct-v1@ASSIGNMENTS_URL=${ASSIGNMENTS_URL}@CORS_ORIGINS=https://jaumelab.github.io|http://127.0.0.1:8772|http://localhost:8772@REVIEWER_PASSCODES=${REVIEWER_PASSCODES}"

echo "Building ${IMAGE}…"
gcloud builds submit --tag "$IMAGE" --project "$PROJECT"

echo "Deploying Cloud Run service ${SERVICE}…"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "${ENV_VARS}" \
  --min-instances 0 \
  --max-instances 3

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
echo ""
echo "API deployed: ${URL}"
echo "Reviewer passcodes: ${SCRIPT_DIR}/reviewer_passcodes.txt"
echo "Update config.json api_base_url to this URL, then push the frontend."
