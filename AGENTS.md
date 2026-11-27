# AGENTS.md — rules for AI coding agents working in this repo

You are editing JARVIS, a Windows-first personal AI assistant. Read this fully before
changing anything. These rules are hard constraints, not suggestions.

## Entry points

- **`main.py` is THE entry point.** `python main.py` (dashboard), `python main.py --terminal`
  (text mode). Runtime path: `main.py → core/orchestrator.py → core/reasoning_core.py →
  core/agentic_core.py → tools/*`.
- **Never wire anything to `jarvis_main.py` or `agent_fabric.py`** — deprecated runtimes kept
  only for history. Do not import them in new code.
- `gui.py` is the dashboard alias; `tool_engine.py` is the Anthropic tool_use ReAct loop
  (Claude-mode only).

## Pluggable brain (free local by default)

- No API key is required. `llm_router.local_mode()` is True when there is no
  `ANTHROPIC_API_KEY`; then `route()` returns the local model (env `OLLAMA_MODEL`, default
  `llama3.1:8b`) and `call()` goes to Ollama `/api/chat` at `http://127.0.0.1:11434`
  (override with `OLLAMA_HOST`).
- Vision: `modules/vision_engine.py` uses `OLLAMA_VISION_MODEL` (default `llava:7b`) when no
  Anthropic key exists; Claude otherwise. `VisionCore` (`core/vision_core.py`) is the
  orchestrator's eyes: `look()`, `verify()`, `locate()`.
- `main.py::_startup_check()` boots when ANY brain is reachable (Anthropic key, any of
  PERPLEXITY/NVIDIA/GEMINI/FIRECRAWL keys, or a live Ollama `/api/tags`). It hard-fails with
  setup guidance only when nothing exists.
- **Core runtime is pure standard library.** Optional packages (pyautogui, pillow, cv2,
  psutil, anthropic…) go behind `try/except ImportError` and must degrade gracefully with an
  honest message — never crash, never pretend success.
- **Never commit, print, log, or store keys.** `.env` is gitignored; the `.env` FILE is the
  source of truth over stale shell vars. No keys in config, memory files, notes, or tests.

## Safety gates — DO NOT WEAKEN

- `security.py` — SecurityClass A/B/C/X classifier + SHA256-chained audit log.
- `core/permission_gate.py` — the ONE authoritative classifier keyed on dispatch intent names.
- `core/permission_manager.py`, `core/safety_guard.py` — hold/confirm flow.
- Deletion, overwriting, shell, installs, external comms, system changes, money and trading
  stay confirmation-gated. Self-modification of `PROTECTED_SOURCE` stays Class C/blocked.
- `pyautogui.FAILSAFE = True` wherever pyautogui is imported — slamming the mouse to the
  top-left corner is the emergency abort. Never remove it.
- Never edit the gates to make a failing test pass. If a test disagrees with the gate, report
  it; the gate wins.

## Desktop control / click-by-description

- Natural language: "click the submit button" → intent `click_vision` →
  `Orchestrator._click_vision` → `VisionCore.locate(target)` → `tools/input_control.py
  ::click_at(x, y)`.
- `VisionCore.locate()` strategy, best-first: (1) Windows UI Automation accessibility tree —
  pixel-exact; (2) two-pass vision "zoom-and-confirm" (coarse locate → crop+2x upscale →
  refine); (3) single-pass fallback. Returns `{ok, x, y, label, method, detail}` and degrades
  honestly.
- Module-level convenience: `modules/gui_automation.py::click_element("the Submit button")` —
  screenshot → `vision_engine.locate_element()` (asks the vision model for coordinates as
  percentages, converts to pixels) → pyautogui click. Works on Ollama/llava with no API key.
- Vision grounding is best-effort: models can mislocate. Always verify after clicking
  (`VisionCore.verify`) and say what actually happened.

## Brain Setup UI (choose local or your own API)

- BOTH dashboards have a ⚙ **SETUP** button that opens the same Brain Setup panel: the HUD
  (`ui/hud.html`, served at `/`) and the classic dashboard (`ui/dashboard.html`, at `/classic`).
  Pick **Local (Ollama, free, no key)** or a **cloud brain** (Claude / Perplexity / NVIDIA /
  Gemini), edit any brain's model, **TEST** it, and Apply — the choice takes effect live and
  persists to `config/settings.json` (non-secret fields only: `llm.active` + per-profile `model`).
- Backing endpoints in `channels/web_server.py`:
  - `GET /api/brains` → `{active, smart_routing, brains:[{name, provider, model, key_env,
    key_present, local, usable}]}`. **Returns only whether a key is PRESENT (bool) and the env-var
    NAME — never the key value.**
  - `POST /api/brain` `{"name":"ollama"|"claude"|...|"auto", "model":"optional"}` → switches the
    live brain (`llm.switch`/`llm.auto`) and persists the choice. `auto` = smart per-request routing.
  - `POST /api/brain/test` `{"name":"..."}` → tests a brain **without switching** to it
    (`LLMClient.test_profile`): Ollama = server up + model pulled (`/api/tags`); cloud = key
    present + a minimal 1-token ping with a short timeout. Returns
    `{ok, reachable, latency_ms, detail[, model_pulled]}`.
- **SAFETY: the API never accepts or returns raw keys.** Keys live solely in `.env` (gitignored).
  Keep it that way — the panel is a switcher, not a key vault. Cloud brains show
  "add <ENV_VAR> to .env" when their key is missing. `test_profile` sends a key only to its OWN
  provider (normal operation) and never echoes it in results or logs.

## Coding agents (works with any tool)

The same rules are mirrored into every major agent's native config so the project behaves
consistently regardless of the tool. Canonical source is **AGENTS.md**; **CONVENTIONS.md** is the
portable summary the others mirror.

- **AGENTS.md** — open standard read by OpenAI Codex, Cursor, Zed, Amp, Jules, Factory, and more.
- **CLAUDE.md** — Claude Code.
- **OpenCode**: `opencode.json` (model + small_model = `ollama/llama3.1:8b`; commands jarvis,
  research, desktop, health, test) + `.opencode/agent/` (jarvis primary; research/coding/security/
  memory subagents) + `.opencode/commands/` (the five slash commands, templates use `$ARGUMENTS`).
- **Cursor**: `.cursor/rules/jarvis.mdc` (alwaysApply).
- **GitHub Copilot**: `.github/copilot-instructions.md`.
- **Gemini CLI**: `GEMINI.md`.
- **Windsurf**: `.windsurfrules`.  **Cline / Roo**: `.clinerules`.  **Aider**: `.aider.conf.yml`
  (reads `CONVENTIONS.md`).

When you change a rule, update AGENTS.md + CONVENTIONS.md and keep the per-tool mirrors in sync.

## Tests

- Run: `python -m pytest tests/ -q --tb=no` (config in `pytest.ini`).
- **Known-failing baseline** (also fails on untouched upstream — NOT regressions):
  `tests/test_hardening.py` (3: `test_9b_run_command_is_now_class_b_and_held`,
  `test_11_self_modification_forbidden`, `test_gate_classifies_by_action_not_phrasing`) and
  `tests/test_core.py::test_agentic_brain_chains_actions`. These encode an older/stricter
  permission vocabulary than the shipped gate; do not "fix" them by weakening the gate.
- `llm_router.complexity_score()` and `classify_task()` are covered by tests — do not change
  their behavior.

## Platform note

Development targets **Windows 10/11**. SAPI voice, Task Scheduler, UI Automation
(`uiautomation`), and application-control features cannot be exercised on Linux CI/sandboxes —
say so explicitly instead of claiming verification.
