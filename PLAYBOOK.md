# GTA 6 Clipping Playbook — account creation to first payout

GTA 6 ships **Thursday 19 Nov 2026** on PS5 / Xbox Series X|S (no PC). You have ~8 days. The money window is the
first 2-3 weeks: every big streamer will run clipping campaigns, CPMs will be at their highest, and the algorithms
will boost anything tagged GTA 6. This file is the full operating system. Do it top to bottom.

---

## 0. Hard truths first (read before spending a rupee)

1. **"Make money at any cost" has one legal shape:** clip content you are *allowed* to clip (a campaign brief, written
   creator permission, or your own gameplay). Unauthorised re-uploads get DMCA'd, demonetised, and banned from Whop.
   The ledger stores a `license_note` for every source for this reason.
2. **Where the money actually is (India):**
   - **Whop Content Rewards / direct clipping deals**: the primary income. Median rate ~$1.00 per 1,000 verified views,
     range $0.50-$3.00, per-clip caps, payout only after the creator approves the clip. Paid to PayPal/bank.
   - **YouTube Shorts (YPP)**: needs 1,000 subs + 10M Shorts views in 90 days. India Shorts RPM is tiny
     (order of $0.01 per 1k). Treat as a long-term asset and as the *proof-of-views* platform for campaigns, not as week-1 income.
   - **Instagram**: ads on Reels need Creator/Pro account + eligibility; bonus programs are invite-only. Same role as YouTube.
   - **TikTok is banned in India.** Most campaigns are TikTok-heavy. You can still post via web from a foreign number /
     VPN, but it violates TikTok ToS and campaign fraud checks flag geo mismatches. Default plan: YouTube + Instagram
     campaigns, TikTok only via a legit partner abroad (see §7).
3. **Realistic numbers:** 3 clips/day x 20 days = 60 clips. A good clipper averages 20-50k views/clip on a hot topic,
   many get 2k. At $1/1k with a 50% approval rate: **$300-$1,500 in the first month** is a realistic target; $5k+ happens
   only with a hit clip or multiple accounts/platforms. Anyone promising more is selling a course.
4. **What this system cannot do for you:** create your social accounts (phone/ID verification), link your bank, or pass
   KYC. Those take you 60-90 minutes of clicking. Everything after that is automated.

---

## 1. Day-0 account checklist (do all of it today; ~90 min)

| # | Account | Exact steps | Why |
|---|---|---|---|
| 1 | **New Gmail** dedicated to the clipping brand (e.g. `gta6.<brand>@gmail.com`) | Google account -> enable 2FA -> recovery phone | Isolates YouTube quota, OAuth, PayPal notifications from your personal mail |
| 2 | **YouTube channel** (Brand channel under that Gmail) | youtube.com -> create channel -> name = brand -> handle -> upload 1080x1920 banner/avatar (Canva) -> Settings -> Channel -> **Feature eligibility: verify phone** (unlocks >15 min, custom thumbs) -> Advanced: "not made for kids" | Shorts upload target; views here are what you report to campaigns |
| 3 | **Google Cloud project** for the YouTube API | console.cloud.google.com -> New project `clipengine` -> APIs & Services -> Enable **YouTube Data API v3** -> OAuth consent screen: External, add your Gmail as test user, scopes `youtube.upload`, `youtube.readonly` -> Credentials -> **OAuth client ID: Desktop app** -> download JSON to `secrets\yt_client_secret.json` | `clipengine publish` uses it. Default quota 10,000 units/day = **6 uploads/day**; file the quota-increase form on day 1 (takes days) |
| 4 | **Instagram Creator account** | New IG account on the phone (S24) with brand name -> Settings -> Account type -> **Creator** -> category "Gamer" -> link to a **Facebook Page** you create (required for API) | Reels target + campaign proof |
| 5 | **Meta app for Reels API** | developers.facebook.com -> Create app -> type "Business" -> add product **Instagram** -> "API setup with Instagram login" -> add your IG account as tester -> generate token -> permissions `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_insights` -> exchange for **long-lived token (60 days)** -> put `CLIP_IG_USER_ID`, `CLIP_IG_ACCESS_TOKEN` in `.env` | 25 API publishes/day. Until the app is live you can publish only to tester accounts, which is you, so that is fine |
| 6 | **Cloudflare R2 bucket (public)** | dash.cloudflare.com -> R2 -> create bucket `clips-public` -> Settings -> Public access: allow / connect a custom domain -> install `rclone`, configure R2 remote | Instagram's API *pulls* the mp4 from a public URL. R2 has free egress. Set `CLIP_PUBLIC_MEDIA_DIR` to a local folder synced with `rclone sync` (see §5) and `CLIP_PUBLIC_MEDIA_BASE_URL` to the bucket URL |
| 7 | **Whop account** | whop.com -> sign up with the brand Gmail -> Settings -> Payouts -> add **PayPal** (and bank if offered for India) -> browse **Content Rewards** -> filter "Gaming" | Where campaigns are posted and where approvals/payouts happen |
| 8 | **PayPal Business (India)** | paypal.com/in -> Business account -> PAN mandatory -> add **Indian bank account** (IFSC) -> purpose code "P1007/P0802"-type freelance services when asked -> verify email + phone | Whop and most creators pay USD via PayPal. PayPal India **auto-withdraws to your bank in INR within 1 business day**, you cannot hold a balance. Keep the FIRC-style statements for tax |
| 9 | **PayPal Developer app** | developer.paypal.com -> Apps & Credentials -> **Live** -> Create app `clipengine` -> Features: tick **Transaction Search** -> copy client id/secret to `.env` (`CLIP_PAYPAL_CLIENT_ID/SECRET`, `CLIP_PAYPAL_ENV=live`) | `clipengine sync-paypal` pulls every incoming credit into the ledger. Transaction Search can take up to 9h to activate |
| 10 | **Wise (optional, recommended)** | wise.com -> personal -> get USD account details | Direct deals with creators: Wise USD->INR is ~1% vs PayPal's ~4%+ spread. Offer Wise first, PayPal second |
| 11 | **Anthropic API key** | console.anthropic.com -> API keys -> put in `ANTHROPIC_API_KEY` -> set a $20 monthly limit | Moment ranking + packaging. Cost per clip at `medium` effort is cents |
| 12 | **Capture (if you play yourself)** | PS5 Share -> auto-capture + "Save recent gameplay" 1080p; move via USB or PS App; or Elgato HD60 X -> OBS | Own footage = zero licensing risk, highest campaign-independent upside |

**Do not** buy followers, use engagement pods, or run multiple accounts from one device/IP. Whop campaigns verify views and clawback.

---

## 2. Software setup (one shot)

```powershell

git clone https://github.com/avanishkasar/klip.git C:\dev\klip; Set-Location C:\dev\klip
.\scripts\setup.ps1
```

Then fill `.env` (copied from `.env.example`). Minimum to produce clips: `ANTHROPIC_API_KEY`. Minimum to publish:
`secrets\yt_client_secret.json` and the Instagram vars. Run `clipengine doctor` until everything you need is `OK`.

GPU: faster-whisper runs on the 4070 (`CLIP_WHISPER_DEVICE=cuda`, `float16`). If CUDA libs are missing it falls back to
CPU/int8 automatically; `small` model on CPU is still ~2x realtime for a 30s clip.

---

## 3. Finding campaigns (daily, 10 minutes)

1. Whop -> Content Rewards -> sort by **"Newest"** and **"Highest rate"**. Filter: Gaming, platforms you have.
2. For each campaign read the brief and record it **verbatim** in the ledger. The `--requirements` string is what Claude
   is forced to satisfy (credit handle, required text, no-go content):
   ```powershell
   clipengine campaign add "kai gta6 launch" --rate 1.50 --max-per-clip 750 --min-views 1000 `
     --platforms youtube,instagram --requirements "Caption must include @kaicenat and 'Clipped from Kai's stream'. No edited audio. 15-60s." `
     --url https://whop.com/...
   ```
3. Join the campaign in Whop, grab the **VOD link they allow** (usually the creator's Twitch/YouTube VODs or a Drive folder).
4. Prefer campaigns with: budget > $5k left, rate >= $1, cap >= $300, YouTube+IG allowed, fast approval history (check the Whop chat).
5. Direct deals: DM 10 mid-size GTA creators (50k-500k) on day 1 with: "I run a clipping pipeline, 3 clips/day, I credit
   you, $1 per 1k views on YouTube Shorts/IG, I send you the links + analytics weekly, paid via Wise/PayPal." Two yeses
   = a campaign nobody else is in.

---

## 4. Producing clips (the loop)

**Never download whole VODs.** Watch the stream live (or scrub the VOD), note timestamps of 2-4 moments, then pull only
those sections:

```powershell
.\scripts\first-clip.ps1 -Url https://www.twitch.tv/videos/123456789 -Start 5400 -End 6300 `
  -Creator "@kaicenat" -Brief "https://whop.com/..." -CampaignId 1 -Top 3 -Layout stack -Cam "1420:0:500:280"
```

What happens:
1. `ingest` downloads 5400-6300s only (yt-dlp section download, keyframe-accurate).
2. `detect` scores every second (loudness z-score 70% + scene-change density 30%), opens windows 4s before each peak,
   transcribes with Whisper, and asks Claude to fix boundaries and rank by rewatch potential.
3. `render` per clip: raw cut -> transcription -> Claude writes **hook / title / caption / hashtags** satisfying the
   campaign requirements -> final NVENC render at 1080x1920, 30fps, -14 LUFS, burned karaoke captions + 2s hook.
4. `publish` uploads to YouTube (public, Gaming category, `#Shorts`), publishes the Reel via Graph API, writes a
   `.tiktok.txt` sidecar for manual TikTok posting.

Layouts: `crop` (center 9:16; GTA action is centered, best default), `stack` (facecam top 32%, gameplay bottom; give
the webcam box in source pixels once per creator), `blur` (full frame on blurred background when the crop loses context).

### Split-screen mode (clip on top, filler gameplay below)

Drop one or more long filler videos (Subway Surfers, parkour, satisfying loops) into `workspace\filler\`, then:

```powershell
.\scripts\first-clip.ps1 -Url <vod> -Start 5400 -End 6300 -Top 3 -Layout split
```

Each render picks a random filler file and a random start offset, mutes it, loops it if it is shorter than the clip,
and puts the captions on the seam. Use `-Filler C:\path\file.mp4` to force a specific one.

Risk you are accepting when clipping without a brief or permission: filler does not defeat audio/video content
matching, takedowns and strikes land on the account (three strikes ends a YouTube channel), YouTube's reused-content
policy blocks monetisation review, and campaigns pay nothing for unapproved clips. Run this mode on accounts you can
afford to lose and keep campaign work on a separate, clean account.

Manual quality gate (30 seconds per clip, do not skip): open the mp4, check the first 1.5s hooks, captions are right,
nothing in the brief is violated. If it is bad, `clipengine render <id> --hook "better hook"` or just do not publish it.

Reels API note: before publishing, sync the public folder:
```powershell
rclone sync "$env:CLIP_PUBLIC_MEDIA_DIR" r2:clips-public --fast-list
```
(`first-clip.ps1` can be extended with that line before `publish`; it is left explicit so you see the egress.)

---

## 5. Posting cadence that the algorithms reward

- 3-5 clips/day per platform, spaced >= 2h apart, between 17:00-23:00 IST **and** 20:00-02:00 ET for US campaigns
  (schedule the US slots with YouTube's built-in scheduler: `--privacy private` then schedule in Studio, or just post late).
- First 3 days: post the *same* best clip to both platforms; afterwards vary the hook per platform.
- Titles: what happens, present tense, <= 60 chars. Hook on screen <= 8 words. No clickbait that the clip does not pay off;
  retention is the ranking signal and a lie kills it.
- Reply to the first 10 comments within an hour. Pin a comment with the creator credit and campaign link if allowed.
- Submit each published URL to the Whop campaign **immediately**; approvals are first-come on budget.

---

## 6. Money tracking (automated)

```powershell
clipengine sync-views      # YouTube + IG view counts -> ledger
clipengine sync-paypal     # incoming PayPal credits -> ledger (idempotent)
clipengine import-whop .\exports\whop-payouts.csv --campaign-id 1
clipengine report          # expected (views x rate, capped) vs received
.\scripts\register-daily-task.ps1   # runs daily.ps1 at 09:00 via Task Scheduler
```

Reconcile weekly: `expected` per campaign vs `payouts`. If a campaign is >14 days behind on approved clips, stop
feeding it and post in its Whop chat with the clip list from `report`.

### Banking / tax (India)
- Income is "profits and gains from business/profession". File ITR-3 or ITR-4 (presumptive 44ADA is usually the
  simplest below Rs 75L: declare 50% as profit). Keep PayPal statements; they carry the remittance details.
- GST: export of services is zero-rated, but registration becomes mandatory above Rs 20L turnover; below that stay out.
- PayPal India fees ~4.4% + fixed + currency spread. Wise is cheaper for direct deals. Whop charges ~7% on clipper payouts.
- Never route money through a friend's account abroad "to avoid fees": FEMA violation, and campaigns pay to the verified name.

---

## 7. TikTok (India reality)
- Option A (clean): skip it. Many GTA 6 campaigns allow YouTube+IG; take only those.
- Option B (clean): partner with one person outside India (friend/relative) who owns the TikTok account; you deliver
  rendered mp4 + `.tiktok.txt`, they post, you split 70/30. Record their posts with `clipengine mark-posted <clip> tiktok <url>`.
- Option C (ToS-violating, not recommended): VPN + foreign SIM. Campaign fraud checks look at geo mismatches and you lose
  the payout and the account. Not worth it for $1 CPMs.
- TikTok Direct Post API is implemented (`CLIP_TIKTOK_MODE=api`) for the day you have an audited app; unaudited apps can only post private.

---

## 8. Launch-week schedule (19-26 Nov)

| when | do |
|---|---|
| **Now -> 18 Nov** | All of §1 done; `doctor` green; test the full loop on any GTA 5 stream with a public-domain or permitted VOD; request YouTube quota increase; message 10 creators (§3.5); join 3-5 Whop campaigns; preload the game if you bought it |
| **19 Nov 00:00 ET** | Campaigns go live within hours; watch the top 3 streamers in your campaigns with timestamps in a notepad; first clips out within 60 minutes of a moment |
| **19-21 Nov** | 5+ clips/day/platform; everything is "first time seeing X"; submit URLs instantly |
| **22-26 Nov** | Shift to "best of", fails, hidden details, NPC dialogue; keep 3-5/day; start the weekly reconcile |
| **Dec** | Kill campaigns that do not pay; double down on the two that do; long-form compilations (8-10 min) for YPP watch hours |

---

## 9. Daily operating checklist (20-40 min of human time)

1. `clipengine campaign list` -> check Whop for new briefs (10 min).
2. Note 3-6 timestamps from live streams / VODs you are allowed to clip.
3. Run `first-clip.ps1` per VOD section (machine time, not yours).
4. 30s QA per clip, publish, submit URLs to campaigns.
5. `daily.ps1` runs at 09:00: views + PayPal synced, report printed. Glance at it.
6. Weekly: reconcile, DM 5 new creators, prune.

---

## 10. Using Claude to run this

Everything in `clipengine` is a CLI, so you can drive it from Claude Code on your PC. Useful prompts:
- "Read PLAYBOOK §3, here is the Whop brief text: <paste>. Add the campaign with the exact requirements string."
- "Run first-clip.ps1 for this VOD at these timestamps, then show me the titles and hooks for approval."
- "Run `clipengine report`, compare with last week's, tell me which campaign to drop."
- "Here are my PayPal CSV exports; import them and reconcile against expected payouts."

Scope rule for autonomous runs: Claude may ingest/detect/render freely; **you** approve before `publish` for the first
20 clips, then let `first-clip.ps1` publish directly once your QA pass rate is > 90%.
