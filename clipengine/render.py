"""Render a 9:16 vertical clip with ffmpeg.

Layouts:
  - "crop":   center-crop the gameplay to 9:16 (fastest, default for GTA where action is centered)
  - "stack":  facecam region on top, gameplay below (give --cam x:y:w:h of the webcam box in source pixels)
  - "blur":   gameplay fitted on a blurred, zoomed copy of itself (safe when cropping kills context)
  - "split":  main clip on top, a muted looping filler video (e.g. Subway Surfers / parkour) on the bottom;
              filler is a second input, started at a random offset so no two clips look identical
Captions are burned in from an ASS file. NVENC used when available (your 4070), x264 fallback.
"""
from __future__ import annotations

import logging
import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .ffmpeg import FFmpegError, ffmpeg, probe, run

log = logging.getLogger(__name__)
Layout = Literal["crop", "stack", "blur", "split"]
SPLIT_TOP_RATIO = 0.55  # share of the frame given to the main clip in split layout
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm"}


@dataclass(frozen=True)
class CamBox:
    x: int
    y: int
    w: int
    h: int

    @classmethod
    def parse(cls, s: str) -> CamBox:
        x, y, w, h = (int(v) for v in s.split(":"))
        if w <= 0 or h <= 0:
            raise ValueError("cam box w/h must be > 0")
        return cls(x, y, w, h)


def _has_nvenc() -> bool:
    try:
        cp = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30)
        return "h264_nvenc" in cp.stdout
    except Exception:
        return False


_NVENC_OK: bool | None = None  # None = untested; set False after a runtime failure (no driver/GPU)


def _video_codec_args(force_cpu: bool = False) -> list[str]:
    if not force_cpu and _NVENC_OK is not False and _has_nvenc():
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-maxrate", "14M",
                "-bufsize", "28M", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p"]


def _escape_filter_path(p: Path) -> str:
    # ffmpeg filter arg escaping (Windows drive colon + backslashes)
    s = str(p.resolve()).replace("\\", "/").replace(":", "\\:")
    return s.replace("'", "\\'")


def build_filter(layout: Layout, src_w: int, src_h: int, cam: CamBox | None, ass_path: Path | None,
                 out_w: int = 1080, out_h: int = 1920) -> str:
    """Return a -filter_complex graph producing [vout]. Pure function (testable)."""
    if layout == "crop":
        crop_w = int(src_h * out_w / out_h)
        chain = (f"[0:v]crop={crop_w}:{src_h}:(iw-{crop_w})/2:0,scale={out_w}:{out_h}:flags=lanczos,"
                 f"setsar=1[base]")
    elif layout == "blur":
        chain = (f"[0:v]split=2[bg][fg];"
                 f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},"
                 f"boxblur=30:5,eq=brightness=-0.15[bgb];"
                 f"[fg]scale={out_w}:-2:flags=lanczos[fgs];"
                 f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    elif layout == "stack":
        if cam is None:
            raise ValueError("stack layout requires a cam box")
        cam_h = int(out_h * 0.32)
        game_h = out_h - cam_h
        crop_w = int(src_h * out_w / game_h)
        chain = (f"[0:v]split=2[c][g];"
                 f"[c]crop={cam.w}:{cam.h}:{cam.x}:{cam.y},scale={out_w}:{cam_h}:force_original_aspect_ratio=increase,"
                 f"crop={out_w}:{cam_h}[cam];"
                 f"[g]crop={min(crop_w, src_w)}:{src_h}:(iw-{min(crop_w, src_w)})/2:0,scale={out_w}:{game_h}:flags=lanczos[game];"
                 f"[cam][game]vstack=inputs=2,setsar=1[base]")
    elif layout == "split":
        top_h = int(out_h * SPLIT_TOP_RATIO) // 2 * 2
        bot_h = out_h - top_h
        chain = (f"[0:v]scale={out_w}:{top_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                 f"crop={out_w}:{top_h}[top];"
                 f"[1:v]scale={out_w}:{bot_h}:force_original_aspect_ratio=increase,crop={out_w}:{bot_h},"
                 f"fps=30,setpts=PTS-STARTPTS[bot];"
                 f"[top][bot]vstack=inputs=2,setsar=1[base]")
    else:  # pragma: no cover
        raise ValueError(f"unknown layout {layout}")
    if ass_path:
        return chain + f";[base]ass='{_escape_filter_path(ass_path)}'[vout]"
    return chain + ";[base]null[vout]"


def pick_filler(filler_dir: Path, rng: random.Random | None = None) -> Path:
    """Pick a random filler video from a directory."""
    files = sorted(f for f in filler_dir.glob("*") if f.suffix.lower() in VIDEO_EXTS) if filler_dir.is_dir() else []
    if not files:
        raise FileNotFoundError(f"no filler videos in {filler_dir} (drop .mp4 files there or pass --filler)")
    return (rng or random).choice(files)


def render_clip(
    src: Path,
    start_s: float,
    end_s: float,
    out: Path,
    layout: Layout = "crop",
    cam: CamBox | None = None,
    ass_path: Path | None = None,
    loudnorm: bool = True,
    timeout_s: int = 1200,
    filler: Path | None = None,
) -> Path:
    if end_s <= start_s:
        raise ValueError("end_s must be > start_s")
    if not src.exists():
        raise FileNotFoundError(src)
    pi = probe(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.mp4")
    graph = build_filter(layout, pi.width, pi.height, cam, ass_path)
    dur = end_s - start_s
    args = [ffmpeg(), "-hide_banner", "-y", "-nostdin",
            "-ss", f"{start_s:.3f}", "-to", f"{end_s:.3f}", "-i", str(src)]
    if layout == "split":
        if filler is None or not filler.exists():
            raise FileNotFoundError("split layout requires an existing filler video")
        f_dur = probe(filler).duration_s
        offset = random.uniform(0.0, max(0.0, f_dur - dur - 1.0)) if f_dur > dur + 1.0 else 0.0
        args += ["-stream_loop", "-1", "-ss", f"{offset:.3f}", "-i", str(filler)]
    args += ["-filter_complex", graph, "-map", "[vout]", "-t", f"{dur:.3f}"]
    if pi.has_audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        if loudnorm:
            args += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    tail = ["-r", "30", "-g", "60", "-movflags", "+faststart", str(tmp)]
    global _NVENC_OK
    try:
        try:
            run(args + _video_codec_args() + tail, timeout_s=timeout_s)
        except FFmpegError as e:
            msg = str(e)
            if _NVENC_OK is not False and ("nvenc" in msg.lower() or "libcuda" in msg.lower()):
                log.warning("NVENC unavailable at runtime (%s); falling back to libx264", msg.splitlines()[-1][:120])
                _NVENC_OK = False
                run(args + _video_codec_args(force_cpu=True) + tail, timeout_s=timeout_s)
            else:
                raise
        else:
            if _NVENC_OK is None:
                _NVENC_OK = True
        shutil.move(str(tmp), str(out))
    finally:
        tmp.unlink(missing_ok=True)
    log.info("rendered %s [%.1f-%.1f] -> %s", src.name, start_s, end_s, out)
    return out
