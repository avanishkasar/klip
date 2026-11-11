"""Claude integration: pick the best moments from a transcript + pack each clip (hook/title/caption/tags)."""
from __future__ import annotations

import logging
from collections.abc import Sequence

import anthropic
from pydantic import BaseModel, Field

from .captions import Word
from .config import get_settings
from .models import ClipMeta, HighlightWindow

log = logging.getLogger(__name__)

_SYSTEM = """You package GTA 6 gameplay moments into short vertical clips that get watched to the end.
Rules:
- Hook text is <= 8 words, no clickbait lies, no profanity in on-screen text.
- Titles state what happens; curiosity gap is fine, deception is not.
- Captions: 1-2 lines + a CTA to follow, then hashtags on a new line. Always include the campaign's required
  credit/handle verbatim if one is provided.
- Hashtags: 6-10, mix of #GTA6 #GTAVI #GrandTheftAuto6 plus 3-5 moment-specific tags. No banned/spam tags.
- Never claim the footage is yours if the creator is named; credit them.
Respond only via the structured schema."""


class _MomentPick(BaseModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    reason: str = Field(max_length=200)
    confidence: float = Field(ge=0, le=1)


class _MomentPicks(BaseModel):
    picks: list[_MomentPick] = Field(max_length=10)


class RefusedError(RuntimeError):
    pass


def _client() -> anthropic.Anthropic:
    s = get_settings()
    if not s.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=3, timeout=120.0)


def _transcript_text(words: Sequence[Word], step_s: float = 5.0) -> str:
    """Bucket words into [mm:ss] lines so Claude can cite timestamps."""
    if not words:
        return ""
    lines: list[str] = []
    bucket_start = int(words[0].start // step_s) * step_s
    cur: list[str] = []
    for w in words:
        b = int(w.start // step_s) * step_s
        if b != bucket_start:
            lines.append(f"[{int(bucket_start//60):02d}:{int(bucket_start%60):02d}] {' '.join(cur)}")
            bucket_start, cur = b, []
        cur.append(w.text)
    if cur:
        lines.append(f"[{int(bucket_start//60):02d}:{int(bucket_start%60):02d}] {' '.join(cur)}")
    return "\n".join(lines)


def refine_moments(
    words: Sequence[Word],
    audio_windows: Sequence[HighlightWindow],
    duration_s: float,
    target_len_s: int = 30,
    max_picks: int = 6,
) -> list[HighlightWindow]:
    """Ask Claude to confirm/adjust the audio-detected windows using what was said. Falls back to audio windows."""
    s = get_settings()
    client = _client()
    prompt = (
        f"Video duration: {duration_s:.0f}s. Target clip length: {target_len_s}s (12-45s allowed).\n"
        f"Audio/scene detector proposed these windows (start-end, score):\n"
        + "\n".join(f"- {w.start_s:.0f}-{w.end_s:.0f}s score={w.score} {w.reason}" for w in audio_windows)
        + "\n\nTranscript (5s buckets):\n" + _transcript_text(words)[:60000]
        + f"\n\nReturn up to {max_picks} non-overlapping moments ranked by how likely they are to be rewatched/"
          "shared. Prefer: reactions, fails, 'no way' moments, funny NPC lines, first-time reveals. "
          "Start 2-4s before the payoff. Use the detector windows as anchors but fix their boundaries."
    )
    try:
        resp = client.messages.parse(
            model=s.clip_claude_model,
            max_tokens=4000,
            system=_SYSTEM,
            output_config={"effort": s.clip_claude_effort},
            messages=[{"role": "user", "content": prompt}],
            output_format=_MomentPicks,
        )
    except anthropic.RateLimitError:
        log.warning("Claude rate limited; using audio windows")
        return list(audio_windows)
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s; using audio windows", e.status_code)
        return list(audio_windows)
    except anthropic.APIConnectionError as e:
        log.warning("Claude connection error %s; using audio windows", e)
        return list(audio_windows)
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        log.warning("Claude refused/empty; using audio windows")
        return list(audio_windows)
    out: list[HighlightWindow] = []
    for p in resp.parsed_output.picks:
        a, b = max(0.0, p.start_s), min(duration_s, p.end_s)
        if 8.0 <= b - a <= 60.0:
            out.append(HighlightWindow(start_s=a, end_s=b, score=round(p.confidence * 10, 3), reason=p.reason))
    return out or list(audio_windows)


def package_clip(
    words: Sequence[Word],
    creator: str,
    campaign_requirements: str,
    context: str = "",
) -> ClipMeta:
    s = get_settings()
    client = _client()
    prompt = (
        f"Creator to credit: {creator or 'none (own footage)'}\n"
        f"Campaign requirements (must satisfy verbatim): {campaign_requirements or 'none'}\n"
        f"Extra context: {context or 'none'}\n\n"
        f"What is said in the clip:\n{' '.join(w.text for w in words)[:4000] or '(no speech)'}\n\n"
        "Produce hook_text, title, caption, hashtags, why_it_works."
    )
    resp = client.messages.parse(
        model=s.clip_claude_model,
        max_tokens=2000,
        system=_SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
        output_format=ClipMeta,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RefusedError("Claude declined to package this clip")
    meta = resp.parsed_output
    meta.hashtags = [h if h.startswith("#") else f"#{h}" for h in meta.hashtags][:12]
    return meta
