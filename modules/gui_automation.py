"""JARVIS v6.0 — GUI automation via pyautogui/pygetwindow."""
from __future__ import annotations
import time

try: import pyautogui; pyautogui.FAILSAFE = True; _PAG = True
except ImportError: _PAG = False

try: import pygetwindow as gw; _GW = True
except ImportError: _GW = False


def take_screenshot_and_analyze(prompt: str = "Describe what you see") -> str:
    """Capture the screen and analyze it via the vision brain (Ollama locally, Claude with a key)."""
    if not _PAG: return "pyautogui not installed."
    try:
        from modules.display_control import take_screenshot
        from modules.vision_engine import analyze_image
        path = take_screenshot()
        return analyze_image(path, prompt)
    except Exception as e: return f"Vision error: {e}"


def click_element(description: str, button: str = "left", confirmed: bool = False) -> str:
    """Click an element described IN WORDS — no coordinates needed.

    Pipeline: screenshot -> vision brain returns the element's coordinates
    (free/locally via llava:7b on Ollama; Claude when keyed) -> pyautogui click.
    FAILSAFE stays on: slam the mouse to the top-left corner to abort mid-move.
    Best-effort by nature — verify the outcome afterwards (e.g. VisionCore.verify)."""
    if not _PAG: return "pyautogui not installed."
    desc = (description or "").strip()
    if not desc: return "Click what? Describe the element, e.g. 'the Submit button'."
    try:
        from modules.vision_engine import locate_element
        loc = locate_element(desc)
        if not loc.get("found"):
            return f"I couldn't find '{desc}' on screen — {loc.get('detail', 'not visible')}"
        x, y = loc["x"], loc["y"]
        pyautogui.click(x, y, button=button)
        label = f" ({loc['label']})" if loc.get("label") else ""
        return f"Clicked {button} on '{desc}'{label} at ({x},{y})"
    except Exception as e:
        return f"click_element error: {e}"


def get_open_windows() -> list[str]:
    if not _GW: return ["pygetwindow not installed"]
    try: return [w.title for w in gw.getAllWindows() if w.title.strip()]
    except Exception as e: return [f"Error: {e}"]


def focus_window(title: str) -> str:
    if not _GW: return "pygetwindow not installed."
    try:
        wins = gw.getWindowsWithTitle(title)
        if not wins: return f"No window '{title}'"
        wins[0].activate(); time.sleep(0.3)
        return f"Focused: {wins[0].title}"
    except Exception as e: return f"Focus error: {e}"


def close_window(title: str, confirmed: bool = False) -> str:
    if not _GW: return "pygetwindow not installed."
    try:
        wins = gw.getWindowsWithTitle(title)
        if not wins: return f"No window '{title}'"
        wins[0].close(); return f"Closed: {title}"
    except Exception as e: return f"Close error: {e}"


def click_at(x: int, y: int, button: str = "left",
             confirmed: bool = False) -> str:
    if not _PAG: return "pyautogui not installed."
    try:
        pyautogui.click(x, y, button=button)
        return f"Clicked {button} at ({x},{y})"
    except Exception as e: return f"Click error: {e}"


def type_text(text: str, interval: float = 0.05, confirmed: bool = False) -> str:
    if not _PAG: return "pyautogui not installed."
    try:
        pyautogui.typewrite(text, interval=interval)
        return f"Typed: {text[:40]}"
    except Exception as e: return f"Type error: {e}"


def press_hotkey(*keys: str, confirmed: bool = False) -> str:
    if not _PAG: return "pyautogui not installed."
    try:
        pyautogui.hotkey(*keys)
        return f"Pressed: {'+'.join(keys)}"
    except Exception as e: return f"Hotkey error: {e}"
