# Implementation documentation

Read these in order:

1. [Architecture and data flow](architecture.md)
2. [Implementation details](implementation.md)
3. [Deployment guide](deployment.md)
4. [YouTube OAuth setup](youtube-oauth.md)
5. [Operations, safety, and cost](operations.md)

The current implementation is a working MVP foundation. It can generate
original narration, metadata, and a background image, create a branded Short,
upload it, and remove temporary assets after a verified YouTube upload.

## Current MVP boundaries

- Video duration is checked against the configured 10–30 second limits.
- Video output is portrait 1080×1920, H.264/AAC MP4 with burned-in captions.
- Visuals use a Gemini-generated 9:16 background with FFmpeg-rendered branded
  graphics, a title panel, and fixed safe-position captions. Image generation
  requires Vertex AI access and incurs model usage charges.
- Gemini Nano is not used by the cloud service. Nano is an on-device model; the
  Cloud Run pipeline calls Gemini on Vertex AI. A device-side Nano client can be
  added separately for local ideation or preprocessing.
- Uploads are `private` by default, and the scheduled job is paused by default.
- Temporary objects are deleted immediately after upload verification. A
  one-day Storage lifecycle rule is a backstop for abandoned run prefixes.
- The code and Terraform are not deployed until you run the documented setup
  commands in your own Google Cloud project and supply YouTube OAuth credentials.
