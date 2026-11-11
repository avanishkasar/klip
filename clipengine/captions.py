"""Word-level transcription (faster-whisper) and ASS subtitle generation for burned-in captions."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


def transcribe(path: Path, language: str | None = "en") -> list[Word]:
    try:
        from faster_whisper import WhisperModel  # lazy heavy import
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("faster-whisper not installed: pip install 'clipengine[captions]'") from e
    s = get_settings()
    device = s.clip_whisper_device
    compute = s.clip_whisper_compute
    try:
        model = WhisperModel(s.clip_whisper_model, device=device, compute_type=compute)
    except Exception as e:  # CUDA missing / wrong compute type -> CPU fallback
        log.warning("whisper %s/%s failed (%s); falling back to cpu/int8", device, compute, e)
        model = WhisperModel(s.clip_whisper_model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), language=language, word_timestamps=True, vad_filter=True)
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(start=float(w.start), end=float(w.end), text=t))
    return words


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def group_words(words: list[Word], max_words: int = 3, max_gap_s: float = 0.6) -> list[list[Word]]:
    """Group into 1-3 word chunks (TikTok-style punchy captions)."""
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > max_gap_s):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(
    words: list[Word],
    hook_text: str | None,
    width: int = 1080,
    height: int = 1920,
    font: str = "Arial Black",
    caption_size: int = 72,
    hook_size: int = 80,
    hook_duration_s: float = 2.0,
) -> str:
    """ASS with: optional top hook for first N seconds + bottom-third pop captions, current word highlighted."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{caption_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{int(height*0.30)},1
Style: Hook,{font},{hook_size},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,8,60,60,{int(height*0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []
    if hook_text:
        lines.append(
            f"Dialogue: 1,{_ass_time(0)},{_ass_time(hook_duration_s)},Hook,,0,0,0,,"
            f"{{\\fad(80,150)}}{_esc(hook_text.upper())}"
        )
    for g in group_words(words):
        start, end = g[0].start, max(g[-1].end, g[0].start + 0.3)
        # karaoke-style: highlight word being spoken using \k (centiseconds)
        parts = []
        for w in g:
            dur_cs = max(1, int(round((w.end - w.start) * 100)))
            parts.append(f"{{\\k{dur_cs}}}{_esc(w.text.upper())}")
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{{\\fad(40,40)}}{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"
