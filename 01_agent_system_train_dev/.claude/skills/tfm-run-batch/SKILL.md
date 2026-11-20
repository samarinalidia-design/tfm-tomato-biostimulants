---
name: tfm-run-batch
description: Process a small diagnostic batch then continue autonomously when finalization
  is requested
disable-model-invocation: true
allowed-tools: Read Agent Bash(python tools/tfm.py *) Bash(python3 tools/tfm.py *)
---

For an explicitly requested diagnostic batch, claim at most 4 tasks and delegate exact named subagents. Otherwise use `/tfm-finalize`, which continues without author batch selection. Always keep independent readers separate, check actual submission status, release orphaned leases and checkpoint.
