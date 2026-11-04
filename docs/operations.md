# Operations, safety, and cost

## Safety and quality controls

- Use `private` visibility during development and pilot runs.
- Review every video for factual accuracy, rights, policy compliance, and
  suitable disclosures before changing the default to public.
- Gemini output can be incorrect or inappropriate. The pipeline does not claim
  to fact-check generated content.
- Do not use the generated visual prompt as proof that any asset was actually
  created or licensed. This MVP's visuals are FFmpeg-rendered infographic
  graphics rather than topic-specific generated or stock imagery.
- Avoid personal data and sensitive topics in prompts unless there is a clear
  need and an approved handling policy.
- Configure a Google Cloud budget and billing alerts before enabling a daily
  Scheduler.
- Limit IAM to the provided runtime and workflow service accounts. Do not use
  owner credentials for the deployed services.

## Failure handling

The Pub/Sub push handler returns success only after Workflows accepts an
execution; malformed requests return 400 and transient workflow-start failures
return 503 for Pub/Sub retry. Cloud Run Job retries and Firestore idempotency
avoid duplicate work for successful runs.

## Check the latest request status

Use the following commands to follow each request. Replace the project ID or
region if you deployed to different values.

List the latest Cloud Run Job executions:

```bash
gcloud run jobs executions list \
  --job=yt-pipeline-worker \
  --region=us-central1 \
  --project=YOUR_PROJECT_ID \
  --limit=10
```

Describe an execution using its name from the list:

```bash
gcloud run jobs executions describe EXECUTION_NAME \
  --region=us-central1 \
  --project=YOUR_PROJECT_ID
```

If it is running or failed, inspect the task state and logs:

```bash
gcloud run jobs executions tasks list \
  --execution=EXECUTION_NAME \
  --region=us-central1 \
  --project=YOUR_PROJECT_ID
```

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="yt-pipeline-worker" AND labels."run.googleapis.com/execution_name"="EXECUTION_NAME"' \
  --project=YOUR_PROJECT_ID \
  --limit=50 \
  --format='value(timestamp,severity,textPayload)'
```

To confirm the Pub/Sub request started a Workflow:

```bash
gcloud workflows executions list yt-pipeline-workflow \
  --location=us-central1 \
  --project=YOUR_PROJECT_ID \
  --limit=10
```

A successful Workflow means it launched the Cloud Run Job; it does not mean
video generation or upload succeeded. The Job execution status and logs show
the outcome of those later stages. After a successful run, use the YouTube
video ID in the worker logs or Firestore `pipeline_runs` record to check the
private video in YouTube Studio.

Inspect:

- Cloud Run service logs for Pub/Sub intake and workflow-start errors.
- Cloud Workflows executions for job launch errors.
- Cloud Run Job executions/logs for generation, render, or upload failures.
- Firestore `pipeline_runs` for status, retry count, and any YouTube video ID.
- Cloud Storage `runs/` prefixes for temporary items. Successful runs remove
  them; the lifecycle policy deletes leftovers after one day.

The current pipeline raises a failure when the narration duration falls
outside the configured limits; adjust the script or TTS settings and retry
using the same idempotency key.

## Costs

No fixed monthly price is guaranteed. The actual bill depends on model input
and output tokens, voice duration, FFmpeg CPU/memory and runtime, Cloud Run
request/job usage, Storage volume, external media licenses, YouTube API quotas,
and network egress. The current motion-card approach has no stock-media
subscription cost.

For 30 short videos per month, the previous `$7–$20` estimate should be treated
as an optimistic low-usage scenario, not a quote. Use the Google Cloud Pricing
Calculator with expected video duration and job runtime; set budget alerts and
review the first month's billing before increasing frequency. The one-day
Storage lifecycle policy and post-upload deletion limit storage retention, but
do not guarantee zero storage or network charges.

## Planned extension points

- Add a licensed stock or generated-image provider in `services/media.py`, with
  attribution/license metadata, input validation, and download limits.
- Add a manual approval stage between render and upload, if fully automatic
  publishing is not yet acceptable.
- Add YouTube Analytics and a reporting store in a later phase; analytics is
  not part of this MVP.
- Add GitHub Actions and Workload Identity Federation after setting up remote
  Terraform state and approving the CI deployment identity.
