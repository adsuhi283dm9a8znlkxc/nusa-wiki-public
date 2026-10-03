$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python tools/export_wiki.py
if ($LASTEXITCODE -ne 0) { throw 'Export failed; nothing was published.' }
python tools/security_check.py --working
if ($LASTEXITCODE -ne 0) { throw 'Security check failed; nothing was published.' }
Write-Host 'Export checked. Review it locally before running Publish Wiki.cmd.'
