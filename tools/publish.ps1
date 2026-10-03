$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:GH_CONFIG_DIR = Join-Path (Get-Location) '.local/github'
$taskAccount = gh api user --jq .login
if ($LASTEXITCODE -ne 0 -or $taskAccount -ne 'adsuhi283dm9a8znlkxc') { throw 'The dedicated GitHub account is not authenticated.' }
python tools/security_check.py --working
if ($LASTEXITCODE -ne 0) { throw 'Security check failed.' }
git add -- docs tools .githooks .gitignore README.md requirements.txt 'Export Wiki.cmd' 'Publish Wiki.cmd'
if ($LASTEXITCODE -ne 0) { throw 'Staging failed.' }
git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git commit -m 'Update checked static wiki export'
    if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
}
git push origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed.' }
