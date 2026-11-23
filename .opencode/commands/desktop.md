---
description: Describe or control the desktop — screenshot, vision, click by description, type
agent: jarvis
---

Desktop task: $ARGUMENTS

Look before you act:
1. Screenshot + vision analysis (`modules/vision_engine.py`, llava:7b via Ollama locally).
2. Locate the element by description (`click_element("the Submit button")` / `VisionCore.locate`).
3. Act via the input tools; pyautogui.FAILSAFE stays True (slam mouse to top-left to abort).
4. Look again and verify the result actually happened; report what you see, not what you assume.
