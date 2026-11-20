---
name: tfm-export
description: Run current checks and atomically export only a qualified data freeze
disable-model-invocation: true
allowed-tools: Read Agent Bash(python tools/tfm.py *) Bash(python3 tools/tfm.py *)
---

Run contrasts, validate, close-all and gates. If a live gate fails, final export must remain BLOCKED. Use `export --draft` only for a clearly labelled diagnostic build; it is never ready-to-use. Once human review is correctly imported and all checks pass, run `python tools/tfm.py export`; it creates SQLite, Excel, CSV and Parquet atomically with one manifest. Report exact path and current counts. Do not use legacy standalone --xlsx, --force or a stale PASS.
