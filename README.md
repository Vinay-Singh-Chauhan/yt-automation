# YouTube Shorts Pipeline

An MVP pipeline for creating and uploading 10–30 second vertical YouTube Shorts.
It uses Vertex AI Gemini for scripts and generated background images, Cloud
Text-to-Speech for narration, FFmpeg for 9:16 rendering, and the YouTube Data
API for upload. Cloud Scheduler and Pub/Sub provide recurring triggers;
Workflows starts a Cloud Run Job for each request.

Start with the implementation guide in [`docs/README.md`](docs/README.md).

**Safe default:** uploads are private unless explicitly configured otherwise.
The Cloud Scheduler job is paused by default. Review generated content and
verify channel permissions before enabling recurring runs or public publishing.
