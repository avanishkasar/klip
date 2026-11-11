"""Instagram Reels publish via Graph API (Instagram Login or Facebook Login for Business).

Requirements:
  - Instagram account switched to Creator or Business.
  - A Meta app with instagram_business_content_publish (+ instagram_business_basic) permissions, long-lived token.
  - The API pulls the video from a PUBLIC https URL: we copy the render to CLIP_PUBLIC_MEDIA_DIR which you sync/
    serve under CLIP_PUBLIC_MEDIA_BASE_URL (Cloudflare R2 public bucket is the cheapest: free egress).
Limit: 25 API publishes per 24h per account.
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import httpx

from ..config import get_settings
from .base import PublishError, PublishResult

log = logging.getLogger(__name__)
GRAPH = "https://graph.instagram.com/v21.0"


def _cfg() -> tuple[str, str]:
    s = get_settings()
    if not (s.clip_ig_user_id and s.clip_ig_access_token):
        raise PublishError("CLIP_IG_USER_ID / CLIP_IG_ACCESS_TOKEN not set")
    return s.clip_ig_user_id, s.clip_ig_access_token


def stage_public(path: Path) -> str:
    """Copy render into the public media dir and return its public URL."""
    s = get_settings()
    if not (s.clip_public_media_dir and s.clip_public_media_base_url):
        raise PublishError("CLIP_PUBLIC_MEDIA_DIR / CLIP_PUBLIC_MEDIA_BASE_URL not set (needed for Reels API)")
    s.clip_public_media_dir.mkdir(parents=True, exist_ok=True)
    dst = s.clip_public_media_dir / path.name
    if dst.resolve() != path.resolve():
        shutil.copy2(path, dst)
    return f"{s.clip_public_media_base_url}/{path.name}"


def publish_reel(video_url: str, caption: str, share_to_feed: bool = True, timeout_s: int = 600) -> PublishResult:
    ig_user, token = _cfg()
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{GRAPH}/{ig_user}/media", data={
            "media_type": "REELS", "video_url": video_url, "caption": caption[:2200],
            "share_to_feed": "true" if share_to_feed else "false", "access_token": token,
        })
        if r.status_code >= 400:
            raise PublishError(f"IG container create failed {r.status_code}: {r.text[:300]}")
        container = r.json()["id"]
        deadline = time.monotonic() + timeout_s
        delay = 5.0
        while True:
            st = c.get(f"{GRAPH}/{container}", params={"fields": "status_code,status", "access_token": token})
            if st.status_code >= 400:
                raise PublishError(f"IG status failed {st.status_code}: {st.text[:300]}")
            code = st.json().get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise PublishError(f"IG container {code}: {st.json().get('status')}")
            if time.monotonic() > deadline:
                raise PublishError("IG container processing timed out")
            time.sleep(delay)
            delay = min(delay * 1.5, 30)
        p = c.post(f"{GRAPH}/{ig_user}/media_publish", data={"creation_id": container, "access_token": token})
        if p.status_code >= 400:
            raise PublishError(f"IG publish failed {p.status_code}: {p.text[:300]}")
        media_id = p.json()["id"]
        perm = c.get(f"{GRAPH}/{media_id}", params={"fields": "permalink", "access_token": token})
        url = perm.json().get("permalink", f"https://www.instagram.com/reel/{media_id}") if perm.status_code < 400 else ""
    return PublishResult(remote_id=media_id, url=url)


def fetch_views(media_ids: list[str]) -> dict[str, int]:
    _, token = _cfg()
    out: dict[str, int] = {}
    with httpx.Client(timeout=30.0) as c:
        for mid in media_ids:
            r = c.get(f"{GRAPH}/{mid}/insights", params={"metric": "views", "access_token": token})
            if r.status_code >= 400:
                log.warning("IG insights %s: %s", mid, r.text[:200])
                continue
            for item in r.json().get("data", []):
                if item.get("name") == "views":
                    out[mid] = int(item.get("values", [{}])[0].get("value", 0))
    return out
