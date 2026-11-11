# klip

Turns a stream VOD into vertical clips with captions and posts them.

**Start here: [PLAYBOOK.md](PLAYBOOK.md)**

## Install (Windows, PowerShell 7)

```powershell
git clone https://github.com/avanishkasar/klip.git C:\dev\klip; Set-Location C:\dev\klip; .\scripts\setup.ps1
```

## Make clips

```powershell
.\scripts\first-clip.ps1 -Url <vod-url> -Start 5400 -End 6300 -Top 3 -Layout split
```

## Commands

| command | does |
|---|---|
| `clipengine doctor` | checks your setup |
| `clipengine ingest` | downloads part of a VOD |
| `clipengine detect` | finds the best moments |
| `clipengine render` | makes the 9:16 clip (`crop`, `stack`, `blur`, `split`) |
| `clipengine publish` | uploads it |
| `clipengine report` | views and money |

Full reference: [docs/REFERENCE.md](docs/REFERENCE.md)
