import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.api import _decode_pubsub
from app.config import Settings
from app.models import GeneratedContent, RunRequest
from app.pipeline import run_id_for
from app.services.renderer import _build_video_filter, _make_caption_segments
from app.services.uploader import YouTubePublisher


class RequestModelTests(unittest.TestCase):
    def test_accepts_requested_short_duration_range(self):
        for duration in (10, 20, 30):
            with self.subTest(duration=duration):
                request = RunRequest(topic="A useful short topic", duration_seconds=duration)
                self.assertEqual(request.duration_seconds, duration)

    def test_rejects_duration_outside_shorts_range(self):
        for duration in (9, 31):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    RunRequest(topic="A useful short topic", duration_seconds=duration)

    def test_privacy_status_must_be_supported(self):
        with self.assertRaises(ValueError):
            RunRequest(topic="A useful short topic", privacy_status="scheduled")


class PubSubMessageTests(unittest.TestCase):
    def test_decodes_pubsub_message(self):
        data = {"topic": "A useful short topic", "duration_seconds": 20}
        body = {
            "message": {
                "data": base64.b64encode(json.dumps(data).encode()).decode(),
                "messageId": "message-123",
            }
        }
        self.assertEqual(_decode_pubsub(body), (data, "message-123"))

    def test_rejects_invalid_base64(self):
        with self.assertRaises(HTTPException) as error:
            _decode_pubsub({"message": {"data": "%%%?"}})
        self.assertEqual(error.exception.status_code, 400)


class RunIdentityTests(unittest.TestCase):
    def test_explicit_idempotency_key_is_stable(self):
        first = {"topic": "A useful short topic", "idempotency_key": "run-1"}
        second = {"topic": "Updated payload", "idempotency_key": "run-1"}
        self.assertEqual(run_id_for(first), run_id_for(second))

    def test_message_id_is_used_when_no_explicit_key(self):
        self.assertEqual(run_id_for({"topic": "A useful short topic"}, "abc"), run_id_for({}, "abc"))


class CaptionTests(unittest.TestCase):
    def test_caption_segments_are_timed_and_wrapped(self):
        with tempfile.TemporaryDirectory() as directory:
            segments = _make_caption_segments(
                "one two three four five six", 10.0, Path(directory)
            )
            first = segments[0][0].read_text(encoding="utf-8")
            second = segments[1][0].read_text(encoding="utf-8")
        self.assertEqual(len(segments), 2)
        self.assertEqual((segments[0][1], segments[0][2]), (0.0, 5.0))
        self.assertEqual((segments[1][1], segments[1][2]), (5.0, 10.0))
        self.assertEqual(first, "one two three four five")
        self.assertEqual(second, "six")

    def test_video_filter_places_captions_in_lower_safe_area(self):
        with tempfile.TemporaryDirectory() as directory:
            title_path = Path(directory) / "title.txt"
            caption_path = Path(directory) / "caption.txt"
            filter_graph = _build_video_filter(title_path, [(caption_path, 0.0, 5.0)])
        self.assertIn("y=1400", filter_graph)
        self.assertIn("y=300", filter_graph)
        self.assertIn("THE BIG IDEA", filter_graph)
        self.assertIn("enable='gte(t,", filter_graph)


class SettingsTests(unittest.TestCase):
    def test_rejects_maximum_duration_above_thirty_seconds(self):
        with patch.dict("os.environ", {"MAX_VIDEO_SECONDS": "31"}):
            with self.assertRaises(ValueError):
                Settings.from_env()


class YouTubePublisherTests(unittest.TestCase):
    def test_uses_video_id_from_upload_response_without_read_scope(self):
        youtube = Mock()
        youtube.videos.return_value.insert.return_value.execute.return_value = {
            "id": "video-123",
            "status": {"uploadStatus": "uploaded"},
        }
        publisher = YouTubePublisher(SimpleNamespace())
        publisher._service = Mock(return_value=youtube)

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "short.mp4"
            thumbnail = Path(directory) / "thumbnail.jpg"
            video.write_bytes(b"video")
            thumbnail.write_bytes(b"thumbnail")
            with patch("app.services.uploader.MediaFileUpload"):
                video_id = publisher.upload(
                    video,
                    thumbnail,
                    GeneratedContent(
                        title="Test Short",
                        description="Test description",
                        narration="This is a test narration.",
                        visual_prompt="A clean vertical title card.",
                    ),
                    "private",
                )

        self.assertEqual(video_id, "video-123")
        youtube.videos.return_value.list.assert_not_called()
        youtube.thumbnails.return_value.set.assert_called_once()


if __name__ == "__main__":
    unittest.main()
