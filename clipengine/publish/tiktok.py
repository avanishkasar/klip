"""TikTok Content Posting API (Direct Post).

Hard truth: Direct Post to public requires your TikTok developer app to pass audit; unaudited apps can only
post as private/draft. TikTok is also blocked in India, so this stays in `manual` mode by default:
we write a .txt sidecar with title/caption/hashtags next to the mp4 and you upload from the app/web.
If/when you have an audited app + token, set CLIP_TIKTOK_MODE=api.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from ..config import get_settings
from .base import PublishError, PublishResult

log = logging.getLogger(__name__)
API = "https://open.tiktokapis.com/v2"


def write_manual_sidecar(path: Path, title: str, caption: str, hashtags: list[str]) -> Path:
    side = path.with_suffix(".tiktok.txt")
    side.write_text(f"TITLE:\n{title}\n\nCAPTION:\n{caption}\n\nHASHTAGS:\n{' '.join(hashtags)}\n", encoding="utf-8")
    return side


def direct_post(path: Path, title: str, privacy: str = "PUBLIC_TO_EVERYONE", timeout_s: int = 600) -> PublishResult:
    s = get_settings()
    if s.clip_tiktok_mode != "api" or not s.clip_tiktok_access_token:
        raise PublishError("TikTok API mode not enabled; use manual sidecar")
    hdr = {"Authorization": f"Bearer {s.clip_tiktok_access_token}", "Content-Type": "application/json; charset=UTF-8"}
    size = path.stat().st_size
    chunk = min(size, 64 * 1024 * 1024)
    total_chunks = max(1, (size + chunk - 1) // chunk)
    with httpx.Client(timeout=120.0) as c:
        init = c.post(f"{API}/post/publish/video/init/", headers=hdr, json={
            "post_info": {"title": title[:2200], "privacy_level": privacy, "disable_duet": False,
                          "disable_comment": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                            "total_chunk_count": total_chunks},
        })
        if init.status_code >= 400 or init.json().get("error", {}).get("code") not in (None, "ok"):
            raise PublishError(f"TikTok init failed: {init.text[:300]}")
        data = init.json()["data"]
        publish_id, upload_url = data["publish_id"], data["upload_url"]
        with path.open("rb") as f:
            for i in range(total_chunks):
                blob = f.read(chunk)
                start = i * chunk
                end = start + len(blob) - 1
                up = c.put(upload_url, content=blob, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(blob)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                })
                if up.status_code not in (200, 201, 206):
                    raise PublishError(f"TikTok chunk {i} failed {up.status_code}: {up.text[:200]}")
        deadline = time.monotonic() + timeout_s
        while True:
            st = c.post(f"{API}/post/publish/status/fetch/", headers=hdr, json={"publish_id": publish_id})
            status = st.json().get("data", {}).get("status")
            if status == "PUBLISH_COMPLETE":
                ids = st.json()["data"].get("publicaly_available_post_id") or []
                vid = str(ids[0]) if ids else publish_id
                return PublishResult(remote_id=vid, url=f"https://www.tiktok.com/@me/video/{vid}")
            if status == "FAILED":
                raise PublishError(f"TikTok publish failed: {st.json()['data'].get('fail_reason')}")
            if time.monotonic() > deadline:
                raise PublishError("TikTok publish timed out")
            time.sleep(5)
