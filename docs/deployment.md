# Deployment guide

## Prerequisites

- A Google Cloud project with billing enabled and permission to enable APIs,
  create IAM roles/service accounts, Cloud Run services/jobs, workflows,
  Firestore, Pub/Sub, Scheduler, Storage, Artifact Registry, and secrets.
- `gcloud`, Terraform 1.5+, Docker or Cloud Build access, and Python 3.11 for
  local development.
- Deployment identity permissions for Cloud Build and Terraform; see
  [IAM setup](#deployment-iam-permissions).
- A YouTube channel and a configured OAuth client. Follow
  [YouTube OAuth setup](youtube-oauth.md) before running the pipeline.

## First deployment

1. Authenticate and select the target project:

   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   gcloud auth application-default login
   ```

2. Enable billing for the project and create/choose a unique Storage bucket
   name. The deploy script uses `YOUR_PROJECT_ID-yt-assets` by default; change
   `scripts/deploy.sh` if that global bucket name is already taken.

3. Build the image and apply infrastructure:

   ```bash
   chmod +x scripts/deploy.sh
   PROJECT_ID=YOUR_PROJECT_ID REGION=us-central1 scripts/deploy.sh
   ```

   The script explicitly uses the service account returned by
   `gcloud builds get-default-service-account`. To select a different build
   identity, set `BUILD_SERVICE_ACCOUNT` to its email address:

   ```bash
   PROJECT_ID=YOUR_PROJECT_ID \
   BUILD_SERVICE_ACCOUNT=PROJECT_NUMBER-compute@developer.gserviceaccount.com \
   scripts/deploy.sh
   ```

   The script enables the APIs needed for bootstrap, initializes Terraform,
   creates the image repository if needed, imports that repository into
   Terraform state if it is not already tracked, provisions the Workflows
   service identity, builds the app, and applies the infrastructure. Terraform
   enables the remaining runtime APIs and creates the application resources.
   The deploy script imports a pre-existing Artifact Registry repository because
   the image must be pushed before the Cloud Run resources can be applied. It
   does not overwrite or recreate the repository.

4. If the project already has a Firestore `(default)` database, import it into
   Terraform state before applying, or adapt `terraform/main.tf` to use the
   existing database. Do not delete a database that contains existing data.

5. Add the YouTube OAuth JSON to the secret. Keep the JSON in a local file with
   restrictive permissions and do not commit it:

   ```bash
   gcloud secrets versions add yt-oauth-credentials \
     --project YOUR_PROJECT_ID \
     --data-file=secrets/youtube-oauth.json
   ```

6. Publish one private test request:

   ```bash
   gcloud pubsub topics publish yt-trigger-topic \
     --project YOUR_PROJECT_ID \
     --message='{"topic":"A fun, accurate fact about honeybees","language":"en","duration_seconds":20,"privacy_status":"private","idempotency_key":"pilot-honeybee-001"}'
   ```

7. Check the Cloud Run Job execution, Cloud Run service logs, Firestore
   `pipeline_runs` record, and the private video in YouTube Studio. Confirm the
   `runs/<run-id>/` Storage prefix is removed after success.

## Deployment IAM permissions

The user running `scripts/deploy.sh` needs permission to submit Cloud Build
builds and apply the Terraform resources. Prefer assigning the required roles
to that user or a dedicated deployment identity rather than granting Owner.
The Cloud Build build service account also needs permission to push the image
to Artifact Registry.

If `gcloud builds submit` reports `iam.serviceAccounts.get` denied, the
authenticated user may not have permission to use/inspect the selected Cloud
Build service account. Confirm the active account and selected build account:

```bash
gcloud auth list
gcloud builds get-default-service-account --project YOUR_PROJECT_ID
```

Ask a project IAM administrator to grant the deployer
`roles/cloudbuild.builds.editor` on the project and
`roles/iam.serviceAccountUser` on the specific service account returned above.
For example, the administrator can run:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:YOUR_GOOGLE_ACCOUNT" \
  --role="roles/cloudbuild.builds.editor"

gcloud iam service-accounts add-iam-policy-binding BUILD_SERVICE_ACCOUNT \
  --project=YOUR_PROJECT_ID \
  --member="user:YOUR_GOOGLE_ACCOUNT" \
  --role="roles/iam.serviceAccountUser"
```

Replace `BUILD_SERVICE_ACCOUNT` with the full email from
`gcloud builds get-default-service-account`; do not grant Service Account User
on every service account unless your administrator has determined that is
necessary. If the Docker build succeeds but the push fails, grant the build
service account `roles/artifactregistry.writer` on the `yt-pipeline`
repository only:

```bash
gcloud artifacts repositories add-iam-policy-binding yt-pipeline \
  --location=us-central1 \
  --project=YOUR_PROJECT_ID \
  --member="serviceAccount:BUILD_SERVICE_ACCOUNT" \
  --role="roles/artifactregistry.writer"
```

Terraform apply may require additional resource-specific permissions; resolve
those errors with narrowly scoped grants as they appear.

The Cloud Build identity is separate from the user running the deploy script
and from the Cloud Run runtime service account. The deployer must have
`roles/iam.serviceAccountUser` on the selected build identity. The build
identity needs access to its source staging bucket and permission to push the
image to Artifact Registry. The `cloudbuild.yaml` config selects Cloud Logging
only for build logs, as Cloud Build requires an explicit logging destination
when a service account is selected; build logs are available in Cloud Logging.
The pipeline runtime receives `roles/serviceusage.serviceUsageConsumer` for
calling enabled APIs; do not add the nonexistent `roles/cloudtts.user` role.
The deploy script explicitly creates the Workflows service identity before
Terraform creates the workflow, avoiding a first-deployment race while APIs
are being enabled.

If Cloud Build reports that the selected service account cannot write logs,
ask a project IAM administrator to grant `roles/logging.logWriter` to the
service account shown in the build error:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

Replace the member with the exact full service account email shown in the
error. This is a project-level role because the build writes its logs to Cloud
Logging for the project.

If `gcloud builds submit` reports that the build service account lacks
`storage.objects.get` on a `*_cloudbuild` bucket, grant that exact principal
read access on the staging bucket only. Use the service account email shown in
the error (it may differ from the account returned by
`gcloud builds get-default-service-account`):

```bash
gcloud storage buckets add-iam-policy-binding \
  gs://YOUR_PROJECT_CLOUD_BUILD_BUCKET \
  --member="serviceAccount:BUILD_SERVICE_ACCOUNT_FROM_ERROR" \
  --role="roles/storage.objectViewer"
```

Replace the bucket with the exact bucket name in the error, omitting the
`/objects/...` suffix. This grants object read access for Cloud Build source
archives without granting access to other project buckets. A project
administrator with permission to change that bucket's IAM policy may need to
run the command. Retry `gcloud builds submit` after the binding takes effect.

## Enable recurring generation

The Scheduler job is created **paused** by default. Verify the private test and
configure the topic text, language, schedule, timezone, and expected monthly
volume first. Re-apply with Scheduler enabled:

```bash
terraform -chdir=terraform apply \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="region=us-central1" \
  -var="bucket_name=YOUR_UNIQUE_BUCKET" \
  -var="app_image=YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/yt-pipeline/pipeline:TAG" \
  -var="enable_scheduler=true" \
  -var="scheduler_cron=0 9 * * *" \
  -var="scheduler_timezone=Etc/UTC" \
  -var="scheduler_topic=An original topic for this channel"
```

Set `youtube_privacy_status=public` only after a deliberate decision to publish
without manual review. Prefer leaving uploads private/unlisted while evaluating
quality and channel compliance.

## Local development

### Conda

The Ubuntu "externally managed environment" / `externally-managed-environment`
error means `pip` is targeting the OS-managed Python instead of the Conda
environment. Do not work around it with `--break-system-packages`.

Create and activate a project environment, then use that environment's Python
to invoke pip:

```bash
conda create -n yt-pipeline python=3.11 pip -y
conda activate yt-pipeline
python -c "import sys; print(sys.executable)"
python -m pip install -r requirements.txt
```

The printed executable path should be inside a Conda directory, typically
`.../envs/yt-pipeline/bin/python`. If you cannot activate environments, target
it explicitly instead:

```bash
conda run -n yt-pipeline python -m pip install -r requirements.txt
```

### Python virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.api:app --reload
```

The intake endpoint depends on Google Cloud credentials and a deployed Workflow.
The Cloud Run Job worker is the normal execution path. FFmpeg and FFprobe are
required to render; the Dockerfile installs them.

## Deployment notes

- Content generation uses `gemini-3.8-flash` by default. Override
  `gemini_model` when applying Terraform if you choose another model that is
  available to your project and region.
- The Vertex AI model location is configured separately from the Cloud Run
  region and defaults to `global`. This matches the global endpoint used by
  the successful Vertex AI test request. To select a regional Vertex AI
  endpoint, set Terraform variable `vertex_ai_location` accordingly.
- `scripts/deploy.sh` builds with Cloud Build and applies Terraform. It does
  not configure GitHub Actions or Workload Identity Federation.
- Configure a Terraform remote backend before collaborating or applying from
  CI. Terraform state can contain sensitive infrastructure metadata; protect
  and lock it.
- The YouTube OAuth secret is created by Terraform, but secret versions are
  added separately so credential values are not embedded in Terraform source
  or passed through Terraform state.
- If Terraform apply is interrupted, inspect `terraform plan` before retrying.
  Do not destroy shared project resources to resolve state drift.
