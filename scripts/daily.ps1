#Requires -Version 7
<# Daily money loop: sync views + PayPal, print report. Schedule with Task Scheduler (see PLAYBOOK §9). #>
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\Activate.ps1
clipengine sync-views
clipengine sync-paypal --days 7
clipengine report
