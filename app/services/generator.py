import json
import random
from typing import Sequence

from google import genai
from google.genai import types

from app.config import Settings
from app.models import GeneratedContent, RunRequest

DEFAULT_CATEGORIES: list[str] = [
    "Mind-bending Science & Physics Anomalies",
    "Psychology Insights & Cognitive Biases",
    "Astonishing & Lesser-Known Historical Events",
    "Space & Cosmic Wonders",
    "Timeless Stoic & Philosophical Life Principles",
    "Human Potential & Remarkable Biographies",
    "Fascinating Ocean & Nature Secrets",
    "Curious Inventions & High-Impact Tech Breakthroughs",
]


class ContentGenerator:
    def __init__(self, settings: Settings):
        self._client = genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.vertex_ai_location,
        )
        self._model = settings.gemini_model

    def generate(
        self, request: RunRequest, recent_titles: Sequence[str] | None = None
    ) -> GeneratedContent:
        # Layer 2: Dynamic Category Angle Selection
        chosen_category = random.choice(DEFAULT_CATEGORIES)

        # Layer 1: Avoid repeating past topics
        avoid_clause = ""
        if recent_titles:
            titles_list = "\n".join(f"- {t}" for t in recent_titles)
            avoid_clause = (
                f"\nIMPORTANT - PREVIOUSLY CREATED TOPICS (DO NOT REPEAT OR CLOSELY RESEMBLE THESE):\n"
                f"{titles_list}\n"
                "You MUST introduce a brand new, completely distinct topic and perspective.\n"
            )

        prompt = (
            "Create an original, accurate YouTube Short. Avoid unsupported factual claims; "
            "if the topic is uncertain, use cautious wording. Do not copy existing scripts. "
            f"Topic direction: {request.topic}\n"
            f"Selected exploration angle/theme: {chosen_category}\n"
            f"Language: {request.language}\n"
            f"Target spoken duration: {request.duration_seconds} seconds. "
            f"{avoid_clause}"
            "Write concise narration suitable for natural speech and this duration. "
            "Return JSON with title, description, tags, narration, visual_prompt, "
            "visual_prompts, badge_label, hashtags. "
            "The visual_prompt should describe a simple vertical background card. "
            "visual_prompts must contain exactly 3 entries: each a distinct background "
            "scene for a different moment in the video (opening, middle, closing). "
            "Vary the mood, colour palette, and composition across the 3 entries so the "
            "background visibly changes as the video plays. "
            "No text, words, logos, or captions in any image prompt. "
            "badge_label must be a short ALL-CAPS category tag (max 20 chars) that best "
            "describes the topic — e.g. 'HISTORY', 'SCIENCE', 'PRO TIP', 'DID YOU KNOW', "
            "'FINANCE', 'FITNESS'. "
            "Include relevant disclosure in description "
            "if the topic could be mistaken for professional advice."
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeneratedContent,
                temperature=0.85,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty content response")
        try:
            return GeneratedContent.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("Gemini returned content that did not match the output schema") from exc
