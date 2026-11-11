# klip — GTA 6 clipping engine

Local, GPU-accelerated pipeline that turns a stream VOD or your own PS5/Xbox capture into packaged 9:16 clips and
pushes them to YouTube Shorts / Instagram Reels (API) and TikTok (manual sidecar), while a SQLite ledger tracks
campaigns, posts, views, expected payouts and money actually received (PayPal / Whop).

```
ingest  ->  detect (ffmpeg loudness+scene, whisper, Claude)  ->  render (9:16, captions, hook)  ->  publish  ->  sync-views / sync-paypal  ->  report
```

**Start here: [`PLAYBOOK.md`](PLAYBOOK.md)** — accounts, payments, India specifics, launch-week schedule, and the hard truths.

## Quick start (Windows 11, PowerShell 7)

```powershell
git clone https://github.com/avanishkasar/klip.git C:\dev\klip; Set-Location C:\dev\klip
.\scripts\setup.ps1            # winget ffmpeg/python, venv, deps, .env, doctor
notepad .env                   # ANTHROPIC_API_KEY + platform creds (see PLAYBOOK §2-§4)
clipengine doctor
clipengine campaign add "example gta6 campaign" --rate 1.25 --max-per-clip 500 --requirements "credit @creator in caption" --url https://whop.com/...
.\scripts\first-clip.ps1 -Url https://www.twitch.tv/videos/123456 -Start 3600 -End 5400 -Creator "@creator" -Brief "https://whop.com/..." -CampaignId 1 -Top 3
clipengine report
```

## Commands

| command | what it does |
|---|---|
| `doctor` | checks ffmpeg, NVENC, Claude key, platform creds |
| `campaign add/list` | paid campaign terms (rate per 1k, cap, min views, required credit text) |
| `ingest <url\|path> [--start --end]` | yt-dlp section download (never the whole 6h VOD) or register local capture |
| `detect <source_id>` | audio peaks + scene density -> candidate windows; Claude refines using the transcript |
| `render <clip_id> [--layout crop\|stack\|blur\|split] [--cam x:y:w:h] [--filler path]` | NVENC/x264 9:16 render, loudnorm, burned captions + hook; Claude writes title/caption/hashtags |
| `publish <clip_id>` | YouTube Data API resumable upload, Instagram Reels Graph API, TikTok sidecar/API |
| `mark-posted` | record a manual upload |
| `sync-views` | pull views from YouTube + Instagram |
| `sync-paypal` | import incoming PayPal transactions (Transaction Search API) |
| `import-whop <csv>` | import Whop payout export |
| `report` | money view: expected (views x rate) vs received |

## Design notes

- Highlight detection is deterministic (ffmpeg `ebur128` + `scene`), then Claude re-ranks using what was said. If the
  Claude call fails or is refused, the pipeline falls back to the audio windows instead of stopping.
- All platform calls have timeouts, bounded retries, and idempotent ledger writes (`UNIQUE(clip_id, platform)`,
  `UNIQUE(provider, txn_id)`); views never regress.
- NVENC is tried first; on a runtime failure (no driver) it falls back to libx264 once and remembers.
- Secrets live only in `.env` / `secrets/`, both git-ignored.

## Tests

```powershell
python -m pytest -q
```
