# Registers (or updates) the scheduled task "JobHunter" (CLAUDE.md §9). Safe to run again.
# Daily 08:00 and 18:00, catches up after the PC was off, wakes the PC, needs network,
# max 2 h, runs as you only while you are logged on (no password is stored).
$ErrorActionPreference = 'Stop'

$taskName = 'JobHunter'
$script = Join-Path $PSScriptRoot 'run.ps1'
$shell = Get-Command pwsh -ErrorAction SilentlyContinue
$shell = if ($shell) { $shell.Source } else { "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" }

$action = New-ScheduledTaskAction -Execute $shell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Trigger scheduled" `
    -WorkingDirectory $PSScriptRoot
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At '08:00'),
    (New-ScheduledTaskTrigger -Daily -At '18:00')
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings `
    -Principal $principal -Description 'JobHunter: search, evaluate and tailor job applications (never submits).' `
    -Force | Out-Null

# Second task: job reminders (core §16c). Every 15 minutes, plain Python, no AI and no tokens.
# pythonw has no console window, so nothing flashes up on the screen.
$remindName = 'JobHunter reminders'
$pythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (Test-Path $pythonw) {
    $remindAction = New-ScheduledTaskAction -Execute $pythonw -Argument 'cli.py reminders --notify' `
        -WorkingDirectory $PSScriptRoot
    $remindTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
        -RepetitionInterval (New-TimeSpan -Minutes 15)
    $remindSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $remindName -Action $remindAction -Trigger $remindTrigger `
        -Settings $remindSettings -Principal $principal `
        -Description 'JobHunter: send the job reminders you set (Telegram). No AI.' -Force | Out-Null
    "Task '$remindName' registered: every 15 minutes"
} else {
    "Task '$remindName' NOT registered: run  uv sync  first (needs .venv\Scripts\pythonw.exe), then this script again"
}

$t = Get-ScheduledTask -TaskName $taskName
"Task '$taskName' registered: " + (($t.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).ToString('HH:mm') }) -join ' and ') +
    " daily · StartWhenAvailable=$($t.Settings.StartWhenAvailable) · WakeToRun=$($t.Settings.WakeToRun) · " +
    "RunOnlyIfNetworkAvailable=$($t.Settings.RunOnlyIfNetworkAvailable) · ExecutionTimeLimit=$($t.Settings.ExecutionTimeLimit)"
