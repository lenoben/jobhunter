"""Run a job-hunt stage with another LLM provider instead of Claude Code (user request 2026-10-25).

Any OpenAI-compatible chat API works (Groq, OpenAI, OpenRouter, Mistral, local Ollama …). The loop
connects to the jobhunter MCP server as a client, so the model gets exactly the tools `claude -p`
gets, and every guard lives in those tools as before: is_seen (R8), the R9 refusals, the docs.py
checks, "drafts only, never send" (R1). The instructions are the job-hunt skill itself.

.env (R3: the key lives only there):
    LLM_PROVIDER = claude-code (default: run.ps1 uses `claude -p`) | groq | openai | openrouter |
                   mistral | ollama | custom
    LLM_API_KEY  = the provider's key (not needed for ollama)
    LLM_BASE_URL = only for custom, or to override a preset
The models are the settings llm_model_filter and llm_model_writer (cli.py setup lists the
provider's models to pick from).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from core.db import ROOT

# name → (base URL, where to create a key). Model names change too often to hard-code: the
# setup wizard asks the provider's /models endpoint.
PROVIDERS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "https://console.groq.com/keys"),
    "openai": ("https://api.openai.com/v1", "https://platform.openai.com/api-keys"),
    "openrouter": ("https://openrouter.ai/api/v1", "https://openrouter.ai/keys"),
    "mistral": ("https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys"),
    "ollama": ("http://localhost:11434/v1", ""),
}
SKILL = ROOT / ".claude" / "skills" / "job-hunt" / "SKILL.md"
READABLE = ("templates/", ".claude/skills/")   # what read_file may open (never .env, profile/, data/)
WRITER_STAGES = ("write", "docs", "single-write")
MAX_TURNS = 200
MAX_TOOL_RESULT = 30_000          # characters per tool result given to the model
KEEP_RECENT_RESULTS = 8           # tool results never trimmed, counted from the end


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    api_key: str = ""

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return f"LLMConfig(provider={self.provider!r}, base_url={self.base_url!r})"


def provider_name() -> str:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return (os.environ.get("LLM_PROVIDER") or "claude-code").strip().lower()


def load_llm_config() -> LLMConfig:
    name = provider_name()
    if name == "claude-code":
        raise RuntimeError("LLM_PROVIDER is claude-code: runs use `claude -p`, not this loop")
    base = (os.environ.get("LLM_BASE_URL") or "").strip() or PROVIDERS.get(name, ("", ""))[0]
    if not base:
        raise RuntimeError(f"LLM_PROVIDER={name!r}: set LLM_BASE_URL in .env (an OpenAI-compatible /v1 URL)")
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    if not key and name != "ollama":
        raise RuntimeError("LLM_API_KEY must be set in .env")
    return LLMConfig(name, base.rstrip("/"), key)


def list_models(cfg: LLMConfig) -> list[str]:
    """The model ids the provider offers (GET /models)."""
    r = httpx.get(f"{cfg.base_url}/models", headers=_headers(cfg), timeout=30)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []) if m.get("id"))


def stage_model(settings: dict[str, str], stage: str) -> str:
    key = "llm_model_writer" if stage in WRITER_STAGES else "llm_model_filter"
    model = (settings.get(key) or "").strip()
    if not model:
        raise RuntimeError(f"setting {key} is empty: run `uv run python cli.py setup` or set it in /settings")
    return model


def system_prompt() -> str:
    skill = SKILL.read_text(encoding="utf-8")
    if skill.startswith("---"):
        skill = skill.split("---", 2)[2]  # drop the front matter
    return ("You are the JobHunter agent. Follow the skill below exactly. Where it says `Read`, call the "
            "read_file tool. Call tools one step at a time and check each result. When the stage is "
            "done, reply with a short summary and no tool call.\n\n" + skill.strip())


def stage_prompt(trigger: str, stage: str, job_id: int = 0) -> str:
    p = f"Run the job-hunt workflow. Trigger: {trigger}. Stage: {stage}."
    return p + (f" Job: {job_id}." if job_id else "")


def read_file(path: str) -> str:
    rel = path.replace("\\", "/").lstrip("/")
    target = (ROOT / rel).resolve()
    if not any(target.is_relative_to((ROOT / p).resolve()) for p in READABLE) or not target.is_file():
        return f"ERROR: read_file only opens files under {', '.join(READABLE)}"
    return target.read_text(encoding="utf-8")


READ_TOOL = {"type": "function", "function": {
    "name": "read_file",
    "description": "Read a project file under templates/ or .claude/skills/ (e.g. templates/examples/cv_de.json).",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}


def trim_history(messages: list[dict], budget: int) -> None:
    """Keep the conversation under `budget` characters by blanking the oldest tool results.
    A run handles one job after another, so old results are rarely needed again."""
    size = sum(len(m.get("content") or "") + len(json.dumps(m.get("tool_calls") or "")) for m in messages)
    tool_idx = [i for i, m in enumerate(messages) if m["role"] == "tool"][:-KEEP_RECENT_RESULTS]
    for i in tool_idx:
        if size <= budget:
            return
        old = messages[i]["content"]
        if old.startswith("[older result removed"):
            continue
        messages[i]["content"] = "[older result removed to save context; call the tool again if needed]"
        size -= len(old) - len(messages[i]["content"])


def _headers(cfg: LLMConfig) -> dict[str, str]:
    return {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}


def chat(client: httpx.Client, cfg: LLMConfig, payload: dict, log: Callable[[str], None]) -> dict:
    """One completion; waits and retries on rate limits (429) and server errors."""
    for attempt in range(8):
        try:
            r = client.post(f"{cfg.base_url}/chat/completions", json=payload, headers=_headers(cfg))
        except httpx.TransportError as e:
            wait, why = 2 ** attempt, f"network error {type(e).__name__}"
        else:
            if r.status_code < 400:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{cfg.provider}: HTTP {r.status_code}: {r.text[:300]}")
            wait = float(r.headers.get("retry-after") or 0) or min(60, 2 ** (attempt + 1))
            why = f"HTTP {r.status_code}"
        log(f"{why}, waiting {wait:.0f}s")
        time.sleep(wait)
    raise RuntimeError(f"{cfg.provider}: gave up after repeated rate limits / errors")


async def run_stage(trigger: str, stage: str, job_id: int = 0, log: Callable[[str], None] = print) -> int:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from core import db

    cfg = load_llm_config()
    conn = db.connect()
    try:
        db.migrate(conn)
        settings = db.get_settings(conn)
    finally:
        conn.close()
    model = stage_model(settings, stage)
    budget = int(os.environ.get("LLM_CONTEXT_CHARS") or 120_000)
    log(f"provider {cfg.provider}, model {model}, stage {stage}")

    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(ROOT),
                                   env=dict(os.environ))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        mcp_tools = (await session.list_tools()).tools
        tools = [{"type": "function", "function": {
            "name": t.name, "description": (t.description or "")[:1024],
            "parameters": t.inputSchema or {"type": "object", "properties": {}}}} for t in mcp_tools] + [READ_TOOL]
        messages: list[dict] = [{"role": "system", "content": system_prompt()},
                                {"role": "user", "content": stage_prompt(trigger, stage, job_id)}]
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        with httpx.Client(timeout=180) as client:
            for turn in range(1, MAX_TURNS + 1):
                trim_history(messages, budget)
                data = chat(client, cfg, {"model": model, "messages": messages, "tools": tools,
                                          "tool_choice": "auto", "temperature": 0.2}, log)
                for k in usage:
                    usage[k] += (data.get("usage") or {}).get(k, 0)
                msg = data["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                messages.append({"role": "assistant", "content": msg.get("content") or "",
                                 **({"tool_calls": calls} if calls else {})})
                if not calls:
                    log(json.dumps({"result": msg.get("content") or "", "num_turns": turn, "usage": usage},
                                   ensure_ascii=False))
                    return 0
                for call in calls:
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                        if name == "read_file":
                            text = read_file(str(args.get("path", "")))
                        else:
                            res = await session.call_tool(name, args)
                            text = "\n".join(getattr(c, "text", "") for c in res.content)
                            if res.isError:
                                text = "ERROR: " + text
                    except json.JSONDecodeError:
                        text = "ERROR: arguments were not valid JSON"
                    except Exception as e:  # a tool failure is the model's to handle, not a crash
                        text = f"ERROR: {type(e).__name__}: {e}"
                    log(f"turn {turn}: {name} ({len(text)} chars)")  # no tool output in the log (R4)
                    if len(text) > MAX_TOOL_RESULT:
                        text = text[:MAX_TOOL_RESULT] + "\n[result cut off]"
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": text})
    log(f"stopped after {MAX_TURNS} turns")
    return 1


def main(trigger: str, stage: str, job_id: int = 0) -> int:
    try:
        return asyncio.run(run_stage(trigger, stage, job_id))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
