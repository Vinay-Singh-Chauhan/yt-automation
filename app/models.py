from typing import Literal

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    language: str = Field(default="en", min_length=2, max_length=12)
    duration_seconds: int = Field(default=20, ge=10, le=30)
    privacy_status: Literal["private", "unlisted", "public"] | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class GeneratedContent(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    narration: str = Field(min_length=1, max_length=6000)
    visual_prompt: str = Field(min_length=1, max_length=1000)
    visual_prompts: list[str] = Field(
        default_factory=list,
        description=(
            "Three distinct visual scene descriptions for the background slideshow. "
            "Each should be unique in mood, colour, and composition so the background "
            "visibly changes as the video plays. Leave empty to fall back to visual_prompt."
        ),
        max_length=3,
    )
    badge_label: str = Field(
        default="QUICK FACT",
        max_length=20,
        description=(
            "Short category badge shown in the top-left corner. "
            "Examples: 'HISTORY', 'SCIENCE', 'PRO TIP', 'DID YOU KNOW'. "
            "Use ALL CAPS. Max 20 characters."
        ),
    )
    hashtags: list[str] = Field(default_factory=list, max_length=10)
