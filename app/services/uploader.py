import json
from pathlib import Path

from google.cloud import secretmanager
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import Settings
from app.models import GeneratedContent

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class ThumbnailUploadError(RuntimeError):
    def __init__(self, video_id: str):
        super().__init__(f"YouTube video {video_id} uploaded, but thumbnail upload failed")
        self.video_id = video_id


class YouTubePublisher:
    def __init__(self, settings: Settings):
        self._settings = settings

    def _service(self):
        secret_name = (
            f"projects/{self._settings.project_id}/secrets/"
            f"{self._settings.youtube_secret_name}/versions/latest"
        )
        secret = secretmanager.SecretManagerServiceClient().access_secret_version(
            request={"name": secret_name}
        )
        try:
            payload = json.loads(secret.payload.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("YouTube OAuth secret must contain a JSON credential object") from exc

        credentials = Credentials(
            token=None,
            refresh_token=payload["refresh_token"],
            token_uri=payload.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=payload["client_id"],
            client_secret=payload["client_secret"],
            scopes=[YOUTUBE_SCOPE],
        )
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def upload(
        self,
        video_path: Path,
        thumbnail_path: Path,
        content: GeneratedContent,
        privacy_status: str,
    ) -> str:
        if privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("Invalid YouTube privacy status")
        youtube = self._service()
        response = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": content.title,
                    "description": content.description,
                    "tags": content.tags + [tag.lstrip("#") for tag in content.hashtags],
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            },
            media_body=MediaFileUpload(
                str(video_path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024
            ),
        ).execute()
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube upload response did not contain a video ID")

        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
            ).execute()
        except Exception as exc:
            raise ThumbnailUploadError(video_id) from exc
        return video_id
