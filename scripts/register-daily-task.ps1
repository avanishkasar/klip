#Requires -Version 7
<# Registers a Windows Task Scheduler job running scripts\daily.ps1 every day at 09:00. #>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$action = New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\daily.ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At 09:00
Register-ScheduledTask -TaskName 'ClipEngine Daily Sync' -Action $action -Trigger $trigger -Description 'Sync views + PayPal, print report' -Force | Out-Null
Write-Host "Registered 'ClipEngine Daily Sync' (09:00 daily)."
