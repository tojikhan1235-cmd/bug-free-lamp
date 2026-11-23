"""JARVIS v6.0 — Multi-LLM router with complexity scoring and health cache.

Pluggable brain: with an ANTHROPIC_API_KEY it routes to Claude models as before.
Without any key it runs in LOCAL MODE against a free Ollama server
(http://127.0.0.1:11434, model from env OLLAMA_MODEL, default llama3.1:8b).
Pure standard library — no paid API required.
"""
from __future__ import annotations
import os, json, time, urllib.request
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LLMResponse:
    text: str
    model: str
    complexity: int
    elapsed: float
    error: Optional[str] = None

_HEALTH: dict[str, float] = {}  # model → last_ok timestamp
_HEALTH_TTL = 300  # 5 min

_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

_FRONTIER_TRIGGERS = ("strategy","architecture","mission critical","trading system",
                      "full analysis","deep research","ooda","independent thinking",
                      "build complete","comprehensive","step by step")
_FAST_TRIGGERS     = ("what is","define","translate","simple","quick","yes or no",
                      "single word","one sentence","summarize briefly")
_WEB_TRIGGERS      = ("search","latest","news","current","today","price","weather",
                      "online","look up","fetch","browse","recent")
_CODE_TRIGGERS     = ("write code","implement","function","class","script","fix bug",
                      "refactor","debug","test","module")

def complexity_score(text: str) -> int:
    t = (text or "").lower()
    score = 5
    words = len(t.split())
    if words > 80:  score += 2
    elif words > 40: score += 1
    elif words < 8:  score -= 2
    if any(k in t for k in _FRONTIER_TRIGGERS): score += 3
    if any(k in t for k in _FAST_TRIGGERS):     score -= 2
    if any(k in t for k in _CODE_TRIGGERS):     score += 1
    return max(1, min(10, score))

def classify_task(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in _WEB_TRIGGERS):   return "web_research"
    if any(k in t for k in _CODE_TRIGGERS):  return "code_generation"
    if "trade" in t or "alpaca" in t:        return "trading"
    if "email" in t or "calendar" in t:     return "communication"
    if "file" in t or "document" in t:      return "file_ops"
    return "general"

def _anthropic_key() -> str:
    """Resolve ANTHROPIC_API_KEY from .env first (source of truth), then environ.
    Never logs or prints the value."""
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
    except OSError:
        pass
    return os.getenv("ANTHROPIC_API_KEY", "")

def local_mode() -> bool:
    """True when there is no Anthropic key — JARVIS runs on the free local brain."""
    return not _anthropic_key()

def route(text: str) -> str:
    if local_mode():
        return _OLLAMA_MODEL
    score = complexity_score(text)
    if score >= 8: return "claude-sonnet-4-6"     # frontier
    if score <= 3: return "claude-haiku-4-5-20251001"  # fast
    # 4-7: keyword rules
    t = text.lower()
    if any(k in t for k in _FRONTIER_TRIGGERS): return "claude-sonnet-4-6"
    return "claude-sonnet-4-6"  # default balanced

def _call_ollama(text: str, system: str, history: list | None,
                 model: str, max_tokens: int) -> LLMResponse:
    """Local brain via Ollama /api/chat. Pure stdlib; degrades with a clear error."""
    score = complexity_score(text)
    msgs = list(history or []) + [{"role": "user", "content": text}]
    payload = {"model": model, "stream": False,
               "messages": ([{"role": "system", "content": system}] if system else []) + msgs,
               "options": {"temperature": 0.7, "num_predict": max_tokens}}
    t0 = time.time()
    try:
        req = urllib.request.Request(
            _OLLAMA_HOST + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            body = json.loads(r.read().decode("utf-8"))
        text_out = (body.get("message") or {}).get("content", "").strip()
        if not text_out:
            return LLMResponse("[Ollama returned an empty reply]", model, score,
                               round(time.time() - t0, 2), error="empty_response")
        _HEALTH[model] = time.time()
        return LLMResponse(text_out, model, score, round(time.time() - t0, 2))
    except Exception as e:
        return LLMResponse(
            f"[Local brain error: {e}. Is Ollama running? Start it with `ollama serve` "
            f"and pull a model with `ollama pull {model}`.]",
            model, score, round(time.time() - t0, 2), error=str(e))

def call(text: str, system: str = "", history: list | None = None,
         model: str | None = None, max_tokens: int = 4096) -> LLMResponse:
    system = system or "You are JARVIS, Dew's autonomous AI agent."
    if local_mode():
        selected = model or _OLLAMA_MODEL
        return _call_ollama(text, system, history, selected, max_tokens)
    import anthropic
    key = _anthropic_key()
    selected = model or route(text)
    score    = complexity_score(text)
    msgs     = list(history or []) + [{"role":"user","content":text}]
    t0 = time.time()
    try:
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model=selected, max_tokens=max_tokens,
            system=system,
            messages=msgs)
        return LLMResponse(r.content[0].text, selected, score,
                           round(time.time()-t0, 2))
    except Exception as e:
        return LLMResponse(f"[LLM error: {e}]", selected, score,
                           round(time.time()-t0, 2), error=str(e))

def health_report() -> str:
    if local_mode():
        lines = ["LLM Health (local mode — no Anthropic key):"]
        try:
            with urllib.request.urlopen(_OLLAMA_HOST + "/api/tags", timeout=3) as r:
                body = json.loads(r.read().decode("utf-8"))
            models = [m.get("name", "?") for m in body.get("models", [])]
            lines.append(f"  ollama {_OLLAMA_HOST}: OK")
            lines.append(f"  models pulled: {', '.join(models) if models else 'none — run: ollama pull ' + _OLLAMA_MODEL}")
            lines.append(f"  active brain: {_OLLAMA_MODEL}")
        except Exception as e:
            lines.append(f"  ollama {_OLLAMA_HOST}: UNREACHABLE — {e}")
            lines.append("  Start it with `ollama serve`, then `ollama pull " + _OLLAMA_MODEL + "`.")
        return "\n".join(lines)
    models = ["claude-sonnet-4-6","claude-haiku-4-5-20251001"]
    key = _anthropic_key()
    lines = ["LLM Health:"]
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        for m in models:
            t0 = time.time()
            try:
                r = client.messages.create(model=m, max_tokens=5,
                    messages=[{"role":"user","content":"hi"}])
                lines.append(f"  {m}: OK ({time.time()-t0:.1f}s)")
            except Exception as e:
                lines.append(f"  {m}: FAIL — {e}")
    except ImportError:
        lines.append("  anthropic not installed")
    return "\n".join(lines)
