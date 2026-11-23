#!/usr/bin/env python3
"""JARVIS OS — entry point.

  python main.py             -> live dashboard with voice (same as: python gui.py)
  python main.py --terminal  -> terminal mode (text only, no browser)
  python main.py --port 9000 -> dashboard on a custom port
  python main.py --no-open   -> start the dashboard but don't auto-open the browser

Designed to never hard-crash on missing optional dependencies.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# UTF-8 console on Windows (Claude replies contain emoji cp1252 can't print)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


_PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY", "NVIDIA_API_KEY",
                  "GEMINI_API_KEY", "FIRECRAWL_API_KEY")
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def _read_env_file() -> dict:
    """Parse .env directly (dotenv is optional). The FILE is the source of truth so a
    stale shell var can't mask a missing key. Never prints or logs the values."""
    cfg = {}
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    return cfg


def _ollama_alive() -> bool:
    """True when a local Ollama server answers /api/tags (free, offline brain)."""
    import urllib.request
    try:
        with urllib.request.urlopen(_OLLAMA_HOST + "/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _startup_check() -> None:
    """Fail fast ONLY when no brain exists anywhere.

    JARVIS boots with any reachable brain:
      * an Anthropic key (full Claude experience), or
      * any provider key (PERPLEXITY / NVIDIA / GEMINI / FIRECRAWL), or
      * a live local Ollama server at http://127.0.0.1:11434 (free, no key at all).
    Pure-stdlib check — the anthropic package is NOT required in local mode."""
    cfg = _read_env_file()
    brains = []

    for name in _PROVIDER_KEYS:
        val = cfg.get(name) or os.environ.get(name, "")
        min_len = 20 if name == "ANTHROPIC_API_KEY" else 8
        if len(val) >= min_len:
            brains.append(name.split("_API_KEY")[0].lower())

    if _ollama_alive():
        brains.append("ollama")

    if not brains:
        print("\n[JARVIS STARTUP FAILURE] No brain found.")
        print("  X No API key in .env / environment, and no local Ollama server at " + _OLLAMA_HOST)
        print("\n  Easiest free fix (fully local, no keys, no cost):")
        print("    1. Install Ollama:        https://ollama.com/download/windows")
        print("    2. Pull a brain model:    ollama pull llama3.1:8b")
        print("    3. Pull eyes (optional):  ollama pull llava:7b")
        print("    4. Start JARVIS again:    python main.py")
        print("\n  Or add any key to the .env file (ANTHROPIC_API_KEY, PERPLEXITY_API_KEY,")
        print("  NVIDIA_API_KEY, GEMINI_API_KEY, FIRECRAWL_API_KEY), then restart JARVIS.\n")
        sys.exit(1)
    print("[JARVIS] Brains online: " + ", ".join(dict.fromkeys(brains)))


def _run_terminal() -> int:
    try:
        from core.orchestrator import Orchestrator
        from channels.terminal_channel import TerminalChannel
    except Exception as e:
        print("JARVIS OS failed to start (import error):", e)
        return 1
    try:
        orch = Orchestrator()
    except Exception as e:
        print("JARVIS OS ONLINE (degraded) — core init error:", e)
        return 1
    try:
        orch.start_autonomy_if_enabled()
    except Exception:
        pass
    try:
        print(orch.startup_greeting())
    except Exception:
        pass
    TerminalChannel(orch, orch.logger).run()
    return 0


def _run_dashboard() -> int:
    try:
        from channels.web_server import serve
    except Exception as e:
        print("JARVIS dashboard failed to start (import error):", e)
        return 1
    port = 8765
    for i, a in enumerate(sys.argv):
        if a in ("--port", "-p") and i + 1 < len(sys.argv):
            try:
                port = int(sys.argv[i + 1])
            except ValueError:
                pass
    no_open = "--no-open" in sys.argv
    serve(port=port, open_browser=not no_open)
    return 0


def _ensure_headroom() -> None:
    """Make the Headroom token-compression proxy robust: if .env points JARVIS at it,
    ping it, start it if down, and fall back to DIRECT Anthropic if it still won't come up —
    so JARVIS never breaks when the proxy is missing."""
    import urllib.request
    cfg = {}
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    base = cfg.get("ANTHROPIC_BASE_URL", "")
    if not base or "8787" not in base and "headroom" not in base.lower():
        if base:
            os.environ["ANTHROPIC_BASE_URL"] = base
        return
    port = cfg.get("HEADROOM_PORT", "8787")
    hdir = cfg.get("HEADROOM_DIR", "")
    health = f"http://127.0.0.1:{port}/health"

    def _up() -> bool:
        try:
            with urllib.request.urlopen(health, timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    if not _up() and hdir and os.path.isdir(hdir):
        try:
            import subprocess, time
            flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            subprocess.Popen(["uv", "run", "--directory", hdir, "headroom", "proxy",
                              "--port", str(port)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags)
            for _ in range(12):
                time.sleep(1)
                if _up():
                    break
        except Exception as e:
            print(f"[JARVIS] Headroom start failed: {e}")

    if _up():
        os.environ["ANTHROPIC_BASE_URL"] = base
        print("[JARVIS] Headroom proxy ON — token compression active (60-95% fewer tokens).")
    else:
        # Block .env re-adding it; force DIRECT Anthropic so JARVIS still works.
        os.environ["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com"
        print("[JARVIS] Headroom proxy unreachable — using direct Anthropic (no break).")


def main() -> int:
    _startup_check()
    _ensure_headroom()
    argv = sys.argv[1:]
    # Terminal mode only if explicitly requested; the GUI dashboard is the default.
    if any(a in ("--terminal", "--cli", "--text", "-t") for a in argv):
        return _run_terminal()
    return _run_dashboard()


if __name__ == "__main__":
    raise SystemExit(main())
