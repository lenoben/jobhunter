#!/usr/bin/env bash
# JobHunter entry point for macOS/Linux: the twin of run.ps1 (CLAUDE.md §9, §10). NOT TESTED on
# Linux/macOS yet (2026-10-25). Usage: ./run.sh [scheduled|manual|docs|single|evaluate] [JOB_ID]
# Stages: filter (model_filter) → write (model_writer); docs = write stage only; single = one job.
# LLM_PROVIDER (.env) other than claude-code runs the same stages via `cli.py agent`.
# cron example (08:00 and 18:00):  0 8,18 * * *  cd /path/to/jobhunter && ./run.sh scheduled
# job reminders (core §16c), every 15 min:  */15 * * * *  cd /path/to/jobhunter && .venv/bin/python cli.py reminders --notify
set -u

TRIGGER="${1:-scheduled}"
JOB_ID="${2:-0}"
case "$TRIGGER" in scheduled|manual|docs|single|evaluate) ;; *) echo "unknown trigger: $TRIGGER" >&2; exit 2;; esac

# R7: never use an API key with Claude Code; it runs on the subscription.
unset ANTHROPIC_API_KEY

cd "$(dirname "$0")" || exit 1
# cron starts with a bare environment: make sure uv and claude are found.
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

mkdir -p logs
LOG="logs/run_$(date +%Y-%m-%d_%H%M%S)_${TRIGGER}.log"
SINCE="$(date -u '+%Y-%m-%d %H:%M:%S')"   # runs.started_at is UTC

log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*" | tee -a "$LOG"; }

PROVIDER="$(uv run python cli.py llm-provider 2>/dev/null | tail -n 1)"
PROVIDER="${PROVIDER:-claude-code}"

get_model() {  # key default
    local m
    m="$(uv run python cli.py setting "$1" 2>/dev/null | tail -n 1)"
    case "$m" in haiku|sonnet|opus) echo "$m";; *) echo "$2";; esac
}

invoke_stage() {  # stage model
    local stage="$1" model="$2" code
    if [ "$PROVIDER" != "claude-code" ]; then
        log "stage '$stage' started (provider: $PROVIDER)"
        uv run python cli.py agent --trigger "$TRIGGER" --stage "$stage" --job "$JOB_ID" 2>&1 | tee -a "$LOG"
        code=${PIPESTATUS[0]}
    else
        log "stage '$stage' started (model: $model)"
        local prompt="Run the job-hunt workflow defined in .claude/skills/job-hunt/SKILL.md. Trigger: $TRIGGER. Stage: $stage."
        [ "$JOB_ID" -gt 0 ] && prompt="$prompt Job: $JOB_ID."
        claude -p "$prompt" \
            --model "$model" \
            --mcp-config .mcp.json --strict-mcp-config \
            --permission-mode dontAsk \
            --allowedTools "mcp__jobhunter" \
            --disallowedTools "Bash" "PowerShell" "Write" "Edit" "NotebookEdit" "WebFetch" "WebSearch" \
            --output-format json 2>&1 | tee -a "$LOG"
        code=${PIPESTATUS[0]}
    fi
    log "stage '$stage' exited with code $code"
    return "$code"
}

run_open() {  # check-run exits 1 when a run started since $SINCE is still open
    uv run python cli.py check-run --since "$SINCE" 2>&1 | tee -a "$LOG"
    [ "${PIPESTATUS[0]}" -ne 0 ]
}

send_failure() {
    uv run python cli.py notify-failure --reason "$1" --log "$LOG" 2>&1 | tee -a "$LOG"
}

finish() { log "JobHunter run finished (exit $1)"; exit "$1"; }

log "JobHunter run started (trigger: $TRIGGER$([ "$JOB_ID" -gt 0 ] && echo ", job $JOB_ID"))"

if [ "$TRIGGER" = "single" ]; then
    [ "$JOB_ID" -gt 0 ] || { log "trigger single needs a JOB_ID"; exit 2; }
    invoke_stage single "$(get_model model_filter haiku)"; code=$?
    if [ $code -ne 0 ]; then
        send_failure "single-job run (job $JOB_ID): exited with code $code"
    elif run_open; then
        invoke_stage single-write "$(get_model model_writer sonnet)"; code=$?
        if [ $code -ne 0 ]; then
            send_failure "single-job run (job $JOB_ID), writer: exited with code $code"
        elif run_open; then
            send_failure "the single-job run (job $JOB_ID) stopped before finish_run"; code=1
        fi
    fi
    finish $code
fi

if [ "$TRIGGER" = "docs" ]; then
    invoke_stage docs "$(get_model model_writer sonnet)"; code=$?
    if [ $code -ne 0 ]; then
        send_failure "documents run: exited with code $code"
    elif run_open; then
        send_failure "the documents run stopped before finish_run"; code=1
    fi
    finish $code
fi

# Follow-up reminders go out before the run, so they also arrive when the time guard refuses it.
if [ "$TRIGGER" = "scheduled" ] || [ "$TRIGGER" = "manual" ]; then
    uv run python cli.py followups --notify 2>&1 | tee -a "$LOG"
fi

STAGE1=filter
[ "$TRIGGER" = "evaluate" ] && STAGE1=evaluate
invoke_stage "$STAGE1" "$(get_model model_filter haiku)"; code=$?
if [ $code -ne 0 ]; then
    send_failure "$STAGE1 stage: exited with code $code"
elif run_open; then
    # Stage 1 left the run open, as it should: the writer stage continues it and calls finish_run.
    invoke_stage write "$(get_model model_writer sonnet)"; code=$?
    if [ $code -ne 0 ]; then
        send_failure "writer stage: exited with code $code (evaluations from the filter stage are kept)"
    elif run_open; then
        send_failure "the writer stage stopped before finish_run"; code=1
    fi
fi
# else: no open run — refused by the time guard (nothing to do) or already closed.
finish $code
