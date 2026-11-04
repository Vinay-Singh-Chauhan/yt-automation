# Architecture and data flow

```text
Cloud Scheduler (paused by default)
    -> Pub/Sub: yt-trigger-topic
        -> authenticated push subscription
            -> Cloud Run intake: /pubsub
                -> Workflows execution
                    -> Cloud Run Job: yt-pipeline-worker
                        -> Vertex AI Gemini text and image generation (global endpoint by default)
                        -> Cloud Text-to-Speech
                        -> FFmpeg rendering
                        -> Cloud Storage temporary run prefix
                        -> YouTube Data API upload and status check
                        -> delete run prefix after successful verification
                        -> Firestore run record
```

## Why the extra components are present

- **Workflows** keeps the Pub/Sub handler short. It starts the batch Job rather
  than doing a long render in an HTTP request.
- **Firestore** records each run and prevents a Pub/Sub redelivery from
  uploading another copy. Failed runs can be retried; complete runs are skipped.
- **Cloud Run Job** has a longer execution timeout and more memory/CPU than the
  intake service, which is appropriate for FFmpeg.
- **Cloud Scheduler** publishes the same JSON request that can be sent manually
  to Pub/Sub. Its Terraform job starts paused to prevent accidental recurring
  publishing before the channel has been tested.
- **Cloud Storage** is private and temporary. It archives the generated audio,
  MP4, and thumbnail under `runs/<run-id>/` during the pipeline. After YouTube
  confirms the uploaded video status, the prefix is removed. A one-day lifecycle
  policy deletes leftovers if a run fails or the worker stops.

## Trigger format

Pub/Sub message data is UTF-8 JSON, for example:

```json
{
  "topic": "Three surprising facts about deep-sea animals",
  "language": "en",
  "duration_seconds": 20,
  "privacy_status": "private",
  "idempotency_key": "deep-sea-facts-2026-11-04"
}
```

`topic` is required. Duration must be 10–30 seconds. `privacy_status` and
`idempotency_key` are optional; the configured channel privacy is used if the
request does not specify it. Stable idempotency keys are useful for manually
retrying a request without creating a second upload.

After publishing a test message, check each stage:

```bash
gcloud pubsub subscriptions describe yt-trigger-push \
  --project=YOUR_PROJECT_ID

gcloud workflows executions list yt-pipeline-workflow \
  --location=us-central1 --project=YOUR_PROJECT_ID --limit=10

gcloud run jobs executions list --job=yt-pipeline-worker \
  --region=us-central1 --project=YOUR_PROJECT_ID --limit=10
```

For a failed Workflow, describe its execution by ID:

```bash
gcloud workflows executions describe EXECUTION_ID \
  --workflow=yt-pipeline-workflow \
  --location=us-central1 --project=YOUR_PROJECT_ID
```

The Pub/Sub push endpoint returning HTTP 204 means it accepted the event and
started a Workflow; it does not mean video generation or upload succeeded.

## Gemini Nano

Gemini Nano is designed for on-device inference on supported devices. It is not
the model endpoint used by this server-side Google Cloud architecture. The
server pipeline uses Gemini through Vertex AI; it can later accept a Nano-made
topic or draft from a separate mobile/desktop client without changing the
server-side upload and rendering workflow.
