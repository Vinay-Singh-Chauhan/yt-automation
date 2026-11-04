#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPOSITORY="${ARTIFACT_REPOSITORY:-yt-pipeline}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/pipeline:$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
BUILD_SERVICE_ACCOUNT="${BUILD_SERVICE_ACCOUNT:-$(gcloud builds get-default-service-account --project "${PROJECT_ID}")}"

gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  workflows.googleapis.com \
  --project "${PROJECT_ID}"

terraform -chdir=terraform init

if ! gcloud artifacts repositories describe "${REPOSITORY}" \
  --project "${PROJECT_ID}" --location "${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPOSITORY}" \
    --project "${PROJECT_ID}" --location "${REGION}" \
    --repository-format=docker
fi

if ! terraform -chdir=terraform state list | grep -Fxq \
  "google_artifact_registry_repository.images"; then
  terraform -chdir=terraform import \
    -var="project_id=${PROJECT_ID}" \
    -var="region=${REGION}" \
    -var="artifact_repository=${REPOSITORY}" \
    -var="bucket_name=${PROJECT_ID}-yt-assets" \
    -var="app_image=us-docker.pkg.dev/cloudrun/container/hello" \
    google_artifact_registry_repository.images \
    "projects/${PROJECT_ID}/locations/${REGION}/repositories/${REPOSITORY}"
fi

gcloud beta services identity create \
  --service=workflows.googleapis.com \
  --project="${PROJECT_ID}" >/dev/null

gcloud builds submit \
  --project "${PROJECT_ID}" \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SERVICE_ACCOUNT}" \
  --config=cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE}" \
  .
terraform -chdir=terraform apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="artifact_repository=${REPOSITORY}" \
  -var="bucket_name=${PROJECT_ID}-yt-assets" \
  -var="app_image=${IMAGE}"
