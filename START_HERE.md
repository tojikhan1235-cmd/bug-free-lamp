# START HERE — JARVIS on Windows, 100% free (no API keys)

This walkthrough gets JARVIS running on your Windows 10/11 PC with a **local brain**
(Ollama) driven by **OpenCode**. Total cost: $0. Time: ~20 minutes, most of it model
downloads.

Prefer Claude instead? Put an `ANTHROPIC_API_KEY` in `.env` and everything upgrades
automatically — the local setup below still works as the free fallback.

---

## 1. Install Ollama (the free brain)

1. Download the Windows installer: <https://ollama.com/download/windows>
2. Run it. Ollama starts automatically and listens on `http://127.0.0.1:11434`.
3. Open **PowerShell** and pull the two models JARVIS uses:

```powershell
ollama pull llama3.1:8b    # the brain (thinking, planning, chat) — ~4.7 GB
ollama pull llava:7b       # the eyes (screenshots, vision, click-by-description) — ~4.7 GB
```

Check they're there:

```powershell
ollama list
```

> RAM note: 8 GB minimum, 16 GB comfortable. A smaller brain works too:
> `ollama pull llama3.2:3b`, then set `OLLAMA_MODEL=llama3.2:3b` in `.env`.

## 2. Install Python 3.11+

1. <https://www.python.org/downloads/windows/> → **Windows installer 64-bit**.
2. On the first screen, tick **"Add python.exe to PATH"** (important).
3. Verify in PowerShell: `python --version`

## 3. Get the code + dependencies

```powershell
cd path\to\jarvis-ai-assistant
python -m pip install -r requirements.txt
```

The **core runs on the pure standard library** — if some optional packages fail to install
(pyautogui, opencv, psutil…), JARVIS still boots and tells you honestly what's missing.
For desktop control (screenshots, clicking, typing) you want at least:

```powershell
python -m pip install pyautogui pillow
```

## 4. (Optional) `.env` — only if you have keys

```powershell
copy .env.example .env    # if present, else create .env manually
notepad .env
```

Leave it empty/absent for the free local mode. Add keys only if you have them
(`ANTHROPIC_API_KEY=…`, `PERPLEXITY_API_KEY=…`, etc.). **Never share or commit `.env`** —
it is gitignored.

Useful local-mode overrides (all optional):

```
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_VISION_MODEL=llava:7b
```

## 5. Run JARVIS

```powershell
python main.py              # dashboard (opens http://localhost:8765 in your browser)
python main.py --terminal   # text mode in the console
python main.py --no-open    # dashboard without auto-opening the browser
```

On boot you should see:

```
[JARVIS] Brains online: ollama
```

If instead you get `[JARVIS STARTUP FAILURE] No brain found.`, either Ollama isn't running
(start menu → Ollama, or `ollama serve` in a second PowerShell) or no model is pulled
(`ollama pull llama3.1:8b`).

**Try it:**
- `what's on my screen?` — screenshot → llava describes it
- `click the submit button` — vision locates it on screen, then clicks it (slam the mouse
  into the **top-left corner** any time to emergency-abort — pyautogui FAILSAFE)
- `open notepad and type hello` — app control
- `health` — brain/model status report

## 6. Install OpenCode (drive JARVIS from your terminal/IDE)

1. Install: <https://opencode.ai/docs/> (Windows: `winget install anomalyco.opencode` or the
   npm route `npm i -g opencode-ai`).
2. In the repo folder, run `opencode`. It reads `opencode.json` automatically — model
   `ollama/llama3.1:8b`, no API key needed (OpenCode talks to your local Ollama).
3. Agents live in `.opencode/agent/` (jarvis = primary; research, coding, security, memory =
   subagents).
4. Slash commands:

```
/jarvis summarise my notes folder
/research best free TTS engines for Windows
/desktop click the Submit button in the open form
/health
/test
```

## 7. Tests

```powershell
python -m pytest tests/ -q --tb=no
```

**Known-failing baseline** (also fails on the untouched upstream repo — not your setup's
fault, and do NOT weaken the permission gate to "fix" them):
`tests/test_hardening.py` (3) + `tests/test_core.py::test_agentic_brain_chains_actions`.
See `AGENTS.md` for details.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No brain found` on startup | Start Ollama (`ollama serve`) and `ollama pull llama3.1:8b` |
| Vision says model missing | `ollama pull llava:7b` |
| Slow first reply | First call loads the model into RAM; later calls are faster |
| `pyautogui not installed` | `python -m pip install pyautogui` |
| Clicks land in the wrong place | Vision grounding is best-effort; keep the target window in focus and unobstructed; JARVIS verifies after clicking |
| Mouse runaway | Slam mouse to **top-left corner** (FAILSAFE abort) |
| Windows features (voice/Scheduler) don't work on Linux | Expected — they're Windows-only and can't be tested in Linux sandboxes |

## Safety

JARVIS has a three-tier permission system (`security.py`, `core/permission_gate.py`):
destructive/financial/external actions require your explicit confirmation; self-modification
requires double confirmation; some actions are hard-blocked. All confirmed actions are
written to a tamper-evident audit log (`security/audit_log.jsonl`).
