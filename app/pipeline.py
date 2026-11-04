import hashlib
import json
import logging
import shutil
import tempfile
from pathlib import Path

from app.config import Settings
from app.models import RunRequest
from app.services.cleanup import AssetStore
from app.services.generator import ContentGenerator
from app.services.media import MediaService
from app.services.renderer import render_short
from app.services.state import RunState
from app.services.uploader import ThumbnailUploadError, YouTubePublisher

LOGGER = logging.getLogger(__name__)


def run_id_for(payload: dict, message_id: str | None = None) -> str:
    identity = payload.get("idempotency_key") or message_id or json.dumps(payload, sort_keys=True)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def run_pipeline(payload: dict, message_id: str | None = None) -> str | None:
    settings = Settings.from_env()
    request = RunRequest.model_validate(payload)
    run_id = run_id_for(payload, message_id)
    state = RunState(settings)
    if not state.create_if_new(run_id, request.model_dump()):
        current = state.get(run_id)
        if current.get("status") == "uploaded" or current.get("upload_verified"):
            video_id = current.get("youtube_video_id")
            if video_id:
                AssetStore(settings).delete_run(run_id)
                state.update(run_id, status="complete", cleanup_status="complete")
                return video_id
        LOGGER.info("Duplicate or active request skipped", extra={"run_id": run_id})
        return current.get("youtube_video_id")

    Path(settings.work_dir).mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="yt-short-", dir=settings.work_dir))
    store = AssetStore(settings)
    uploaded_to_youtube = False
    try:
        state.update(run_id, status="generating")
        content = ContentGenerator(settings).generate(request)
        media = MediaService(settings)
        audio_path = work_dir / "narration.mp3"
        video_path = work_dir / "short.mp4"
        thumbnail_path = work_dir / "thumbnail.jpg"
        media.synthesize_narration(content.narration, audio_path)

        # Use the three scene-specific visual prompts when available; fall back to the
        # single visual_prompt so older GeneratedContent responses still work.
        visual_prompts = content.visual_prompts or [content.visual_prompt]
        background_paths = media.generate_backgrounds(visual_prompts, work_dir)

        duration = render_short(
            audio_path,
            content.narration,
            content.title,
            video_path,
            thumbnail_path,
            settings.min_video_seconds,
            min(settings.max_video_seconds, request.duration_seconds + 5),
            background_paths=background_paths,
            badge_label=content.badge_label,
            channel_handle=settings.channel_handle,
        )
        state.update(
            run_id,
            status="rendered",
            title=content.title,
            duration_seconds=duration,
        )
        store.archive_run(run_id, work_dir)
        privacy = request.privacy_status or settings.privacy_status
        try:
            video_id = YouTubePublisher(settings).upload(video_path, thumbnail_path, content, privacy)
        except ThumbnailUploadError as exc:
            uploaded_to_youtube = True
            state.update(
                run_id,
                status="uploaded",
                youtube_video_id=exc.video_id,
                thumbnail_status="failed",
                thumbnail_error=str(exc),
            )
            LOGGER.exception("Video uploaded but thumbnail upload failed", extra={"run_id": run_id})
            store.delete_run(run_id)
            state.update(run_id, status="complete", cleanup_status="complete")
            return exc.video_id
        uploaded_to_youtube = True
        state.update(run_id, status="uploaded", youtube_video_id=video_id)
        store.delete_run(run_id)
        state.update(run_id, status="complete", cleanup_status="complete")
        return video_id
    except Exception as exc:
        LOGGER.exception("Pipeline run failed", extra={"run_id": run_id})
        state.update(
            run_id,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc)[:1000],
            upload_verified=uploaded_to_youtube,
        )
        raise
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir)
