from __future__ import annotations

import logging
import re
from pathlib import Path

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import get_settings
from .ffmpeg import probe
from .models import SourceVideo

log = logging.getLogger(__name__)
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SourceError(RuntimeError):
    pass


def _slug(s: str, n: int = 60) -> str:
    return _SAFE.sub("-", s).strip("-")[:n] or "video"


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type(SourceError),
)
def download(url: str, section: tuple[int, int] | None = None, creator: str = "", license_note: str = "") -> SourceVideo:
    """Download a VOD (or a time section of it) with yt-dlp. Returns SourceVideo with local_path set.

    section=(start_s, end_s) downloads only that range (saves GBs on 6h streams).
    Only download content you have the right to clip (campaign brief / creator permission / own footage).
    """
    try:
        import yt_dlp  # lazy: heavy import
    except ImportError as e:  # pragma: no cover
        raise SourceError("yt-dlp not installed: pip install yt-dlp") from e

    s = get_settings()
    out_dir = s.sources_dir
    opts: dict[str, object] = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(id)s__%(title).60B.%(ext)s"),
        "restrictfilenames": True,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "quiet": True,
        "no_warnings": True,
    }
    if section:
        a, b = section
        if b <= a:
            raise ValueError("section end must be > start")
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(a, b)])
        opts["force_keyframes_at_cuts"] = True
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    except yt_dlp.utils.DownloadError as e:
        raise SourceError(str(e)) from e
    if not path.exists():
        # merge may have produced a different suffix; find newest matching id
        cands = sorted(out_dir.glob(f"{info.get('id')}__*"), key=lambda p: p.stat().st_mtime)
        if not cands:
            raise SourceError(f"download finished but file missing for {url}")
        path = cands[-1]
    pi = probe(path)
    log.info("downloaded %s -> %s (%.0fs, %dx%d)", url, path.name, pi.duration_s, pi.width, pi.height)
    return SourceVideo(
        url=url, title=str(info.get("title") or ""), local_path=path, duration_s=pi.duration_s,
        creator=creator or str(info.get("uploader") or ""), license_note=license_note,
    )


def register_local(path: Path, title: str = "", creator: str = "", license_note: str = "") -> SourceVideo:
    """Register a local capture (your own PS5/Xbox footage via capture card or Share)."""
    if not path.exists():
        raise SourceError(f"{path} does not exist")
    pi = probe(path)
    return SourceVideo(url=path.resolve().as_uri(), title=title or path.stem, local_path=path,
                       duration_s=pi.duration_s, creator=creator, license_note=license_note or "own footage")
