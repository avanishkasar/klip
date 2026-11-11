"""YouTube Shorts upload via YouTube Data API v3 (resumable upload, OAuth installed-app flow).

Setup (one time):
  1. console.cloud.google.com -> new project -> enable "YouTube Data API v3"
  2. OAuth consent screen (External, add yourself as test user) -> Credentials -> OAuth client ID (Desktop app)
  3. Download JSON -> ./secrets/yt_client_secret.json
First run opens a browser for consent; token cached at CLIP_YT_TOKEN_PATH.
Quota: an upload costs 1600 units of the 10,000/day default => ~6 uploads/day until quota increase is granted.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..config import get_settings
from .base import PublishError, PublishResult

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def _service() -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:  # pragma: no cover
        raise PublishError("google libs missing: pip install 'clipengine[youtube]'") from e
    s = get_settings()
    creds = None
    if s.clip_yt_token_path.exists():
        creds = Credentials.from_authorized_user_file(str(s.clip_yt_token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not s.clip_yt_client_secrets.exists():
                raise PublishError(f"missing OAuth client secrets at {s.clip_yt_client_secrets}")
            flow = InstalledAppFlow.from_client_secrets_file(str(s.clip_yt_client_secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        s.clip_yt_token_path.parent.mkdir(parents=True, exist_ok=True)
        s.clip_yt_token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_short(
    path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "public",
    made_for_kids: bool = False,
    category_id: str = "20",  # Gaming
) -> PublishResult:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not path.exists():
        raise PublishError(f"{path} missing")
    if "#Shorts" not in title and "#Shorts" not in description:
        description = f"{description}\n#Shorts"
    yt = _service()
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": [t.lstrip("#") for t in tags][:30], "categoryId": category_id},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids},
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response: dict[str, Any] | None = None
    backoff = 2.0
    errors = 0
    while response is None:
        try:
            _, response = req.next_chunk()
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and errors < 6:
                errors += 1
                log.warning("YouTube %s; retry in %.0fs", e.resp.status, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if e.resp.status == 403 and b"quotaExceeded" in (e.content or b""):
                raise PublishError("YouTube daily quota exceeded (10k units; 1600/upload). Try tomorrow or request increase.") from e
            raise PublishError(f"YouTube HTTP {e.resp.status}: {e.content[:300]!r}") from e
    vid = response["id"]
    return PublishResult(remote_id=vid, url=f"https://youtube.com/shorts/{vid}")


def fetch_views(video_ids: list[str]) -> dict[str, int]:
    if not video_ids:
        return {}
    yt = _service()
    out: dict[str, int] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        resp = yt.videos().list(part="statistics", id=",".join(chunk)).execute()
        for item in resp.get("items", []):
            out[item["id"]] = int(item.get("statistics", {}).get("viewCount", 0))
    return out
