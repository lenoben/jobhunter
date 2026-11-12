# Started by install.bat (double-click). Installs what JobHunter needs, builds the web UI and
# starts it on the setup page (/setup), where the user enters accounts and keys. Safe to run again: finished parts are skipped or kept.
# Keep this file ASCII: Windows PowerShell 5.1 reads a script without a BOM as ANSI.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
    # Programs installed a moment ago are not on this window's PATH yet.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User') + ";$env:USERPROFILE\.local\bin"
}
function Node-Ok {
    # Vite and better-sqlite3 need Node 22.12+ (older Node: npm install or the build fails).
    if (-not (Has npm)) { return $false }
    $v = [version]((node -v) -replace '^v', '')
    return $v -ge [version]'22.12.0'
}
function Run($what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what did not finish." }
}

try {
    Say '1/6  Tools'
    if (-not (Has uv)) {
        Write-Host 'Installing uv (it installs Python for JobHunter) ...'
        Run 'Installing uv' { powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex' }
        Refresh-Path
        if (-not (Has uv)) { throw 'uv is installed, but this window cannot see it yet.' }
    }
    else {
        # An old uv cannot read a newer uv.lock. Only works for the standalone install; failure is fine.
        try { uv self update 2>&1 | Out-Null } catch {}
    }
    if (-not (Node-Ok)) {
        $found = if (Has node) { "Node.js $(node -v) is too old" } else { 'Node.js is missing' }
        if (-not (Has winget)) { throw "$found. Install the LTS version (22 or newer) from https://nodejs.org first." }
        Write-Host "$found; installing the current LTS version (Windows may ask for your permission) ..."
        # install also upgrades an older LTS from winget; exit code is non-zero when nothing changed, so check the version instead
        winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
        Refresh-Path
        if (-not (Node-Ok)) {
            $now = if (Has node) { "node -v says $(node -v)" } else { 'node is not found' }
            throw "JobHunter needs Node.js 22.12 or newer, but $now. Uninstall the old Node.js (Settings > Apps) or install the LTS from https://nodejs.org, then run install.bat again."
        }
    }
    Write-Host 'uv and Node.js are ready.'
    if (-not (Has claude)) {
        Write-Host 'Claude Code is not installed. That is fine with another AI provider (for example a free'
        Write-Host 'Google Gemini key). To use Claude Code, install it from https://claude.com/claude-code ,'
        Write-Host 'run "claude" once to log in, then double-click install.bat again.'
    }

    Say '2/6  Python packages (a few minutes the first time)'
    Run 'Installing the Python packages' { uv sync }

    Say '3/6  Database'
    Run 'Creating the database' { uv run python cli.py init-db }

    Say '4/6  Web UI (a few minutes the first time)'
    Push-Location ui
    try {
        Run 'Installing the web UI' { npm install --no-fund --no-audit }
        Run 'Building the web UI' { npm run build }
    } finally { Pop-Location }

    Say '5/6  Automatic runs'
    $answer = Read-Host 'Search for jobs automatically every day at 08:00 and 18:00? [Y/n]'
    if ($answer -notmatch '^\s*n') { & (Join-Path $PSScriptRoot 'setup-task.ps1') }

    Say '6/6  Done'
    Write-Host 'JobHunter opens in your browser on the Setup page. Enter your accounts and keys there,'
    Write-Host 'then fill in your profile. From now on, open JobHunter with run.bat.'
    & (Join-Path $PSScriptRoot 'run.bat') /setup
} catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Close this window and double-click install.bat again. What is already done is kept.'
    exit 1
}
