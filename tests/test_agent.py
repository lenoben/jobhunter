"""core/agent.py: the loop for OpenAI-compatible providers (no network: HTTP is faked)."""

import httpx
import pytest

from core import agent


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    for k in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)


def test_config_presets_and_key(monkeypatch):
    assert agent.provider_name() == "claude-code"
    with pytest.raises(RuntimeError, match="claude-code"):
        agent.load_llm_config()
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        agent.load_llm_config()
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    cfg = agent.load_llm_config()
    assert cfg.base_url == "https://api.groq.com/openai/v1" and "secret-key" not in repr(cfg)
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        agent.load_llm_config()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("LLM_API_KEY")
    assert agent.load_llm_config().base_url == "http://localhost:11434/v1"  # no key needed


def test_stage_model():
    s = {"llm_model_filter": "small", "llm_model_writer": "big"}
    assert [agent.stage_model(s, st) for st in ("filter", "evaluate", "single", "write", "docs", "single-write")] \
        == ["small"] * 3 + ["big"] * 3
    with pytest.raises(RuntimeError, match="llm_model_writer"):
        agent.stage_model({}, "write")


def test_read_file_only_templates_and_skills():
    assert "{" in agent.read_file("templates/examples/cv_de.json")
    for path in (".env", "profile/profile.yaml", "../secret", "templates/../.env", "data/jobhunter.db"):
        assert agent.read_file(path).startswith("ERROR")


def test_trim_history_blanks_oldest_tool_results_first():
    msgs = [{"role": "system", "content": "s"}] + [
        {"role": "tool", "tool_call_id": str(i), "content": "x" * 1000} for i in range(12)]
    agent.trim_history(msgs, budget=9000)
    assert msgs[1]["content"].startswith("[older")
    assert all(m["content"] == "x" * 1000 for m in msgs[-agent.KEEP_RECENT_RESULTS:])


def test_chat_retries_rate_limits(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0.01"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    monkeypatch.setattr(agent.time, "sleep", lambda s: None)
    cfg = agent.LLMConfig("groq", "https://api.example/v1", "k")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = agent.chat(client, cfg, {"model": "m"}, log=lambda m: None)
    assert data["choices"][0]["message"]["content"] == "done" and len(calls) == 2
    assert calls[0].headers["authorization"] == "Bearer k"


def test_chat_fails_fast_on_bad_request():
    cfg = agent.LLMConfig("groq", "https://api.example/v1", "k")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad model"))) as client:
        with pytest.raises(RuntimeError, match="HTTP 400"):
            agent.chat(client, cfg, {}, log=lambda m: None)
