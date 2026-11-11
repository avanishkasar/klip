from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import get_settings


class FFmpegError(RuntimeError):
    pass


def _bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FFmpegError(
            f"{name} not found on PATH. Install: winget install Gyan.FFmpeg  (then restart the terminal)"
        )
    return path


def run(args: list[str], timeout_s: int = 1800) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg/ffprobe with a hard timeout; raise with stderr tail on failure."""
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired as e:
        raise FFmpegError(f"timed out after {timeout_s}s: {' '.join(args[:6])}...") from e
    if cp.returncode != 0:
        raise FFmpegError(f"exit {cp.returncode}: {cp.stderr[-2000:]}")
    return cp


@dataclass(frozen=True)
class ProbeInfo:
    duration_s: float
    width: int
    height: int
    fps: float
    has_audio: bool


def probe(path: Path) -> ProbeInfo:
    s = get_settings()
    cp = run([_bin(s.clip_ffprobe_bin), "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams", str(path)], timeout_s=60)
    data = json.loads(cp.stdout)
    v = next((st for st in data["streams"] if st.get("codec_type") == "video"), None)
    if v is None:
        raise FFmpegError(f"no video stream in {path}")
    num, _, den = (v.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return ProbeInfo(
        duration_s=float(data["format"].get("duration", 0.0)),
        width=int(v["width"]), height=int(v["height"]), fps=fps,
        has_audio=any(st.get("codec_type") == "audio" for st in data["streams"]),
    )


def ffmpeg() -> str:
    return _bin(get_settings().clip_ffmpeg_bin)
