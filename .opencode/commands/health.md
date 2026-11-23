---
description: Check brains, models, and system health
agent: jarvis
---

Run the health check for: $ARGUMENTS

Steps:
1. `python -c "import llm_router; print(llm_router.health_report())"` — brains + Ollama status.
2. `ollama list` — confirm llama3.1:8b (brain) and llava:7b (eyes) are pulled.
3. Report: which brains are online, active model, missing models with the exact pull commands,
   and anything in the environment that blocks startup. Never print key values — only whether
   each key is present.
