import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    vertex_ai_location: str
    workflow_name: str
    bucket_name: str
    firestore_collection: str
    youtube_secret_name: str
    gemini_model: str
    gemini_image_model: str
    tts_voice: str
    tts_language: str
    privacy_status: str
    max_video_seconds: int
    min_video_seconds: int
    work_dir: str
    channel_handle: str

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            region=os.environ.get("REGION", "us-central1"),
            vertex_ai_location=os.environ.get("VERTEX_AI_LOCATION", "global"),
            workflow_name=os.environ.get("WORKFLOW_NAME", ""),
            bucket_name=os.environ.get("ASSETS_BUCKET", ""),
            firestore_collection=os.environ.get("FIRESTORE_COLLECTION", "pipeline_runs"),
            youtube_secret_name=os.environ.get("YOUTUBE_OAUTH_SECRET", "yt-oauth-credentials"),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            gemini_image_model=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            tts_voice=os.environ.get("TTS_VOICE", "en-US-Neural2-F"),
            tts_language=os.environ.get("TTS_LANGUAGE", "en-US"),
            privacy_status=os.environ.get("YOUTUBE_PRIVACY_STATUS", "private"),
            max_video_seconds=int(os.environ.get("MAX_VIDEO_SECONDS", "30")),
            min_video_seconds=int(os.environ.get("MIN_VIDEO_SECONDS", "10")),
            work_dir=os.environ.get("WORK_DIR", "/tmp/yt-short"),
            channel_handle=os.environ.get("CHANNEL_HANDLE", "WATCH  •  LEARN  •  SHARE"),
        )
        if settings.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("YOUTUBE_PRIVACY_STATUS must be private, unlisted, or public")
        if not 1 <= settings.min_video_seconds <= settings.max_video_seconds <= 30:
            raise ValueError("Short duration must be between 1 and 30 seconds")
        return settings
