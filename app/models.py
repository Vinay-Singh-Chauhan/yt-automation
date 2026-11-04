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
    hashtags: list[str] = Field(default_factory=list, max_length=10)
