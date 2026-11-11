#Requires -Version 7
<#
.SYNOPSIS  One-shot setup on Windows 11 (PowerShell 7). Run from the repo root:  .\scripts\setup.ps1
#>
[CmdletBinding()]
param([switch]$SkipWinget)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

function Test-Cmd([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

if (-not $SkipWinget) {
  if (-not (Test-Cmd 'ffmpeg')) { winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements }
  if (-not (Test-Cmd 'python')) { winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements }
  if (-not (Test-Cmd 'git'))    { winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements }
  # refresh PATH for this session
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}

if (-not (Test-Path '.venv')) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[all]"
# CUDA wheels for faster-whisper on the 4070 (ctranslate2 needs cuBLAS/cuDNN); falls back to CPU automatically if absent
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12

New-Item -ItemType Directory -Force -Path secrets, workspace\sources, workspace\clips, workspace\renders, workspace\logs | Out-Null
if (-not (Test-Path '.env')) { Copy-Item .env.example .env; Write-Host "Created .env -> fill ANTHROPIC_API_KEY and platform creds" -ForegroundColor Yellow }

clipengine doctor
Write-Host "`nSetup done. Next: notepad .env ; then .\scripts\first-clip.ps1 -Url <vod> -Start 3600 -End 4200 -Creator @handle -Brief <campaign url>" -ForegroundColor Green
