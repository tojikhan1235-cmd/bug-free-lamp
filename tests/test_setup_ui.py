"""Setup-panel backend: GET /api/brains + POST /api/brain (choose local or your API).

Hermetic: no sockets, no network, no real config writes (SETTINGS_PATH is redirected
to a tmp file). The critical invariant tested here is SAFETY — the payload reports
only whether a key is PRESENT, never its value.
"""
import io
import json
import types

import pytest


_CFG = {"enabled": True, "active": "claude", "profiles": {
    "ollama": {"provider": "ollama", "model": "llama3.1:8b",
               "base_url": "http://localhost:11434", "api_key_env": ""},
    "claude": {"provider": "anthropic", "model": "claude-sonnet-4-6",
               "api_key_env": "ANTHROPIC_API_KEY"},
    "gemini": {"provider": "openai", "model": "gemini-2.5-flash",
               "api_key_env": "GEMINI_API_KEY"},
}}


def _client():
    from core.llm_client import LLMClient
    return LLMClient(json.loads(json.dumps(_CFG)))   # deep copy


# ---------- _brains_payload ----------

def test_brains_payload_structure(monkeypatch):
    from channels.web_server import _brains_payload
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    p = _brains_payload(_client())
    names = [b["name"] for b in p["brains"]]
    assert names == ["ollama", "claude", "gemini"]
    ollama = next(b for b in p["brains"] if b["name"] == "ollama")
    assert ollama["local"] is True and ollama["key_present"] is True   # no key needed
    claude = next(b for b in p["brains"] if b["name"] == "claude")
    assert claude["local"] is False and claude["key_present"] is False
    assert claude["key_env"] == "ANTHROPIC_API_KEY"                     # name only


def test_brains_payload_key_present_flips_with_env(monkeypatch):
    from channels.web_server import _brains_payload
    monkeypatch.setenv("GEMINI_API_KEY", "a-real-looking-key-value")
    p = _brains_payload(_client())
    gemini = next(b for b in p["brains"] if b["name"] == "gemini")
    assert gemini["key_present"] is True and gemini["usable"] is True


def test_brains_payload_never_leaks_secret_value(monkeypatch):
    from channels.web_server import _brains_payload
    secret = "sk-SUPER-SECRET-987654321"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    blob = json.dumps(_brains_payload(_client()))
    assert secret not in blob            # the value must NEVER reach the browser


def test_brains_payload_reflects_pin_state(monkeypatch):
    from channels.web_server import _brains_payload
    c = _client()
    assert _brains_payload(c)["smart_routing"] is True    # not pinned yet
    c.switch("ollama")                                    # pins
    p = _brains_payload(c)
    assert p["smart_routing"] is False and p["active"] == "ollama"


def test_brains_payload_handles_none_llm():
    from channels.web_server import _brains_payload
    assert _brains_payload(None) == {"active": "", "smart_routing": False, "brains": []}


# ---------- _persist_brain_choice ----------

def test_persist_writes_active_and_model(tmp_path):
    from channels.web_server import _persist_brain_choice
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"llm": {"active": "claude", "profiles": {"ollama": {"model": "old"}}},
                             "version": "7.0"}))
    assert _persist_brain_choice(str(p), active="ollama", model="llama3.2:3b") is True
    saved = json.loads(p.read_text())
    assert saved["llm"]["active"] == "ollama"
    assert saved["llm"]["profiles"]["ollama"]["model"] == "llama3.2:3b"
    assert saved["version"] == "7.0"                       # other config preserved


def test_persist_creates_file_when_missing(tmp_path):
    from channels.web_server import _persist_brain_choice
    p = tmp_path / "new.json"
    assert _persist_brain_choice(str(p), active="claude") is True
    assert json.loads(p.read_text())["llm"]["active"] == "claude"


def test_persist_writes_no_secret(tmp_path):
    from channels.web_server import _persist_brain_choice
    p = tmp_path / "s.json"
    _persist_brain_choice(str(p), active="claude", model="claude-sonnet-4-6")
    txt = p.read_text()
    assert "api_key" not in txt.lower() or "ANTHROPIC" not in txt   # only profile name/model, never a key


# ---------- POST /api/brain handler wiring (socket-free) ----------

def _fake_handler(ws, llm, body_dict):
    fake = object.__new__(ws._Handler)
    fake.orch = types.SimpleNamespace(llm=llm)
    fake._status_dict = lambda: {}
    sent = {}
    fake._send = lambda code, b, ctype="application/json": sent.update(code=code, body=json.loads(b))
    raw = json.dumps(body_dict).encode()
    fake.headers = {"Content-Length": str(len(raw))}
    fake.rfile = io.BytesIO(raw)
    return fake, sent


def test_handle_brain_switch_to_local(monkeypatch, tmp_path):
    import channels.web_server as ws
    monkeypatch.setattr(ws, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    (tmp_path / "settings.json").write_text(json.dumps({"llm": {"active": "claude"}}))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm = _client()
    fake, sent = _fake_handler(ws, llm, {"name": "ollama", "model": "llama3.2:3b"})
    ws._Handler._handle_brain_switch(fake)
    assert sent["code"] == 200 and sent["body"]["ok"] is True
    assert llm.active == "ollama" and llm.model == "llama3.2:3b"
    assert "local brain engaged" in sent["body"]["reply"].lower()
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["llm"]["active"] == "ollama"


def test_handle_brain_switch_warns_when_key_missing(monkeypatch, tmp_path):
    import channels.web_server as ws
    monkeypatch.setattr(ws, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm = _client()
    fake, sent = _fake_handler(ws, llm, {"name": "claude"})
    ws._Handler._handle_brain_switch(fake)
    assert sent["code"] == 200 and sent["body"]["ok"] is True
    assert "missing" in sent["body"]["reply"].lower() and ".env" in sent["body"]["reply"]


def test_handle_brain_switch_unknown_400(monkeypatch, tmp_path):
    import channels.web_server as ws
    monkeypatch.setattr(ws, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    llm = _client()
    fake, sent = _fake_handler(ws, llm, {"name": "does-not-exist"})
    ws._Handler._handle_brain_switch(fake)
    assert sent["code"] == 400 and sent["body"]["ok"] is False


def test_handle_brain_switch_auto_unpins(monkeypatch, tmp_path):
    import channels.web_server as ws
    monkeypatch.setattr(ws, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    llm = _client()
    llm.switch("ollama")                       # pinned
    assert llm.pinned is True
    fake, sent = _fake_handler(ws, llm, {"name": "auto"})
    ws._Handler._handle_brain_switch(fake)
    assert sent["code"] == 200 and llm.pinned is False
    assert sent["body"]["brains"]["smart_routing"] is True


def test_handle_brain_switch_bad_json_400(monkeypatch, tmp_path):
    import channels.web_server as ws
    monkeypatch.setattr(ws, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    llm = _client()
    fake = object.__new__(ws._Handler)
    fake.orch = types.SimpleNamespace(llm=llm)
    sent = {}
    fake._send = lambda code, b, ctype="application/json": sent.update(code=code, body=b)
    fake.headers = {"Content-Length": "3"}
    fake.rfile = io.BytesIO(b"{no")             # malformed
    ws._Handler._handle_brain_switch(fake)
    assert sent["code"] == 400


# ---------- LLMClient.test_profile — the TEST button (no switching) ----------

def test_test_profile_unknown_brain():
    c = _client()
    r = c.test_profile("nope")
    assert r["ok"] is False and "no brain called" in r["detail"]


def test_test_profile_ollama_ready(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_get_json", lambda url, timeout=None: {"models": [{"name": "llama3.1:8b"}]})
    r = c.test_profile("ollama")
    assert r["ok"] is True and r["reachable"] is True and r["model_pulled"] is True
    assert "ready" in r["detail"] and isinstance(r["latency_ms"], int)


def test_test_profile_ollama_model_not_pulled(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_get_json", lambda url, timeout=None: {"models": [{"name": "other:latest"}]})
    r = c.test_profile("ollama")
    assert r["ok"] is False and r["reachable"] is True and r["model_pulled"] is False
    assert "ollama pull llama3.1:8b" in r["detail"]


def test_test_profile_ollama_server_down(monkeypatch):
    import urllib.error
    c = _client()
    def boom(url, timeout=None):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(c, "_get_json", boom)
    r = c.test_profile("ollama")
    assert r["ok"] is False and r["reachable"] is False and "can't reach" in r["detail"]


def test_test_profile_cloud_key_missing(monkeypatch):
    c = _client()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = c.test_profile("claude")
    assert r["ok"] is False and r["reachable"] is False
    assert "add ANTHROPIC_API_KEY to your .env" in r["detail"]


def test_test_profile_cloud_anthropic_ok(monkeypatch):
    c = _client()
    secret = "sk-ant-TESTVALUE-123"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    seen = {}
    def fake_post(url, payload, headers, timeout=None):
        seen.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {"content": [{"type": "text", "text": ""}]}
    monkeypatch.setattr(c, "_post", fake_post)
    r = c.test_profile("claude")
    assert r["ok"] is True and r["reachable"] is True
    assert seen["url"].endswith("/v1/messages")
    assert seen["headers"]["x-api-key"] == secret       # key goes ONLY to its own provider
    assert seen["payload"]["max_tokens"] == 1           # minimal ping, bounded cost
    assert seen["timeout"] and seen["timeout"] <= 10    # short, bounded wait
    assert secret not in r["detail"]                    # result never echoes the key


def test_test_profile_cloud_openai_compatible(monkeypatch):
    c = _client()
    secret = "gemi-TESTVALUE-456"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    seen = {}
    def fake_post(url, payload, headers, timeout=None):
        seen.update(url=url, headers=headers)
        return {"choices": []}
    monkeypatch.setattr(c, "_post", fake_post)
    r = c.test_profile("gemini")
    assert r["ok"] is True
    assert seen["url"].endswith("/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer " + secret
    assert secret not in r["detail"]


def test_test_profile_cloud_http_error(monkeypatch):
    import urllib.error
    c = _client()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    def fake_post(url, payload, headers, timeout=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(c, "_post", fake_post)
    r = c.test_profile("claude")
    assert r["ok"] is False and r["reachable"] is True
    assert "HTTP 401" in r["detail"] and "Unauthorized" in r["detail"]


# ---------- POST /api/brain/test handler wiring (socket-free) ----------

def test_handle_brain_test_returns_result():
    import channels.web_server as ws
    llm = _client()
    llm.test_profile = lambda name, timeout=10: {
        "ok": True, "reachable": True, "latency_ms": 42, "detail": "stub"}
    fake, sent = _fake_handler(ws, llm, {"name": "ollama"})
    ws._Handler._handle_brain_test(fake)
    assert sent["code"] == 200 and sent["body"]["ok"] is True and sent["body"]["latency_ms"] == 42


def test_handle_brain_test_requires_name():
    import channels.web_server as ws
    fake, sent = _fake_handler(ws, _client(), {})
    ws._Handler._handle_brain_test(fake)
    assert sent["code"] == 400


def test_handle_brain_test_survives_exception():
    import channels.web_server as ws
    llm = _client()
    def boom(name, timeout=10):
        raise RuntimeError("kaboom")
    llm.test_profile = boom
    fake, sent = _fake_handler(ws, llm, {"name": "ollama"})
    ws._Handler._handle_brain_test(fake)
    assert sent["code"] == 200 and sent["body"]["ok"] is False and "kaboom" in sent["body"]["detail"]
