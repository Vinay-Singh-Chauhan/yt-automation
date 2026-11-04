from pathlib import Path

from google.cloud import texttospeech

from app.config import Settings


class MediaService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = texttospeech.TextToSpeechClient()

    def synthesize_narration(self, text: str, output_path: Path) -> None:
        response = self._client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=self._settings.tts_language,
                name=self._settings.tts_voice,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
            ),
        )
        if not response.audio_content:
            raise RuntimeError("Text-to-Speech returned empty audio")
        output_path.write_bytes(response.audio_content)

    def download_assets(self, visual_prompt: str, output_dir: Path) -> list[Path]:
        """Return no external assets in the MVP; FFmpeg creates a generated motion card."""
        del visual_prompt, output_dir
        return []
