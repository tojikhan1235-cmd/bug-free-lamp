"""JARVIS v6.0 — Computer vision: OCR, face detection, object detection, screen reader."""
from __future__ import annotations
import os, base64, json, urllib.request
from pathlib import Path

try: import cv2; _CV2 = True
except ImportError: _CV2 = False

try: from PIL import Image; _PIL = True
except ImportError: _PIL = False

# Local (free) vision brain — used whenever there is no ANTHROPIC_API_KEY.
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "llava:7b")
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def _ollama_analyze(b64: str, prompt: str) -> str:
    """Analyze an image with a local Ollama vision model (e.g. llava:7b). Pure stdlib."""
    payload = {
        "model": OLLAMA_VISION_MODEL,
        "stream": False,
        "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        "options": {"temperature": 0.2, "num_predict": 1024},
    }
    req = urllib.request.Request(
        _OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.loads(r.read().decode("utf-8"))
    return (body.get("message") or {}).get("content", "").strip()


def screenshot_to_text() -> str:
    """Take screenshot, extract all readable text using the vision brain."""
    try:
        from modules.display_control import take_screenshot
        path = take_screenshot()
        return analyze_image(path, "Extract and return ALL text visible in this image. Be thorough.")
    except Exception as e: return f"Screen read error: {e}"


def analyze_image(path: str, prompt: str = "Describe this image in detail.") -> str:
    """Send image to the vision brain: local Ollama (no key needed) or Claude."""
    try:
        with open(path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode()
    except OSError as e:
        return f"Vision error: cannot read image {path}: {e}"

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        # Local mode — free vision via Ollama
        try:
            out = _ollama_analyze(b64, prompt)
            if out:
                return out
            return (f"Local vision ({OLLAMA_VISION_MODEL}) returned nothing. "
                    f"Pull it with: ollama pull {OLLAMA_VISION_MODEL}")
        except Exception as e:
            return (f"Local vision error: {e}. Is Ollama running with a vision model? "
                    f"Fix: ollama serve  +  ollama pull {OLLAMA_VISION_MODEL}")
    try:
        import anthropic
        ext = Path(path).suffix.lower().lstrip(".")
        mime = {"jpg":"image/jpeg","jpeg":"image/jpeg",
                "png":"image/png","gif":"image/gif","webp":"image/webp"}.get(ext,"image/png")
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1024,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":mime,"data":b64}},
                {"type":"text","text":prompt}
            ]}])
        return r.content[0].text
    except Exception as e: return f"Vision API error: {e}"


def detect_faces(path: str) -> dict:
    """Detect faces in image using OpenCV. Returns count and bounding boxes."""
    if not _CV2: return {"error": "opencv-python not installed", "faces": 0}
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        img = cv2.imread(path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 4)
        return {"faces": len(faces),
                "boxes": [{"x":int(x),"y":int(y),"w":int(w),"h":int(h)}
                           for (x,y,w,h) in faces]}
    except Exception as e: return {"error": str(e), "faces": 0}


def detect_objects(path: str) -> str:
    """Use Claude vision to detect objects in image."""
    return analyze_image(path, "List all objects visible in this image, one per line.")


def ocr_image(path: str) -> str:
    """Extract text from image. Uses Claude vision (most accurate)."""
    return analyze_image(path, "Extract all text from this image. Return only the text, no commentary.")


def monitor_screen(interval: int = 10, prompt: str = "Describe any important changes") -> None:
    """Continuous screen monitoring — runs in a separate thread."""
    import time, queue
    prev_text = ""
    while True:
        try:
            current = screenshot_to_text()
            if current != prev_text and len(current) > 20:
                prev_text = current
        except Exception: pass
        time.sleep(interval)


def identify_face(path: str) -> str:
    """Face identification using DeepFace. Requires prior consent and face database."""
    try:
        from deepface import DeepFace
        result = DeepFace.find(img_path=path, db_path="memory/face_db",
                               enforce_detection=False)
        if result and len(result[0]) > 0:
            return f"Identity match found: {result[0].iloc[0]['identity']}"
        return "No match in face database."
    except ImportError: return "deepface not installed."
    except Exception as e: return f"Face ID error: {e}"
