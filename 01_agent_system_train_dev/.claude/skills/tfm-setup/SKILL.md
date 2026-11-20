---
name: tfm-setup
description: Verify the already installed project and seed the authorized A399 queue
disable-model-invocation: true
allowed-tools: Read Agent Bash(python tools/tfm.py *) Bash(python3 tools/tfm.py *)
---

Installation/configuration is performed by the user once with the supplied INSTALL_RU.md. Do not install packages or edit protected files during the agent run. Read work/SETUP_REPORT.json if present, then `python tools/tfm.py status`. If the baseline is not imported, report the exact installation step; do not silently create a substitute workbook. With a prepared queue, continue `/tfm-finalize`. Missing original source access is a concrete consolidated blocker, not permission to skip verification.
