# Your steps

Status checked on 11 Nov 2026 from your Gmail and PayPal. GTA 6 launches 19 Nov.

## Already done

- [x] YouTube channel: [@ColdWindy](https://www.youtube.com/@ColdWindy)
- [x] Instagram account: `avanishhkasar`
- [x] Google Cloud account
- [x] PayPal account exists (but blocked, see step 2)
- [x] Code on GitHub: https://github.com/avanishkasar/klip

## To do, in order

### 1. Secure your Google account (5 min)
- [ ] Change your Google password (you pasted it in chat)
- [ ] Turn on 2-Step Verification

### 2. Fix PayPal (15 min) — you cannot get paid until this is done
PayPal blocked features in July and removed your bank in September (RBI rules).
- [ ] Log in at paypal.com -> complete **Verify your identity** (PAN)
- [ ] Wallet -> **Link a bank account** again

### 3. Install on your PC (10 min)
```powershell
git clone https://github.com/avanishkasar/klip.git C:\dev\klip; Set-Location C:\dev\klip; .\scripts\setup.ps1
```

### 4. Claude API key (3 min)
- [ ] console.anthropic.com -> API keys -> create key
- [ ] Paste into `C:\dev\klip\.env` as `ANTHROPIC_API_KEY=`

### 5. YouTube upload access (10 min)
- [ ] console.cloud.google.com -> new project -> enable **YouTube Data API v3**
- [ ] OAuth consent screen: External, add yourself as test user
- [ ] Credentials -> OAuth client ID -> **Desktop app** -> download JSON
- [ ] Save it as `C:\dev\klip\secrets\yt_client_secret.json`

### 6. Instagram (5 min)
- [ ] In the app: Settings -> Account type -> switch to **Creator**
- [ ] Post Reels by hand for now (the mp4 and caption are ready after each render)

### 7. Whop (5 min) — not signed up yet
- [ ] whop.com -> Sign in with Google -> Settings -> Payouts -> add PayPal

### 8. Add filler videos
- [ ] Put Subway Surfers / parkour videos in `C:\dev\klip\workspace\filler\`

### 9. Make your first clips
```powershell
.\scripts\first-clip.ps1 -Url <vod-url> -Start 5400 -End 6300 -Top 3 -Layout split -NoPublish
```
- [ ] Watch the 3 videos in `C:\dev\klip\workspace\renders\`
- [ ] Happy with them? Run again without `-NoPublish` to upload to YouTube

## Every day after that

1. Pick 3-6 timestamps from a stream.
2. Run the `first-clip.ps1` command.
3. Check each clip for 30 seconds, then post.
4. `clipengine report` shows views and money.

Details, rates, tax and API setup for Instagram/TikTok: [docs/REFERENCE.md](docs/REFERENCE.md)
