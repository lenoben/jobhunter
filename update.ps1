# Started by update.bat (double-click). Gets the newest JobHunter and installs it again (user request
# 2026-11-20): with git if this folder is a git copy, otherwise by downloading the ZIP from GitHub, so
# people without git can update too. Never touches .env, profile\, data\, output\ or logs\.
# Keep this file ASCII and Windows PowerShell 5.1 compatible (see install.ps1).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$Repo = 'lenoben/jobhunter'
$Branch = 'main'

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

try {
    # A running JobHunter keeps files open, and would keep showing the old version.
    $open = $null
    try { $open = Get-NetTCPConnection -LocalPort 5790 -State Listen -ErrorAction Stop } catch {}
    if ($open) { throw 'JobHunter is still open. Close its window (the one run.bat opened), then run update.bat again.' }

    Say 'Getting the newest version'
    if ((Test-Path (Join-Path $PSScriptRoot '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        git pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw 'git pull did not finish (changed files in this folder?). Run "git status" to see why.' }
    }
    else {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $tmp = Join-Path $env:TEMP ("jobhunter-update-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        try {
            $zip = Join-Path $tmp 'jobhunter.zip'
            Write-Host "Downloading https://github.com/$Repo ..."
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
            # .NET directly: Expand-Archive breaks when PowerShell 7's module path leaks into 5.1
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [IO.Compression.ZipFile]::ExtractToDirectory($zip, (Join-Path $tmp 'src'))
            $src = Get-ChildItem -Path (Join-Path $tmp 'src') -Directory | Select-Object -First 1
            if (-not $src -or -not (Test-Path (Join-Path $src.FullName 'install.ps1'))) { throw 'The download does not look like JobHunter.' }
            # Copy over this folder. The ZIP has no personal files (they are not in the repository);
            # the exclusions are a second guard. Files removed upstream stay here; that is harmless.
            robocopy $src.FullName $PSScriptRoot /E /NFL /NDL /NJH /NJS /NP `
                /XD profile data output logs .venv node_modules build .svelte-kit .git /XF .env | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "Copying the new files failed (robocopy code $LASTEXITCODE). Is a file still open?" }
        }
        finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
    }
}
catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Nothing was installed. Your data is unchanged.'
    exit 1
}

# The new install.ps1: checks Python/Node versions, installs packages, updates the database, builds the UI.
& (Join-Path $PSScriptRoot 'install.ps1') -Update
exit $LASTEXITCODE
