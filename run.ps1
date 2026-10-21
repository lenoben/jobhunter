# JobHunter entry point for Task Scheduler (CLAUDE.md §9, §10). Usage: .\run.ps1 [-Trigger scheduled|manual]
# Runs Claude headless on the Pro subscription with only the jobhunter MCP tools + Read, in two stages
# (or, if LLM_PROVIDER in .env is not claude-code, the same stages via `cli.py agent`, core/agent.py):
#   1 filter (model_filter, default haiku): start_run, search, evaluate/score, project suggestions
#   2 write  (model_writer, default sonnet): CVs + cover letters, email drafts, finish_run
#   -Trigger docs ("Generate now" in the UI): only the write stage, only for jobs the user requested
#   -Trigger single -JobId N ("Evaluate now"): evaluate one job (filter model), then write its
#                    documents if it meets the criteria (writer model)
#   -Trigger evaluate ("Score waiting jobs"): stage 1 evaluates the backlog of new jobs without
#                    searching (no time guard), then the normal write stage
param(
    [ValidateSet('scheduled', 'manual', 'docs', 'single', 'evaluate')]
    [string]$Trigger = 'scheduled',
    [int]$JobId = 0
)

# R7: never use an API key; everything runs on the Pro subscription.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

Set-Location -LiteralPath $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# Task Scheduler starts with a bare environment: make sure uv and the npm-installed claude are found.
$env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$env:Path"

New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = "logs/run_$(Get-Date -Format 'yyyy-MM-dd_HHmmss')_$Trigger.log"
$since = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')   # runs.started_at is UTC

function Write-Log([string]$msg) { "[$(Get-Date -Format s)] $msg" | Tee-Object -FilePath $log -Append | Out-Host }

function Get-Model([string]$key, [string]$default) {
    $m = (uv run python cli.py setting $key 2>$null | Select-Object -Last 1)
    if ($m -in @('haiku', 'sonnet', 'opus')) { return $m }
    return $default   # missing/unknown value → safe default
}

$provider = (uv run python cli.py llm-provider 2>$null | Select-Object -Last 1)
if (-not $provider) { $provider = 'claude-code' }

function Invoke-Stage([string]$stage, [string]$model) {
    if ($provider -ne 'claude-code') {
        # Another LLM provider: the agent loop uses the same MCP tools and the same skill; the
        # models come from the settings llm_model_filter / llm_model_writer.
        Write-Log "stage '$stage' started (provider: $provider)"
        uv run python cli.py agent --trigger $Trigger --stage $stage --job $JobId *>&1 | Tee-Object -FilePath $log -Append | Out-Host
        $c = $LASTEXITCODE
        Write-Log "stage '$stage' exited with code $c"
        return $c
    }
    Write-Log "stage '$stage' started (model: $model)"
    $prompt = "Run the job-hunt workflow defined in .claude/skills/job-hunt/SKILL.md. Trigger: $Trigger. Stage: $stage."
    if ($JobId -gt 0) { $prompt += " Job: $JobId." }
    # --strict-mcp-config: only the jobhunter server, none of the user's other connectors.
    # --permission-mode dontAsk: anything not allowed in .claude/settings.json is denied, never prompted.
    # --output-format json: the log gets the result, turn count, model usage and any permission denials.
    & claude -p $prompt `
        --model $model `
        --mcp-config .mcp.json --strict-mcp-config `
        --permission-mode dontAsk `
        --allowedTools "mcp__jobhunter" `
        --disallowedTools "Bash" "PowerShell" "Write" "Edit" "NotebookEdit" "WebFetch" "WebSearch" `
        --output-format json *>&1 | Tee-Object -FilePath $log -Append | Out-Host
    $c = $LASTEXITCODE
    Write-Log "stage '$stage' exited with code $c"
    return $c
}

function Test-RunOpen {
    # check-run exits 1 when a run started since $since is still open
    uv run python cli.py check-run --since $since *>&1 | Tee-Object -FilePath $log -Append | Out-Host
    return ($LASTEXITCODE -ne 0)
}

function Send-Failure([string]$reason) {
    uv run python cli.py notify-failure --reason $reason --log $log *>&1 | Tee-Object -FilePath $log -Append | Out-Host
}

Write-Log "JobHunter run started (trigger: $Trigger$(if ($JobId) { ", job $JobId" }))"
if ($Trigger -eq 'single') {
    if ($JobId -le 0) { Write-Log "-Trigger single needs -JobId"; exit 2 }
    $code = Invoke-Stage 'single' (Get-Model 'model_filter' 'haiku')
    if ($code -ne 0) {
        Send-Failure "single-job run (job $JobId): claude exited with code $code"
    } elseif (Test-RunOpen) {
        $code = Invoke-Stage 'single-write' (Get-Model 'model_writer' 'sonnet')
        if ($code -ne 0) {
            Send-Failure "single-job run (job $JobId), writer: claude exited with code $code"
        } elseif (Test-RunOpen) {
            Send-Failure "the single-job run (job $JobId) stopped before finish_run"
            $code = 1
        }
    }
    Write-Log "JobHunter run finished (exit $code)"
    exit $code
}
if ($Trigger -eq 'docs') {
    # Writer only: the stage starts its own "docs" run, writes the requested documents, finishes it.
    $code = Invoke-Stage 'docs' (Get-Model 'model_writer' 'sonnet')
    if ($code -ne 0) {
        Send-Failure "documents run: claude exited with code $code"
    } elseif (Test-RunOpen) {
        Send-Failure "the documents run stopped before finish_run"
        $code = 1
    }
    Write-Log "JobHunter run finished (exit $code)"
    exit $code
}

# Follow-up reminders (applications without a reply) go out before the run, so they also arrive
# when the time guard refuses it. A failure here never stops the run.
if ($Trigger -in @('scheduled', 'manual')) {
    uv run python cli.py followups --notify *>&1 | Tee-Object -FilePath $log -Append | Out-Host
}

$stage1 = if ($Trigger -eq 'evaluate') { 'evaluate' } else { 'filter' }
$code = Invoke-Stage $stage1 (Get-Model 'model_filter' 'haiku')

if ($code -ne 0) {
    Send-Failure "$stage1 stage: claude exited with code $code"
} elseif (Test-RunOpen) {
    # Stage 1 left the run open, as it should: the writer stage continues it and calls finish_run.
    $code = Invoke-Stage 'write' (Get-Model 'model_writer' 'sonnet')
    if ($code -ne 0) {
        Send-Failure "writer stage: claude exited with code $code (evaluations from the filter stage are kept)"
    } elseif (Test-RunOpen) {
        Send-Failure "the writer stage stopped before finish_run"
        $code = 1
    }
}
# else: no open run — refused by the time guard (nothing to do) or already closed.

Write-Log "JobHunter run finished (exit $code)"
exit $code
