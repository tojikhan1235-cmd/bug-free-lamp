"""Local-brain + click-by-description coverage (free Ollama mode).

Hermetic: no network, no pyautogui, no API keys. Everything external is monkeypatched.
Guards the contract from AGENTS.md:
  - llm_router falls back to Ollama when no Anthropic key exists, and stays honest
    when Ollama is down;
  - vision (LLMClient.vision / vision_engine) works key-free via Ollama;
  - click_element() = screenshot -> vision coordinates -> click, degrading gracefully;
  - the functions upstream tests depend on (complexity_score/classify_task) are unchanged.
"""
import json
import urllib.error


# ---------- llm_router: local mode ----------

def test_local_mode_routes_to_ollama(monkeypatch):
    import llm_router as R
    monkeypatch.setattr(R, "_anthropic_key", lambda: "")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert R.local_mode() is True
    assert R.route("hi") == "llama3.1:8b"
    assert R.route("deep research strategy architecture") == "llama3.1:8b"  # all roads -> local
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    assert R.route("hi") == "llama3.2:3b"  # env override honored at call time


def test_local_mode_off_with_key(monkeypatch):
    import llm_router as R
    monkeypatch.setattr(R, "_anthropic_key", lambda: "sk-ant-0123456789abcdefghij")
    assert R.local_mode() is False
    assert R.route("hi").startswith("claude")


def test_call_ollama_unreachable_is_honest(monkeypatch):
    import llm_router as R
    monkeypatch.setattr(R, "_anthropic_key", lambda: "")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")  # closed port -> instant refuse
    resp = R.call("hello")
    assert resp.error
    assert "ollama" in resp.text.lower()
    assert resp.model == "llama3.1:8b"


def test_router_functions_tests_depend_on_unchanged():
    import llm_router as R
    assert R.classify_task("search latest news online") == "web_research"
    assert R.classify_task("write a Python class") == "code_generation"
    assert R.complexity_score("hi") == 3
    assert 1 <= R.complexity_score("deep research strategy architecture mission critical") <= 10


# ---------- vision_engine.locate_element ----------

def test_locate_element_parses_coordinates(monkeypatch):
    from modules import vision_engine as V
    monkeypatch.setattr(V, "analyze_image", lambda path, prompt: (
        'Sure! Here you go: {"found": true, "x_pct": 62, "y_pct": 41, "label": "Submit button"}'))
    monkeypatch.setattr(V, "_image_size", lambda path: (1000, 800))
    loc = V.locate_element("the Submit button", path="fake.png")
    assert loc["found"] is True
    assert (loc["x"], loc["y"]) == (620, 328)          # 62% of 1000, 41% of 800
    assert loc["label"] == "Submit button"


def test_locate_element_clamps_and_handles_not_found(monkeypatch):
    from modules import vision_engine as V
    monkeypatch.setattr(V, "_image_size", lambda path: (1920, 1080))
    monkeypatch.setattr(V, "analyze_image", lambda p, q: '{"found": true, "x_pct": 130, "y_pct": -5}')
    loc = V.locate_element("thing", path="f.png")
    assert loc["found"] and loc["x"] == 1920 and loc["y"] == 0   # clamped into the image
    monkeypatch.setattr(V, "analyze_image", lambda p, q: '{"found": false, "label": ""}')
    loc = V.locate_element("thing", path="f.png")
    assert loc["found"] is False and loc["detail"]
    monkeypatch.setattr(V, "analyze_image", lambda p, q: "I see a desktop with icons.")
    loc = V.locate_element("thing", path="f.png")
    assert loc["found"] is False and "usable coordinates" in loc["detail"]


def test_locate_element_needs_a_description():
    from modules import vision_engine as V
    loc = V.locate_element("   ")
    assert loc["found"] is False and loc["detail"]


# ---------- gui_automation.click_element ----------

def test_click_element_without_pyautogui(monkeypatch):
    from modules import gui_automation as G
    monkeypatch.setattr(G, "_PAG", False)
    assert "pyautogui not installed" in G.click_element("the Submit button")


class _FakePG:
    FAILSAFE = True
    def __init__(self): self.clicks = []
    def click(self, x, y, button="left"): self.clicks.append((x, y, button))


def test_click_element_clicks_located_coordinates(monkeypatch):
    from modules import gui_automation as G
    from modules import vision_engine as V
    fake = _FakePG()
    monkeypatch.setattr(G, "_PAG", True)
    monkeypatch.setattr(G, "pyautogui", fake, raising=False)
    monkeypatch.setattr(V, "locate_element", lambda desc, path=None: {
        "found": True, "x": 620, "y": 328, "label": "Submit button", "detail": "vision"})
    out = G.click_element("the Submit button")
    assert fake.clicks == [(620, 328, "left")]
    assert out.startswith("Clicked") and "Submit button" in out


def test_click_element_honest_when_not_found(monkeypatch):
    from modules import gui_automation as G
    from modules import vision_engine as V
    fake = _FakePG()
    monkeypatch.setattr(G, "_PAG", True)
    monkeypatch.setattr(G, "pyautogui", fake, raising=False)
    monkeypatch.setattr(V, "locate_element", lambda desc, path=None: {
        "found": False, "detail": "'the Nope button' is not visible on screen"})
    out = G.click_element("the Nope button")
    assert fake.clicks == []                       # never clicks blind
    assert "couldn't find" in out.lower()


def test_click_element_needs_a_description(monkeypatch):
    from modules import gui_automation as G
    monkeypatch.setattr(G, "_PAG", True)
    assert "describe the element" in G.click_element("").lower()


# ---------- tools layer ----------

def test_input_tool_click_element_delegates(monkeypatch):
    from tools.input_control import InputControlTool
    from modules import gui_automation as G
    t = InputControlTool()
    monkeypatch.setattr(t, "_pg", lambda: object())
    monkeypatch.setattr(G, "click_element", lambda desc, button="left", confirmed=False:
                        f"Clicked {button} on '{desc}' (Submit) at (10,20)")
    r = t.click_element("the Submit button")
    assert r["started"] is True and "Clicked" in r["spoken"]
    monkeypatch.setattr(G, "click_element", lambda desc, button="left", confirmed=False:
                        "I couldn't find 'the Ghost button' on screen — not visible")
    r = t.click_element("the Ghost button")
    assert r["started"] is False and "couldn't" in r["spoken"].lower()


def test_input_tool_click_element_without_pyautogui(monkeypatch):
    from tools.input_control import InputControlTool
    t = InputControlTool()
    monkeypatch.setattr(t, "_pg", lambda: None)
    r = t.click_element("anything")
    assert r["started"] is False and "pip install pyautogui" in r["spoken"]


def test_tool_engine_exposes_click_element(monkeypatch):
    import tool_engine as T
    from modules import gui_automation as G
    names = [s["name"] for s in T.JARVIS_TOOLS]
    assert "click_element" in names
    schema = next(s for s in T.JARVIS_TOOLS if s["name"] == "click_element")
    assert schema["input_schema"]["required"] == ["description"]
    monkeypatch.setattr(G, "click_element", lambda desc, button="left": f"Clicked on '{desc}'")
    out = T._execute_tool("click_element", {"description": "the Submit button"})
    assert out == "Clicked on 'the Submit button'"


# ---------- LLMClient.vision Ollama fallback ----------

_OLLAMA_CFG = {"enabled": True, "active": "ollama",
               "profiles": {"ollama": {"provider": "ollama", "model": "llama3.1:8b",
                                       "base_url": "http://127.0.0.1:11434"}}}


def test_llm_client_vision_falls_back_to_ollama(monkeypatch):
    from core.llm_client import LLMClient
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_VISION_MODEL", raising=False)
    c = LLMClient(_OLLAMA_CFG)
    seen = {}
    def fake_post(url, payload, headers):
        seen["url"], seen["payload"] = url, payload
        return {"message": {"content": '{"found": true, "x_pct": 50, "y_pct": 50}'}}
    monkeypatch.setattr(c, "_post", fake_post)
    out = c.vision("persona", "find the button", "QUJD")
    assert out == '{"found": true, "x_pct": 50, "y_pct": 50}'
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["payload"]["model"] == "llava:7b"
    msg = seen["payload"]["messages"][0]
    assert msg["images"] == ["QUJD"] and msg["content"] == "find the button"


def test_llm_client_vision_prefers_claude_when_keyed(monkeypatch):
    from core.llm_client import LLMClient
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cfg = dict(_OLLAMA_CFG)
    cfg["profiles"] = dict(_OLLAMA_CFG["profiles"])
    cfg["profiles"]["claude"] = {"provider": "anthropic", "model": "claude-sonnet-4-6",
                                 "base_url": "https://api.anthropic.com",
                                 "api_key_env": "ANTHROPIC_API_KEY"}
    c = LLMClient(cfg)
    seen = {}
    def fake_post(url, payload, headers):
        seen["url"], seen["payload"] = url, payload
        return {"content": [{"type": "text", "text": "claude saw it"}]}
    monkeypatch.setattr(c, "_post", fake_post)
    assert c.vision("s", "q", "QUJD") == "claude saw it"
    assert "/v1/messages" in seen["url"] and "model" in seen["payload"]


def test_llm_client_vision_ollama_down_degrades(monkeypatch):
    from core.llm_client import LLMClient
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    c = LLMClient(_OLLAMA_CFG)
    assert c.vision("s", "q", "QUJD") is None
    assert "llava:7b" in c._last_error and "ollama pull" in c._last_error


# ---------- VisionCore eyes ----------

def test_vision_core_has_eyes_with_local_ollama(monkeypatch):
    from core.orchestrator import Orchestrator
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    v = Orchestrator().vision
    monkeypatch.setattr(v, "_ollama_available", lambda: True)
    assert v._has_eyes() is True
    monkeypatch.setattr(v, "_ollama_available", lambda: False)
    assert v._has_eyes() is False


def test_vision_core_locate_reports_local_brain_option(monkeypatch):
    from core.orchestrator import Orchestrator
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    v = Orchestrator().vision
    monkeypatch.setattr(v, "_locate_uia", lambda t: None)
    monkeypatch.setattr(v, "_has_eyes", lambda: False)
    loc = v.locate("the Submit button")
    assert loc["ok"] is False and "ollama" in loc["detail"].lower()
