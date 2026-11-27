# JARVIS — repository guidance for GitHub Copilot

Canonical rules: **AGENTS.md** / **CONVENTIONS.md**. These are hard constraints.

## Entry points
- `main.py` is THE entry point (`python main.py` = HUD dashboard, `python main.py --terminal` = text).
  Flow: `main.py → core/orchestrator.py → core/reasoning_core.py → core/agentic_core.py → tools/*`.
- Never wire anything to `jarvis_main.py` or `agent_fabric.py` (deprecated runtimes).
- `gui.py` = dashboard alias; `tool_engine.py` = Anthropic tool_use ReAct loop (Claude-mode only).

## Pluggable brain (free, local-first)
- No API key required. Without `ANTHROPIC_API_KEY`, JARVIS runs on local Ollama
  (`llm_router.local_mode()`), model env `OLLAMA_MODEL` (default `llama3.1:8b`), host env
  `OLLAMA_HOST` (default `http://127.0.0.1:11434`); vision env `OLLAMA_VISION_MODEL`
  (default `llava:7b`). With a key, Claude is used and preferred.
- `main.py::_startup_check()` boots when ANY brain is reachable (Anthropic/provider key, or a live
  Ollama `/api/tags`); it hard-fails with guidance only when nothing exists.
- **Core runtime is pure standard library.** Optional packages (pyautogui, pillow, cv2, psutil,
  anthropic…) must be imported inside `try/except ImportError` and degrade gracefully with an honest
  message — never crash, never pretend success.

## Brain Setup UI
- Both dashboards — HUD (`ui/hud.html`, at `/`) and classic (`ui/dashboard.html`, at `/classic`) —
  have a ⚙ SETUP panel backed by `channels/web_server.py`: `GET /api/brains`, `POST /api/brain
  {"name","model"}` (switch local/cloud brain, edit model; persists to `config/settings.json`,
  non-secret fields only), and `POST /api/brain/test {"name"}` (reachability test WITHOUT
  switching — Ollama: server up + model pulled; cloud: key present + minimal 1-token ping).
- The endpoints NEVER accept or return raw keys — only a `key_present` boolean and the env-var NAME.
  Keys live solely in `.env` (gitignored). Do not change that.

## Safety gates — DO NOT WEAKEN
- `security.py` (SecurityClass A/B/C/X + audit log), `core/permission_gate.py` (the ONE authoritative
  classifier), `core/permission_manager.py`, `core/safety_guard.py`.
- Deletion, overwriting, shell, installs, external comms, system changes, money and trading stay
  confirmation-gated. Self-modification of `PROTECTED_SOURCE` stays Class C/blocked.
- Keep `pyautogui.FAILSAFE = True` wherever pyautogui is imported.
- Never edit a gate to make a failing test pass — the gate wins; report the disagreement.

## Secrets
- Never commit, print, log, or store API keys. `.env` is gitignored and is the source of truth over
  stale shell vars. No secrets in code, config, memory files, notes, or tests.

## click_element (click by description)
- "click the submit button" → intent `click_vision` → `Orchestrator._click_vision` →
  `VisionCore.locate(target)` (Windows UIA tree → two-pass vision zoom → single-pass fallback) →
  `tools/input_control.py::click_at`. Module path: `modules/gui_automation.py::click_element()` →
  `modules/vision_engine.py::locate_element()` (vision returns % coords → pixels) → pyautogui click.
- Vision grounding is best-effort; verify after clicking and report what actually happened.

## Tests
- Run: `python -m pytest tests/ -q --tb=no` (`pytest.ini`).
- **Known-failing baseline** (fails on untouched upstream too — NOT regressions; do not "fix" by
  weakening gates): `tests/test_hardening.py` (3: `test_9b_run_command_is_now_class_b_and_held`,
  `test_11_self_modification_forbidden`, `test_gate_classifies_by_action_not_phrasing`) and
  `tests/test_core.py::test_agentic_brain_chains_actions`.
- Do not change behavior of `llm_router.complexity_score()` / `classify_task()`.

## Platform
- Targets **Windows 10/11**. SAPI voice, Task Scheduler, UI Automation (`uiautomation`), and
  application-control features cannot be exercised on Linux CI/sandboxes — say so explicitly; never
  claim they were verified.
