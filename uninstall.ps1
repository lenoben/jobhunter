# Started by uninstall.bat (double-click). Removes what install.bat added to this folder and to
# Windows: the two scheduled tasks and the installed packages. Your profile, database, documents,
# logs and keys stay unless you type DELETE. uv and Node.js stay installed (other programs may
# use them). Keep this file ASCII and Windows PowerShell 5.1 compatible (see install.ps1).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$root = (Get-Location).Path

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

try {
    Write-Host 'This removes JobHunter from this PC. Close the JobHunter window (run.bat) first.'
    $answer = Read-Host 'Continue? [y/N]'
    if ($answer -notmatch '^\s*[yj]') { Write-Host 'Nothing was changed.'; exit 0 }

    Say '1/3  Scheduled runs'
    # Only the tasks of THIS folder: another copy of JobHunter on the PC keeps its own.
    $tasks = @(Get-ScheduledTask -TaskName 'JobHunter*' -ErrorAction SilentlyContinue |
        Where-Object { $_.Actions | Where-Object { $_.WorkingDirectory -eq $root } })
    foreach ($t in $tasks) {
        Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false
        Write-Host "Removed the task '$($t.TaskName)'."
    }
    if (-not $tasks) { Write-Host 'No scheduled task of this folder found.' }

    Say '2/3  Installed packages'
    foreach ($dir in '.venv', 'ui\node_modules', 'ui\build', 'ui\.svelte-kit') {
        if (Test-Path $dir) {
            try { Remove-Item $dir -Recurse -Force }
            catch { throw "Couldn't remove $dir; JobHunter is probably still open. Close its window and run uninstall.bat again." }
            Write-Host "Removed $dir"
        }
    }

    Say '3/3  Your data'
    $mine = @('profile', 'data', 'output', 'logs', '.env') | Where-Object { Test-Path $_ }
    if ($mine) {
        Write-Host 'These hold your profile, jobs, CVs and letters, logs and keys:'
        $mine | ForEach-Object { Write-Host "  $root\$_" }
        Write-Host 'Keep them if you might install JobHunter again; it picks them up.'
        $answer = Read-Host 'Type DELETE to delete them for good, or press Enter to keep them'
        if ($answer -ceq 'DELETE') {
            $mine | ForEach-Object { Remove-Item $_ -Recurse -Force }
            Write-Host 'Your data was deleted.'
        } else {
            Write-Host 'Your data was kept.'
        }
    }

    Say 'Done'
    Write-Host "You can now delete the folder $root yourself."
    Write-Host 'uv and Node.js are still installed; remove them in Windows Settings > Apps if you like.'
} catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
