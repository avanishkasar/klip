#Requires -Version 7
<#
.SYNOPSIS  End-to-end: ingest a VOD section -> detect -> render top N -> publish. Idempotent per source URL.
.EXAMPLE   .\scripts\first-clip.ps1 -Url https://www.twitch.tv/videos/123 -Start 3600 -End 5400 -Creator "@kaicenat" -Brief "https://whop.com/..." -CampaignId 1 -Top 3
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Url,
  [int]$Start = -1,
  [int]$End = -1,
  [string]$Creator = '',
  [string]$Brief = '',
  [int]$CampaignId = 0,
  [int]$Top = 3,
  [int]$Length = 30,
  [ValidateSet('crop','stack','blur')][string]$Layout = 'crop',
  [string]$Cam = '',
  [string]$Platforms = 'youtube,instagram,tiktok',
  [switch]$NoPublish
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\Activate.ps1

$ingest = @('ingest', $Url, '--creator', $Creator, '--license-note', $Brief)
if ($Start -ge 0 -and $End -gt $Start) { $ingest += @('--start', $Start, '--end', $End) }
$out = clipengine @ingest 2>&1 | Tee-Object -Variable ingestLog
$sourceId = [int](($ingestLog | Select-String -Pattern 'source #(\d+)').Matches[0].Groups[1].Value)

$detect = @('detect', $sourceId, '--length', $Length, '--max-clips', $Top)
if ($CampaignId -gt 0) { $detect += @('--campaign-id', $CampaignId) }
$detectLog = clipengine @detect 2>&1 | Tee-Object -Variable detectLog
$clipIds = ($detectLog | Select-String -Pattern 'clip #(\d+)' -AllMatches).Matches | ForEach-Object { [int]$_.Groups[1].Value }

foreach ($id in ($clipIds | Select-Object -First $Top)) {
  $render = @('render', $id, '--layout', $Layout)
  if ($Cam) { $render += @('--cam', $Cam) }
  clipengine @render
  if (-not $NoPublish) { clipengine publish $id --platforms $Platforms }
}
clipengine report
