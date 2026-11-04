# Implementation details

## Application modules

| Module | Responsibility |
|---|---|
| `app/api.py` | FastAPI health check and Pub/Sub push endpoint. It validates message JSON and starts a Workflows execution. |
| `app/models.py` | Validates topics, duration, language, privacy, and Gemini output. |
| `app/services/generator.py` | Calls Gemini through the Vertex AI-enabled `google-genai` client and validates structured JSON output. |
| `app/services/media.py` | Synthesizes narration using Cloud Text-to-Speech. The MVP returns no downloaded assets; the renderer supplies the visuals. |
| `app/services/renderer.py` | Checks audio duration and uses FFmpeg/FFprobe to create a vertical infographic-style H.264/AAC video, fixed lower-third captions, and JPEG thumbnail. |
| `app/services/uploader.py` | Reads OAuth JSON from Secret Manager, uploads the MP4 and thumbnail, then checks the YouTube upload status. |
| `app/services/cleanup.py` | Copies temporary artifacts to a per-run Cloud Storage prefix and deletes local files or the successful run prefix. |
| `app/services/state.py` | Uses Firestore transactions to claim a run, guard duplicate deliveries, and record progress. |
| `app/pipeline.py` | Connects generation, narration, rendering, storage, upload, run state, and cleanup. |
| `app/worker.py` | Cloud Run Job entry point. |

## Generation and rendering

Gemini returns a title, description, tags, narration, visual prompt, and
hashtags. The narration is synthesized with the configured Cloud TTS voice.
FFprobe measures the audio before rendering; audio outside the configured
duration range fails the run rather than silently producing a Short that
misses the requirement. Captions are burned into a 1080×1920 portrait video.

The renderer creates a branded infographic-style composition with a title
panel, chart bars that reveal progressively during the opening, and timed
narration captions positioned in the lower safe area. `visual_prompt` is preserved in the generated content for
future image/video provider integration, but this MVP does not download stock
media or call a generative image endpoint. This keeps first deployment simpler
and avoids unreviewed third-party asset licensing.

## Idempotency and retries

The run key is derived from request `idempotency_key`, Pub/Sub `messageId`, or a
stable hash of the request. Firestore atomically claims a new run. Recent
in-progress runs and completed runs are not repeated. Failed or stale runs can
be reclaimed. The upload is done only after content generation and rendering
succeed.

If upload verification succeeds but Storage deletion fails, the recorded video
ID and upload flag let a retry perform cleanup without uploading a second
video. If an upload fails before YouTube returns a verified video ID, local
temporary files are removed and the Cloud Storage lifecycle policy is the
fallback for any partially archived files.

## Publishing and cleanup behavior

The default visibility is `private`. A request can set `private`, `unlisted`,
or `public`; public publishing should only be enabled after human review and
channel-specific policy checks. Once YouTube reports the upload as `uploaded`
or `processed`, the pipeline stores the video ID and removes the corresponding
Cloud Storage prefix. The lifecycle rule removes abandoned objects after one
day; it is not the normal cleanup mechanism.

YouTube API acceptance does not mean YouTube's transcoding is finished. The
pipeline checks that the upload response contains a video ID; processing and
public availability may continue asynchronously. It does not call `videos.list`
because that requires a read scope beyond the upload-only OAuth permission.

## Configuration

The application reads these environment variables; Terraform supplies the
deployed values:

| Variable | Default | Description |
|---|---:|---|
| `GOOGLE_CLOUD_PROJECT` | empty | Project containing Vertex AI and resources. |
| `REGION` | `us-central1` | Cloud location. |
| `VERTEX_AI_LOCATION` | `global` | Vertex AI model endpoint location; independent of the Cloud Run region. |
| `WORKFLOW_NAME` | empty | Workflow to start from Pub/Sub intake. |
| `ASSETS_BUCKET` | empty | Private temporary asset bucket. |
| `YOUTUBE_OAUTH_SECRET` | `yt-oauth-credentials` | Secret containing YouTube OAuth JSON. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Vertex AI Gemini model ID used for content generation. |
| `TTS_VOICE` | `en-US-Neural2-F` | Text-to-Speech voice. |
| `TTS_LANGUAGE` | `en-US` | Text-to-Speech language code. |
| `YOUTUBE_PRIVACY_STATUS` | `private` | Default visibility. |
| `MIN_VIDEO_SECONDS` | `10` | Lower duration limit. |
| `MAX_VIDEO_SECONDS` | `30` | Upper duration limit. |
| `WORK_DIR` | `/tmp/yt-short` | Temporary work directory. |

## Tests and extension points

The application is separated so tests can mock Gemini, TTS, Storage,
Firestore, and YouTube APIs. Before enabling automatic publishing, add
provider-mocked tests for those service boundaries and run an end-to-end private
upload in a test channel. A later media-provider implementation should include
license/attribution metadata, download size/time limits, and safe URL validation.
