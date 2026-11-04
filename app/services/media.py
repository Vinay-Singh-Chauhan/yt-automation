from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.cloud import texttospeech
from google.genai import types

from app.config import Settings


class MediaService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = texttospeech.TextToSpeechClient()
        self._image_client = genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.vertex_ai_location,
        )

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

    def generate_background(self, visual_prompt: str, output_path: Path) -> Path:
        prompt = (
            "Create a polished, original 9:16 vertical background image for a short "
            "educational video. Do not include lettering, words, captions, logos, or "
            "watermarks. Keep the central composition visually clear so graphic panels "
            f"and captions can be overlaid. Visual direction: {visual_prompt}"
        )
        response = self._image_client.models.generate_content(
            model=self._settings.gemini_image_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                image_config=types.ImageConfig(
                    aspect_ratio="9:16",
                    image_size="1K",
                    output_mime_type="image/png",
                ),
            ),
        )
        for candidate in response.candidates or []:
            if candidate.content is None:
                continue
            for part in candidate.content.parts or []:
                if part.inline_data and part.inline_data.data:
                    output_path.write_bytes(part.inline_data.data)
                    return output_path
        raise RuntimeError("Gemini image generation returned no image data")

    def generate_backgrounds(
        self, visual_prompts: list[str], output_dir: Path
    ) -> list[Path]:
        """Generate one image per prompt concurrently and return paths in prompt order.

        Each image is saved as ``background-0.png``, ``background-1.png``, … so the
        caller can pass the ordered list straight to the renderer's slideshow path.
        """
        if not visual_prompts:
            raise ValueError("At least one visual prompt is required")

        output_paths = [
            output_dir / f"background-{i}.png" for i in range(len(visual_prompts))
        ]

        def _generate(index: int) -> int:
            self.generate_background(visual_prompts[index], output_paths[index])
            return index

        with ThreadPoolExecutor(max_workers=len(visual_prompts)) as pool:
            futures = {pool.submit(_generate, i): i for i in range(len(visual_prompts))}
            for future in as_completed(futures):
                future.result()  # re-raise any exception from the worker

        return output_paths
