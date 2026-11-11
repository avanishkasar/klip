"""Highlight detection.

Two signals, no ML dependency:
  1. Audio loudness peaks (ffmpeg ebur128 momentary loudness) -> shouting, explosions, chat-pop moments.
  2. Scene-change density (ffmpeg scene filter) -> action/cuts.
Fused into a per-second score; non-max-suppressed into windows of target length.
Pure scoring functions are separated from ffmpeg I/O so they are unit-testable.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .ffmpeg import ffmpeg, run
from .models import HighlightWindow

_LOUD = re.compile(r"t:\s*([0-9.]+)\s+.*?M:\s*(-?[0-9.]+|-inf)")
_SCENE = re.compile(r"pts_time:([0-9.]+)")


def analyze_loudness(path: Path, timeout_s: int = 1800) -> list[tuple[float, float]]:
    """Return [(t, momentary_lufs)] sampled ~10Hz."""
    cp = run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn",
              "-filter_complex", "ebur128=peak=none", "-f", "null", "-"], timeout_s=timeout_s)
    out: list[tuple[float, float]] = []
    for m in _LOUD.finditer(cp.stderr):
        t, lufs = m.group(1), m.group(2)
        out.append((float(t), -70.0 if lufs == "-inf" else float(lufs)))
    return out


def analyze_scenes(path: Path, threshold: float = 0.35, timeout_s: int = 1800) -> list[float]:
    """Return timestamps of scene changes above threshold."""
    cp = run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-an",
              "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"], timeout_s=timeout_s)
    return [float(x) for x in _SCENE.findall(cp.stderr)]


# ---------------- pure functions ----------------

def per_second_scores(
    loudness: list[tuple[float, float]],
    scenes: list[float],
    duration_s: float,
    loud_weight: float = 0.7,
    scene_weight: float = 0.3,
) -> list[float]:
    """Fuse loudness z-score (positive side) and scene density into a per-second score in [0, inf)."""
    n = max(1, int(math.ceil(duration_s)))
    loud = [0.0] * n
    cnt = [0] * n
    for t, l in loudness:
        i = int(t)
        if 0 <= i < n and l > -70:
            loud[i] += l
            cnt[i] += 1
    vals = [loud[i] / cnt[i] for i in range(n) if cnt[i]]
    if vals:
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / len(vals)
        sd = math.sqrt(var) or 1.0
    else:
        mu, sd = 0.0, 1.0
    loud_z = [max(0.0, (loud[i] / cnt[i] - mu) / sd) if cnt[i] else 0.0 for i in range(n)]

    scene_d = [0.0] * n
    for t in scenes:
        i = int(t)
        if 0 <= i < n:
            scene_d[i] += 1.0
    # smooth scene density over 3s
    sm = [0.0] * n
    for i in range(n):
        sm[i] = sum(scene_d[max(0, i - 1): i + 2]) / 3.0
    mx = max(sm) or 1.0
    scene_n = [v / mx for v in sm]
    return [loud_weight * loud_z[i] + scene_weight * scene_n[i] for i in range(n)]


def pick_windows(
    scores: list[float],
    target_len_s: int = 30,
    min_len_s: int = 12,
    max_windows: int = 8,
    pre_roll_s: int = 4,
) -> list[HighlightWindow]:
    """Peak-anchored non-max suppression: take the strongest untaken second as the payoff, open the window
    pre_roll_s before it (hook lands fast), clamp to bounds, and suppress overlaps. Window score = sum."""
    n = len(scores)
    if n == 0:
        return []
    L = min(max(target_len_s, min_len_s), n)
    taken = [False] * n
    out: list[HighlightWindow] = []
    while len(out) < max_windows:
        peak, peak_v = -1, 0.0
        for i, v in enumerate(scores):
            if not taken[i] and v > peak_v:
                peak, peak_v = i, v
        if peak < 0:
            break
        start = max(0, peak - pre_roll_s)
        end = min(n, start + L)
        start = max(0, end - L)
        # shrink if it collides with an already-taken window; drop if too short
        while start < end and any(taken[start:end]):
            if taken[start]:
                start += 1
            else:
                end -= 1
        if end - start < min_len_s:
            taken[peak] = True
            continue
        for k in range(start, end):
            taken[k] = True
        out.append(HighlightWindow(start_s=float(start), end_s=float(end), score=round(sum(scores[start:end]), 3),
                                   reason=f"peak@{peak}s"))
    return out


def detect(path: Path, duration_s: float, target_len_s: int = 30, max_windows: int = 8) -> list[HighlightWindow]:
    loud = analyze_loudness(path)
    scenes = analyze_scenes(path)
    scores = per_second_scores(loud, scenes, duration_s)
    return pick_windows(scores, target_len_s=target_len_s, max_windows=max_windows)
