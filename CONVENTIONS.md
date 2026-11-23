# CONVENTIONS.md — JARVIS coding rules (agent-agnostic summary)

Canonical source: **AGENTS.md** (read it in full). This is the portable summary that every
coding agent's config mirrors. These are hard constraints, not suggestions.

## Entry points
- **`main.py` is THE entry point.** `python main.py` (dashboard/HUD), `python main.py --terminal`
  (text). Runtime path: `main.py → core/orchestrator.py → core/reasoning_core.py →
  core/agentic_core.py → tools/*`.
- **Never wire anything to `jarvis_main.py` or `agent_fabric.py`** (deprecated runtimes).
- `gui.py` = dashboard alias; `tool_engine.py` = Anthropic tool_use ReAct loop (Claude-mode only).

## Pluggable brain (free local by default)
- No API key required. No `ANTHROPIC_API_KEY` → local Ollama: `llm_router.local_mode()` True,
  model from env `OLLAMA_MODEL` (default `llama3.1:8b`), host env `OLLAMA_HOST`
  (default `http://127.0.0.1:11434`). With a key, Claude is used and preferred.
- Vision: env `OLLAMA_VISION_MODEL` (default `llava:7b`) locally; Claude when keyed.
  `core/vision_core.py::VisionCore` = the eyes: `look()`, `verify()`, `locate()`.
- **Core runtime is pure standard library.** Optional packages (pyautogui, pillow, cv2, psutil,
  anthropic…) go behind `try/except ImportError` and degrade gracefully with an honest message —
  never crash, never fake success.

## Brain Setup UI
- The HUD (`ui/hud.html`) has a ⚙ **SETUP** panel backed by `channels/web_server.py`:
  `GET /api/brains` (lists brains) and `POST /api/brain` `{"name","model"}` (switch local/cloud,
  edit model). Choice persists to `config/settings.json` (non-secret only).
- **The API never accepts or returns raw keys** — only a `key_present` boolean and the env-var
  NAME. Keys live solely in `.env` (gitignored). Keep it that way.

## Safety gates — DO NOT WEAKEN
- `security.py` (SecurityClass A/B/C/X + SHA256-chained audit log), `core/permission_gate.py`
  (the ONE authoritative classifier), `core/permission_manager.py`, `core/safety_guard.py`.
- Deletion, overwriting, shell, installs, external comms, system changes, money and trading stay
  confirmation-gated. Self-modification of `PROTECTED_SOURCE` stays Class C/blocked.
- `pyautogui.FAILSAFE = True` wherever pyautogui is imported (top-left corner = emergency abort).
- Never edit a gate to make a failing test pass — the gate wins; report the disagreement.

## Secrets
- Never commit, print, log, or store keys. `.env` is gitignored and is the source of truth over
  stale shell vars. No secrets in code, config, memory files, notes, or tests.

## click_element (click by description)
- NL: "click the submit button" → intent `click_vision` → `Orchestrator._click_vision` →
  `VisionCore.locate(target)` (Windows UIA tree → two-pass vision zoom → single-pass) →
  `tools/input_control.py::click_at`. Module-level path: `modules/gui_automation.py::click_element()`
  → `modules/vision_engine.py::locate_element()` (vision returns % coords → pixels) → pyautogui.
- Grounding is best-effort; verify after clicking and report what actually happened.

## Tests
- Run: `python -m pytest tests/ -q --tb=no` (config: `pytest.ini`).
- **Known-failing baseline** (also fails on untouched upstream — NOT regressions; do NOT "fix" by
  weakening gates): `tests/test_hardening.py` (3: `test_9b_run_command_is_now_class_b_and_held`,
  `test_11_self_modification_forbidden`, `test_gate_classifies_by_action_not_phrasing`) and
  `tests/test_core.py::test_agentic_brain_chains_actions`.
- Do not change behavior of `llm_router.complexity_score()` / `classify_task()` (tests depend on them).

## Platform
- Targets **Windows 10/11**. SAPI voice, Task Scheduler, UI Automation (`uiautomation`), and
  application-control features cannot be exercised on Linux CI/sandboxes — say so explicitly;
  never claim they were verified.
