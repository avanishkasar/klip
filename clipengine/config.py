from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Loaded from env / .env; never hard-code secrets."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    clip_workspace: Path = Field(default=Path("./workspace"))
    clip_ffmpeg_bin: str = "ffmpeg"
    clip_ffprobe_bin: str = "ffprobe"
    clip_db_path: Path = Field(default=Path("./workspace/ledger.sqlite3"))

    # Claude
    anthropic_api_key: str | None = None
    clip_claude_model: str = "claude-opus-5-5"
    clip_claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Captions
    clip_whisper_model: str = "small"
    clip_whisper_device: Literal["cuda", "cpu", "auto"] = "auto"
    clip_whisper_compute: str = "float16"

    # YouTube
    clip_yt_client_secrets: Path = Field(default=Path("./secrets/yt_client_secret.json"))
    clip_yt_token_path: Path = Field(default=Path("./secrets/yt_token.json"))

    # Instagram
    clip_ig_user_id: str | None = None
    clip_ig_access_token: str | None = None
    clip_public_media_base_url: str | None = None
    clip_public_media_dir: Path | None = None

    # TikTok
    clip_tiktok_access_token: str | None = None
    clip_tiktok_mode: Literal["manual", "api"] = "manual"

    # PayPal
    clip_paypal_client_id: str | None = None
    clip_paypal_client_secret: str | None = None
    clip_paypal_env: Literal["live", "sandbox"] = "live"

    @field_validator("clip_public_media_base_url")
    @classmethod
    def _strip_slash(cls, v: str | None) -> str | None:
        return v.rstrip("/") if v else v

    # Derived paths
    @property
    def sources_dir(self) -> Path:
        return self.clip_workspace / "sources"

    @property
    def clips_dir(self) -> Path:
        return self.clip_workspace / "clips"

    @property
    def renders_dir(self) -> Path:
        return self.clip_workspace / "renders"

    @property
    def filler_dir(self) -> Path:
        return self.clip_workspace / "filler"

    @property
    def logs_dir(self) -> Path:
        return self.clip_workspace / "logs"

    def ensure_dirs(self) -> None:
        for d in (self.sources_dir, self.clips_dir, self.renders_dir, self.logs_dir, self.filler_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.clip_db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
