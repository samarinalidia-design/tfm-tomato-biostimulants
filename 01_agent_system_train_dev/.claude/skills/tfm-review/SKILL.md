---
name: tfm-review
description: Prepare the single consolidated human review package required by TFM
disable-model-invocation: true
allowed-tools: Read Agent Bash(python tools/tfm.py *) Bash(python3 tools/tfm.py *)
---

Run `review-export work/human_review/questions.csv` for irreducible questions. When global QA is complete, run `human-audit-export`. N is unique retained contrasts in evidence_long, k=min(N,max(20,ceil(.15*N))). The exported arm evidence includes all four factorial cells. Explain that the author or a named human expert fills verdict/reviewer/notes and imports outside the agent session. Agents cannot sign the human audit. Legacy manual 35-study gold is optional and not a startup dependency.
