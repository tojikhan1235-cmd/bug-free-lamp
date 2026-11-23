---
description: Run the pytest suite and compare against the known-failing baseline
agent: jarvis
---

Run: `python -m pytest tests/ -q --tb=no`

Known-failing baseline (present on untouched upstream — do NOT weaken the permission gate to
make these pass): tests/test_hardening.py (3 failures) and
tests/test_core.py::test_agentic_brain_chains_actions.

Report: total passed/failed, any failure OUTSIDE the baseline (a regression — investigate and
fix), and for focus areas requested here, dig in with --tb=short: $ARGUMENTS
