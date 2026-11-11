from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, field_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class Platform(StrEnum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class ClipStatus(StrEnum):
    CANDIDATE = "candidate"
    RENDERED = "rendered"
    PUBLISHED = "published"
    REJECTED = "rejected"


class PostStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    MANUAL = "manual"  # rendered + metadata ready, upload done by hand (TikTok w/o audited app)


class Campaign(BaseModel):
    """A paid clipping campaign (Whop Content Rewards / direct deal / platform fund)."""

    id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(default="whop", description="whop | direct | platform")
    rate_per_1k_views_usd: Decimal = Field(ge=0)
    max_payout_per_clip_usd: Decimal | None = Field(default=None, ge=0)
    min_views_for_payout: int = Field(default=0, ge=0)
    platforms: list[Platform] = Field(default_factory=lambda: [Platform.YOUTUBE, Platform.INSTAGRAM])
    requirements: str = ""
    url: HttpUrl | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("rate_per_1k_views_usd", "max_payout_per_clip_usd", mode="before")
    @classmethod
    def _dec(cls, v: object) -> object:
        return Decimal(str(v)) if v is not None and not isinstance(v, Decimal) else v


class SourceVideo(BaseModel):
    id: int | None = None
    url: str
    title: str = ""
    local_path: Path | None = None
    duration_s: float | None = None
    creator: str = ""
    license_note: str = Field(
        default="",
        description="Why you are allowed to clip this (campaign brief URL, creator permission, own footage).",
    )
    created_at: datetime = Field(default_factory=utcnow)


class HighlightWindow(BaseModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    score: float = Field(ge=0)
    reason: str = ""

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


class ClipMeta(BaseModel):
    """Claude-generated packaging for one clip."""

    hook_text: str = Field(max_length=60, description="On-screen hook, first 1.5s")
    title: str = Field(max_length=100)
    caption: str = Field(max_length=2200)
    hashtags: list[str] = Field(max_length=12)
    why_it_works: str = Field(max_length=300)


class Clip(BaseModel):
    id: int | None = None
    source_id: int
    campaign_id: int | None = None
    start_s: float
    end_s: float
    score: float = 0.0
    status: ClipStatus = ClipStatus.CANDIDATE
    render_path: Path | None = None
    meta: ClipMeta | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Post(BaseModel):
    id: int | None = None
    clip_id: int
    platform: Platform
    status: PostStatus = PostStatus.PENDING
    remote_id: str | None = None
    url: str | None = None
    views: int = 0
    last_synced_at: datetime | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Payout(BaseModel):
    id: int | None = None
    campaign_id: int | None = None
    provider: str = Field(description="paypal | whop | bank | other")
    provider_txn_id: str
    amount: Decimal
    currency: str = "USD"
    amount_inr: Decimal | None = None
    received_at: datetime
    note: str = ""

    @field_validator("amount", "amount_inr", mode="before")
    @classmethod
    def _dec(cls, v: object) -> object:
        return Decimal(str(v)) if v is not None and not isinstance(v, Decimal) else v
