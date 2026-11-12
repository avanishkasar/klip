"""clipengine CLI. Run `clipengine --help`."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import captions as cap
from . import highlights, render, source
from .config import get_settings
from .db import Ledger
from .models import Campaign, Clip, ClipStatus, Platform, Post, PostStatus
from .payouts import paypal, whop

app = typer.Typer(no_args_is_help=True, help="GTA 6 clipping pipeline: source -> clips -> render -> publish -> ledger")
campaign_app = typer.Typer(no_args_is_help=True, help="Paid clipping campaigns")
app.add_typer(campaign_app, name="campaign")
con = Console()


def _ledger() -> Ledger:
    return Ledger(get_settings().clip_db_path)


@app.callback()
def _root(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    s = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(s.logs_dir / "clipengine.log", encoding="utf-8"), logging.StreamHandler()],
    )


@app.command()
def doctor() -> None:
    """Check ffmpeg, GPU encoder, Claude key, platform creds."""
    import shutil

    s = get_settings()
    rows = [
        ("ffmpeg", bool(shutil.which(s.clip_ffmpeg_bin))),
        ("ffprobe", bool(shutil.which(s.clip_ffprobe_bin))),
        ("nvenc (4070)", render._has_nvenc() if shutil.which(s.clip_ffmpeg_bin) else False),
        ("ANTHROPIC_API_KEY", bool(s.anthropic_api_key)),
        ("YouTube client secrets", s.clip_yt_client_secrets.exists()),
        ("Instagram token", bool(s.clip_ig_access_token and s.clip_ig_user_id)),
        ("Instagram public media URL", bool(s.clip_public_media_base_url)),
        ("TikTok mode", s.clip_tiktok_mode),
        ("PayPal creds", bool(s.clip_paypal_client_id and s.clip_paypal_client_secret)),
    ]
    t = Table("check", "status")
    for k, v in rows:
        t.add_row(k, ("[green]OK[/]" if v else "[red]MISSING[/]") if isinstance(v, bool) else str(v))
    con.print(t)


# ---------------- campaigns ----------------
@campaign_app.command("add")
def campaign_add(
    name: str,
    rate: str = typer.Option(..., help="USD per 1k views, e.g. 1.25"),
    max_per_clip: str | None = typer.Option(None, help="USD cap per clip"),
    min_views: int = typer.Option(0),
    source_kind: str = typer.Option("whop", "--source"),
    platforms: str = typer.Option("youtube,instagram", help="comma list: youtube,instagram,tiktok"),
    requirements: str = typer.Option("", help="Verbatim brief rules: credit handle, required text, no-go content"),
    url: str | None = typer.Option(None),
) -> None:
    c = Campaign(
        name=name, source=source_kind, rate_per_1k_views_usd=Decimal(rate),
        max_payout_per_clip_usd=Decimal(max_per_clip) if max_per_clip else None, min_views_for_payout=min_views,
        platforms=[Platform(p.strip()) for p in platforms.split(",") if p.strip()], requirements=requirements, url=url,
    )
    c = _ledger().add_campaign(c)
    con.print(f"campaign #{c.id} added: {c.name} @ ${c.rate_per_1k_views_usd}/1k")


@campaign_app.command("list")
def campaign_list() -> None:
    t = Table("id", "name", "source", "$/1k", "cap", "platforms")
    for c in _ledger().list_campaigns(active_only=False):
        t.add_row(str(c.id), c.name, c.source, str(c.rate_per_1k_views_usd),
                  str(c.max_payout_per_clip_usd or "-"), ",".join(p.value for p in c.platforms))
    con.print(t)


# ---------------- ingest ----------------
@app.command()
def ingest(
    url_or_path: str,
    start: int | None = typer.Option(None, help="Only download from this second (saves GBs on long VODs)"),
    end: int | None = typer.Option(None),
    creator: str = typer.Option("", help="Handle to credit"),
    license_note: str = typer.Option("", help="Why you may clip this: campaign URL / permission / own footage"),
) -> None:
    """Download a VOD (or a section) or register a local capture. Records it as a source."""
    p = Path(url_or_path)
    if p.exists():
        sv = source.register_local(p, creator=creator, license_note=license_note)
    else:
        section = (start, end) if start is not None and end is not None else None
        sv = source.download(url_or_path, section=section, creator=creator, license_note=license_note)
    sv = _ledger().upsert_source(sv)
    con.print(f"source #{sv.id}: {sv.title} ({sv.duration_s:.0f}s) -> {sv.local_path}")


# ---------------- detect ----------------
@app.command()
def detect(
    source_id: int,
    length: int = typer.Option(30, help="target clip length seconds"),
    max_clips: int = typer.Option(8),
    campaign_id: int | None = typer.Option(None),
    use_claude: bool = typer.Option(True, help="Refine windows with transcript + Claude"),
) -> None:
    """Find highlight windows and store them as candidate clips."""
    lg = _ledger()
    sv = lg.get_source(source_id)
    if not sv or not sv.local_path:
        raise typer.BadParameter(f"source {source_id} not found/downloaded")
    dur = sv.duration_s or 0.0
    wins = highlights.detect(sv.local_path, dur, target_len_s=length, max_windows=max_clips)
    con.print(f"audio/scene detector: {len(wins)} windows")
    if use_claude and get_settings().anthropic_api_key:
        try:
            from . import brain

            words = cap.transcribe(sv.local_path)
            wins = brain.refine_moments(words, wins, dur, target_len_s=length, max_picks=max_clips)
            con.print(f"claude-refined: {len(wins)} windows")
        except Exception as e:  # keep pipeline moving
            con.print(f"[yellow]claude refine skipped: {e}[/]")
    for w in wins:
        c = lg.add_clip(Clip(source_id=source_id, campaign_id=campaign_id, start_s=w.start_s, end_s=w.end_s,
                             score=w.score))
        con.print(f"  clip #{c.id}: {w.start_s:.0f}-{w.end_s:.0f}s score={w.score} {w.reason}")


# ---------------- render ----------------
@app.command("render")
def render_cmd(
    clip_id: int,
    layout: str = typer.Option("crop", help="crop | stack | blur | split"),
    filler: Optional[Path] = typer.Option(None, help="filler video for split (default: random from workspace/filler)"),
    cam: str | None = typer.Option(None, help="facecam box x:y:w:h in source px (for stack)"),
    captions: bool = typer.Option(True),
    hook: str | None = typer.Option(None, help="Override hook text"),
) -> None:
    """Cut, crop to 9:16, burn captions + hook, package metadata with Claude."""
    s = get_settings()
    lg = _ledger()
    c = lg.get_clip(clip_id)
    if not c:
        raise typer.BadParameter("clip not found")
    sv = lg.get_source(c.source_id)
    assert sv and sv.local_path
    camp = lg.get_campaign(c.campaign_id) if c.campaign_id else None
    out = s.renders_dir / f"clip{clip_id:05d}.mp4"
    tmp_cut = s.clips_dir / f"clip{clip_id:05d}_raw.mp4"
    # 1) raw cut (fast, for transcription)
    render.render_clip(sv.local_path, c.start_s, c.end_s, tmp_cut, layout="crop", loudnorm=False)
    words: list[cap.Word] = []
    if captions:
        try:
            words = cap.transcribe(tmp_cut)
        except Exception as e:
            con.print(f"[yellow]captions skipped: {e}[/]")
    # 2) metadata
    meta = None
    if s.anthropic_api_key:
        try:
            from . import brain

            meta = brain.package_clip(words, sv.creator, camp.requirements if camp else "", context=sv.title)
        except Exception as e:
            con.print(f"[yellow]claude packaging failed: {e}[/]")
    hook_text = hook or (meta.hook_text if meta else None)
    # 3) final render with captions
    ass_path = None
    if words or hook_text:
        ass_path = s.clips_dir / f"clip{clip_id:05d}.ass"
        # split: captions sit on the seam between the clip and the filler
        margin = (1 - render.SPLIT_TOP_RATIO) - 0.03 if layout == "split" else 0.30
        ass_path.write_text(cap.build_ass(words, hook_text, caption_margin_ratio=margin), encoding="utf-8")
    filler_path = None
    if layout == "split":
        filler_path = filler or render.pick_filler(s.filler_dir)
        con.print(f"filler: {filler_path.name}")
    render.render_clip(sv.local_path, c.start_s, c.end_s, out, layout=layout,  # type: ignore[arg-type]
                       cam=render.CamBox.parse(cam) if cam else None, ass_path=ass_path, filler=filler_path)
    tmp_cut.unlink(missing_ok=True)
    c = c.model_copy(update={"status": ClipStatus.RENDERED, "render_path": out, "meta": meta})
    lg.update_clip(c)
    con.print(f"rendered -> {out}")
    if meta:
        con.print(f"[bold]{meta.title}[/]\n{meta.caption}\n{' '.join(meta.hashtags)}")


# ---------------- publish ----------------
@app.command()
def publish(
    clip_id: int,
    platforms: str = typer.Option("youtube,instagram,tiktok"),
    privacy: str = typer.Option("public"),
) -> None:
    """Upload a rendered clip. TikTok defaults to manual sidecar (see PLAYBOOK)."""
    lg = _ledger()
    c = lg.get_clip(clip_id)
    if not c or not c.render_path or not c.render_path.exists():
        raise typer.BadParameter("clip not rendered")
    meta = c.meta
    title = meta.title if meta else f"GTA 6 clip #{clip_id}"
    caption = (f"{meta.caption}\n\n{' '.join(meta.hashtags)}" if meta else "#GTA6 #Shorts")
    tags = meta.hashtags if meta else ["#GTA6"]
    any_ok = False
    for p in [Platform(x.strip()) for x in platforms.split(",") if x.strip()]:
        post = Post(clip_id=clip_id, platform=p)
        try:
            if p is Platform.YOUTUBE:
                from .publish import youtube

                r = youtube.upload_short(c.render_path, title, caption, tags, privacy=privacy)
                post = post.model_copy(update={"status": PostStatus.PUBLISHED, "remote_id": r.remote_id, "url": r.url})
            elif p is Platform.INSTAGRAM:
                from .publish import instagram

                url = instagram.stage_public(c.render_path)
                r = instagram.publish_reel(url, caption)
                post = post.model_copy(update={"status": PostStatus.PUBLISHED, "remote_id": r.remote_id, "url": r.url})
            elif p is Platform.TIKTOK:
                from .publish import tiktok

                if get_settings().clip_tiktok_mode == "api":
                    r = tiktok.direct_post(c.render_path, f"{title} {' '.join(tags)}")
                    post = post.model_copy(update={"status": PostStatus.PUBLISHED, "remote_id": r.remote_id, "url": r.url})
                else:
                    side = tiktok.write_manual_sidecar(c.render_path, title, caption, tags)
                    post = post.model_copy(update={"status": PostStatus.MANUAL, "error": f"upload manually; metadata: {side}"})
            any_ok = True
        except Exception as e:
            post = post.model_copy(update={"status": PostStatus.FAILED, "error": str(e)[:500]})
            con.print(f"[red]{p.value}: {e}[/]")
        lg.upsert_post(post)
        con.print(f"{p.value}: {post.status.value} {post.url or ''}")
    if any_ok:
        lg.update_clip(c.model_copy(update={"status": ClipStatus.PUBLISHED}))


@app.command("mark-posted")
def mark_posted(clip_id: int, platform: str, url: str, remote_id: str | None = None) -> None:
    """Record a manual upload (TikTok / anything you posted by hand)."""
    lg = _ledger()
    lg.upsert_post(Post(clip_id=clip_id, platform=Platform(platform), status=PostStatus.PUBLISHED,
                        remote_id=remote_id or url.rstrip("/").split("/")[-1], url=url))
    con.print("recorded")


@app.command("sync-views")
def sync_views() -> None:
    """Pull view counts for published posts (YouTube + Instagram APIs)."""
    lg = _ledger()
    posts = [p for p in lg.list_posts(PostStatus.PUBLISHED) if p.remote_id]
    now = datetime.now(UTC)
    yt_ids = [p.remote_id for p in posts if p.platform is Platform.YOUTUBE and p.remote_id]
    ig_ids = [p.remote_id for p in posts if p.platform is Platform.INSTAGRAM and p.remote_id]
    views: dict[str, int] = {}
    if yt_ids:
        from .publish import youtube

        views.update(youtube.fetch_views(yt_ids))
    if ig_ids:
        from .publish import instagram

        views.update(instagram.fetch_views(ig_ids))
    for p in posts:
        if p.remote_id in views:
            lg.upsert_post(p.model_copy(update={"views": views[p.remote_id], "last_synced_at": now}))
    con.print(f"synced {len(views)} posts")


@app.command("sync-paypal")
def sync_paypal(days: int = typer.Option(31, max=31)) -> None:
    """Import incoming PayPal transactions into the payout ledger."""
    n = paypal.sync_incoming(_ledger(), days=days)
    con.print(f"{n} new PayPal credits recorded")


@app.command("import-whop")
def import_whop(csv_path: Path, campaign_id: int | None = None) -> None:
    n = whop.import_csv(_ledger(), csv_path, campaign_id)
    con.print(f"{n} Whop payouts imported")


@app.command()
def report() -> None:
    """Money view: views per campaign, expected vs received."""
    lg = _ledger()
    s = lg.summary()
    t = Table("metric", "value")
    for k, v in s.items():
        t.add_row(k, str(v))
    con.print(t)
    camps = {c.id: c for c in lg.list_campaigns(active_only=False)}
    clips = {c.id: c for c in lg.list_clips()}
    owed: dict[int, Decimal] = {}
    for p in lg.list_posts(PostStatus.PUBLISHED):
        c = clips.get(p.clip_id)
        if c and c.campaign_id in camps:
            owed[c.campaign_id] = owed.get(c.campaign_id, Decimal(0)) + whop.expected_payout_usd(p.views, camps[c.campaign_id])
    if owed:
        t2 = Table("campaign", "expected USD (from synced views)")
        for cid, amt in owed.items():
            t2.add_row(camps[cid].name, f"${amt}")
        con.print(t2)


if __name__ == "__main__":
    app()
