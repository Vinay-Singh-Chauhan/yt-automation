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
from app.services.media import MediaService
from app.services.renderer import _build_video_filter, _make_caption_segments, render_short
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
        self.assertEqual(first, "one two three")
        self.assertEqual(second, "four five six")

    def test_video_filter_places_captions_in_lower_safe_area(self):
        with tempfile.TemporaryDirectory() as directory:
            title_path = Path(directory) / "title.txt"
            caption_path = Path(directory) / "caption.txt"
            filter_graph = _build_video_filter(title_path, [(caption_path, 0.0, 5.0)])
        self.assertIn("y=1250", filter_graph)
        self.assertIn("y=210", filter_graph)
        self.assertIn("QUICK FACT", filter_graph)
        self.assertIn("enable='between(t,", filter_graph)

    def test_background_image_is_scaled_and_visible_under_graphics(self):
        """Filter graph always starts with scale/crop/eq regardless of input source."""
        with tempfile.TemporaryDirectory() as directory:
            title_path = Path(directory) / "title.txt"
            caption_path = Path(directory) / "caption.txt"
            filter_graph = _build_video_filter(
                title_path, [(caption_path, 0.0, 5.0)]
            )
        self.assertTrue(filter_graph.startswith("scale=1080:1920:"))
        self.assertIn("crop=1080:1920", filter_graph)
        self.assertIn("color=0x10172A@0.38", filter_graph)
        # Title panel retains its semi-transparent overlay.
        self.assertIn("color=0x17213B@0.82", filter_graph)

    def test_renderer_uses_generated_background_as_looped_video_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_path = root / "narration.mp3"
            background_path = root / "background.png"
            audio_path.write_bytes(b"audio")
            background_path.write_bytes(b"image")
            commands = []
            with patch("app.services.renderer.audio_duration", return_value=15.0), patch(
                "app.services.renderer._run", side_effect=commands.append
            ):
                render_short(
                    audio_path,
                    "This narration has enough words for a short.",
                    "A generated background",
                    root / "short.mp4",
                    root / "thumbnail.jpg",
                    10,
                    30,
                    background_path=background_path,
                )
        video_command = commands[0]
        self.assertEqual(video_command[2:4], ["-loop", "1"])
        self.assertIn(str(background_path), video_command)
        self.assertIn("scale=1080:1920:", video_command[video_command.index("-vf") + 1])


class SettingsTests(unittest.TestCase):
    def test_rejects_maximum_duration_above_thirty_seconds(self):
        with patch.dict("os.environ", {"MAX_VIDEO_SECONDS": "31"}):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_image_model_has_vertex_image_model_default(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.gemini_image_model, "gemini-3.1-flash-image")


class MediaServiceTests(unittest.TestCase):
    def test_generate_background_saves_image_from_vertex_response(self):
        settings = Settings.from_env()
        image_client = Mock()
        image_client.models.generate_content.return_value.candidates = [
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            inline_data=SimpleNamespace(data=b"generated-image")
                        )
                    ]
                )
            )
        ]
        with patch("app.services.media.texttospeech.TextToSpeechClient"), patch(
            "app.services.media.genai.Client", return_value=image_client
        ):
            media = MediaService(settings)
            with tempfile.TemporaryDirectory() as directory:
                output_path = Path(directory) / "background.png"
                result = media.generate_background("A calm ocean scene", output_path)
                self.assertEqual(result, output_path)
                self.assertEqual(output_path.read_bytes(), b"generated-image")

        call = image_client.models.generate_content.call_args
        self.assertEqual(call.kwargs["model"], settings.gemini_image_model)
        self.assertEqual(
            call.kwargs["config"].response_modalities,
            ["TEXT", "IMAGE"],
        )
        self.assertEqual(
            call.kwargs["config"].image_config.aspect_ratio,
            "9:16",
        )
        self.assertEqual(
            call.kwargs["config"].image_config.output_mime_type,
            "image/png",
        )

    def test_generate_background_fails_when_response_has_no_image(self):
        settings = Settings.from_env()
        image_client = Mock()
        image_client.models.generate_content.return_value.candidates = []
        with patch("app.services.media.texttospeech.TextToSpeechClient"), patch(
            "app.services.media.genai.Client", return_value=image_client
        ):
            media = MediaService(settings)
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(RuntimeError, "no image data"):
                    media.generate_background(
                        "A calm ocean scene", Path(directory) / "background.png"
                    )

    def test_generate_backgrounds_returns_one_path_per_prompt_in_order(self):
        """generate_backgrounds calls generate_background once per prompt concurrently."""
        settings = Settings.from_env()
        created: list[Path] = []

        def fake_generate_background(prompt: str, output_path: Path) -> Path:
            output_path.write_bytes(prompt.encode())
            created.append(output_path)
            return output_path

        with patch("app.services.media.texttospeech.TextToSpeechClient"), patch(
            "app.services.media.genai.Client"
        ):
            media = MediaService(settings)
            media.generate_background = fake_generate_background  # type: ignore[method-assign]
            with tempfile.TemporaryDirectory() as directory:
                paths = media.generate_backgrounds(
                    ["scene A", "scene B", "scene C"], Path(directory)
                )
        self.assertEqual(len(paths), 3)
        for i, path in enumerate(paths):
            self.assertEqual(path.name, f"background-{i}.png")
            self.assertEqual(path.read_bytes().decode(), f"scene {chr(65 + i)}")

    def test_renderer_slideshow_uses_xfade_filter_complex(self):
        """render_short with background_paths builds an xfade filter_complex command."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_path = root / "narration.mp3"
            audio_path.write_bytes(b"audio")
            bg_paths = []
            for i in range(3):
                p = root / f"bg-{i}.png"
                p.write_bytes(b"img")
                bg_paths.append(p)
            commands = []
            with patch("app.services.renderer.audio_duration", return_value=15.0), patch(
                "app.services.renderer._run", side_effect=commands.append
            ):
                render_short(
                    audio_path,
                    "This narration has enough words for a short video clip.",
                    "Slideshow test",
                    root / "short.mp4",
                    root / "thumbnail.jpg",
                    10,
                    30,
                    background_paths=bg_paths,
                )
        video_command = commands[0]
        self.assertIn("-filter_complex", video_command)
        fc = video_command[video_command.index("-filter_complex") + 1]
        self.assertIn("xfade", fc)
        self.assertIn("dissolve", fc)
        # All three image paths must appear as inputs.
        for bp in bg_paths:
            self.assertIn(str(bp), video_command)


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
