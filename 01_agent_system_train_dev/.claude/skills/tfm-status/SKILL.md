---
name: tfm-status
description: Report live A399 progress without claiming readiness prematurely
disable-model-invocation: true
allowed-tools: Read Agent Bash(python tools/tfm.py *) Bash(python3 tools/tfm.py *)
---

Run `python tools/tfm.py status`. Report closed/399, source problems, unresolved slots/tasks/questions and retained contrast counts by endpoint. Technical queue completion, scientific closure and ready_to_use are different. Use `gates` only when needed; it rehashes originals. Never infer accuracy or ready-to-use from agent agreement alone.
