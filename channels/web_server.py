"""Local web server bridge for the JARVIS dashboard.

Pure standard library (http.server) — no Flask, no pip installs. Serves the
Iron-Man-style dashboard and exposes a tiny JSON API that drives the same
Orchestrator used by terminal mode. Voice runs in the browser (Web Speech API),
so there's nothing to install for speech.

Endpoints:
  GET  /                -> hud.html (classic dashboard at /classic)
  GET  /api/bootstrap   -> banner, agents, tools, status, llm status
  GET  /api/brains      -> brain list for the Setup panel (key PRESENCE only, never values)
  POST /api/command     -> {"text": "..."} -> {"reply": "...", "status": {...}}
  POST /api/brain       -> {"name": "ollama"|"claude"|...|"auto", "model": "..."} -> switch brain
"""
from __future__ import annotations
import json, os, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.orchestrator import Orchestrator

UI_PATH = os.path.join("ui", "hud.html")          # movie-grade JARVIS HUD (default)
CLASSIC_PATH = os.path.join("ui", "dashboard.html")  # classic dashboard at /classic
SETTINGS_PATH = os.path.join("config", "settings.json")
_LOCK = threading.Lock()


def _brains_payload(llm) -> dict:
    """Describe every configured brain for the Setup panel.

    SAFETY: returns only whether each key is PRESENT (bool) and the ENV VAR NAME —
    never the key value. Secrets stay in .env / the environment and are never sent
    to the browser, stored in config, or logged."""
    if llm is None:
        return {"active": "", "smart_routing": False, "brains": []}
    full = getattr(llm, "full", {}) or {}
    profiles = full.get("profiles") or {}
    brains = []
    for name in llm.profiles():
        prof = profiles.get(name, {}) or {}
        env = prof.get("api_key_env", "") or ""
        provider = prof.get("provider", "") or ""
        key_present = (not env) or bool(os.environ.get(env))
        brains.append({
            "name": name,
            "provider": provider,
            "model": prof.get("model", ""),
            "key_env": env,           # the NAME of the env var only — never its value
            "key_present": key_present,
            "local": provider == "ollama",
            "usable": key_present,
        })
    return {"active": getattr(llm, "active", ""),
            "smart_routing": not getattr(llm, "pinned", False),
            "brains": brains}


def _persist_brain_choice(cfg_path, active=None, model=None) -> bool:
    """Persist the chosen brain (and optional model override) to settings.json.
    Writes NON-SECRET config only — which profile is active, and a model string.
    Never writes keys."""
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    llm_cfg = cfg.setdefault("llm", {})
    if active:
        llm_cfg["active"] = active
        if model:
            llm_cfg.setdefault("profiles", {}).setdefault(active, {})["model"] = model
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except OSError:
        return False


class _Handler(BaseHTTPRequestHandler):
    orch: Orchestrator = None  # set by serve()

    # quieter logging
    def log_message(self, fmt, *args):
        try:
            self.orch.logger.info("web " + (fmt % args))
        except Exception:
            pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Client closed the connection before we finished (e.g. superseded
            # request, page refresh). Nothing to send — ignore quietly.
            pass

    def _status_dict(self):
        o = self.orch
        return {
            "version": o.settings.get("version", "?"),
            "agents": len(o.agents.names()),
            "tools": len(o.tools.names()),
            "open_tasks": o.tasks.open_count(),
            "voice_on": o.voice_on,
            "llm": o.llm.status(),
            "llm_enabled": o.llm.enabled,
            "brain": o.llm.active,
            "mode": getattr(o, "mode", "balanced"),
            "live": o.live.snapshot() if hasattr(o, "live") else {},
        }

    def _handle_brain_switch(self):
        """POST /api/brain {"name":"ollama"|"claude"|...|"auto", "model":"optional"}.
        Switches the live brain and persists the (non-secret) choice. Keys are never
        accepted here — this only picks a profile and, optionally, its model string."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            data = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            self._send(400, json.dumps({"error": "bad request"}))
            return
        name = (data.get("name") or "").strip().lower()
        model = (data.get("model") or "").strip()
        llm = self.orch.llm

        # "auto" releases any manual pin -> smart per-request routing (nothing to persist)
        if name in ("auto", "smart", "automatic"):
            try:
                llm.auto()
            except Exception:
                pass
            self._send(200, json.dumps({
                "ok": True,
                "reply": "Smart routing engaged, sir - I'll pick the best brain per request.",
                "brains": _brains_payload(llm), "status": self._status_dict()}))
            return

        if not name or not llm.switch(name):
            self._send(400, json.dumps({
                "ok": False, "error": f"Unknown brain '{name}'.",
                "brains": _brains_payload(llm)}))
            return
        if model:
            llm.model = model
        _persist_brain_choice(SETTINGS_PATH, active=name, model=model or None)

        try:
            key_ok = llm._key_ok()
        except Exception:
            key_ok = True
        env = getattr(llm, "api_key_env", "")
        tail = "" if key_ok else f" (but env {env} is missing - add it to your .env)"
        label = "Local brain engaged" if getattr(llm, "provider", "") == "ollama" else f"Switched to {name}"
        reply = f"{label}, sir ({getattr(llm, 'model', '')}){tail}."
        self._send(200, json.dumps({
            "ok": True, "reply": reply,
            "brains": _brains_payload(llm), "status": self._status_dict()}))

    def do_GET(self):
        if self.path in ("/", "/index.html", "/dashboard"):
            try:
                with open(UI_PATH, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "<h1>dashboard.html not found</h1>", "text/html")
            return
        if self.path == "/classic":
            try:
                with open(CLASSIC_PATH, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "<h1>dashboard.html not found</h1>", "text/html")
            return
        if self.path == "/api/greeting":
            o = self.orch
            try:
                greet = o._time_greeting()
                recap = ""
                try:
                    eps = o.jmem.recent_episodes(n=1)   # v3: situational recall on boot
                    if eps:
                        recap = " Last session: " + (eps[-1].get("summary", "")[:120])
                except Exception:
                    pass
                briefing = ""
                try:
                    briefing = o.startup_greeting()
                except Exception:
                    pass
                payload = {"greeting": greet + recap, "slot": o._greeting_slot(), "briefing": briefing}
            except Exception:
                payload = {"greeting": "", "slot": "", "briefing": ""}
            self._send(200, json.dumps(payload)); return
        if self.path == "/api/status":
            self._send(200, json.dumps(self._status_dict()))
            return
        if self.path == "/api/brains":
            self._send(200, json.dumps(_brains_payload(self.orch.llm)))
            return
        if self.path == "/api/alerts":
            try:
                alerts = self.orch.drain_alerts()
            except Exception:
                alerts = []
            self._send(200, json.dumps({"alerts": alerts}))
            return
        if self.path == "/api/bootstrap":
            o = self.orch
            payload = {
                "banner": o.settings.get("boot_banner", "JARVIS OS ONLINE"),
                "agents": o.agents.describe(),
                "tools": o.tools.names(),
                "status": self._status_dict(),
            }
            self._send(200, json.dumps(payload))
            return
        if self.path.startswith("/api/tts"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            text = (q.get("text", [""])[0]).strip()
            lang = (q.get("lang", [""])[0]).strip() or None
            eng = getattr(self.orch, "voice_engine", None)
            if eng and text:
                try:
                    fp = eng.synth_to_file(text, lang=lang)
                    if fp:
                        with open(fp, "rb") as f:
                            self._send(200, f.read(), "audio/mpeg")
                        return
                except Exception:
                    pass
            self._send(204, b"", "audio/mpeg")   # no neural audio -> HUD uses browser voice
            return
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path == "/api/brain":
            self._handle_brain_switch()
            return
        if self.path != "/api/command":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            text = (json.loads(raw).get("text") or "").strip()
        except (ValueError, json.JSONDecodeError):
            self._send(400, json.dumps({"error": "bad request"}))
            return
        if not text:
            self._send(200, json.dumps({"reply": "Say something, Master.", "status": self._status_dict()}))
            return
        # No module lock here: orch.handle() is now single-flight internally (it claims a
        # turn epoch, serializes on its own lock, and DROPS a turn that a newer command
        # supersedes). Wrapping it in _LOCK would block a newer command from claiming its
        # epoch until the old one finished — defeating supersede. So call it directly.
        try:
            reply = self.orch.handle(text)
        except Exception as e:
            reply = f"[!] Error (logged): {e}"
        if not reply:
            # Superseded by a newer command (or empty) — tell the client to ignore this
            # stale turn so it never renders or speaks a previous answer.
            self._send(200, json.dumps({"superseded": True, "reply": "",
                                        "status": self._status_dict()}))
            return
        payload = {"reply": reply, "status": self._status_dict(),
                   "running": self.orch.running}
        self._send(200, json.dumps(payload))


def serve(host="127.0.0.1", port=8765, open_browser=True):
    orch = Orchestrator()
    _Handler.orch = orch
    try:
        orch.start_monitor()
    except Exception:
        pass
    try:
        orch.start_autonomy_if_enabled()
    except Exception:
        pass
    httpd = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}/"
    print("=" * 56)
    print(f"   {orch.settings.get('boot_banner', 'JARVIS OS ONLINE')}")
    print(f"   Dashboard live at:  {url}")
    print("   Voice runs in your browser (use Chrome or Edge).")
    print("   Press Ctrl+C here to stop the server.")
    print("=" * 56)
    if open_browser:
        try:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nJARVIS dashboard stopped. Goodbye, Master.")
    finally:
        httpd.server_close()
