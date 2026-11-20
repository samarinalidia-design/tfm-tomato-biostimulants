---
name: tfm-finalize
description: Autonomously finish the frozen A399 agent queue and prepare final release
disable-model-invocation: true
allowed-tools: Read Agent Bash(python tools/tfm.py *) Bash(python3 tools/tfm.py *)
---

Continue the existing SQLite queue; never re-import/restart it. User has authorized autonomous routine decisions. Do not ask which batch to process.

1. Read CLAUDE.md, pipeline configuration and the checkpoint. Run `python tools/tfm.py status`.
2. Before global processing run `python tools/tfm.py pilot-select`. If the pilot is PENDING, process its selected study IDs first with `claim --study <ID> --limit 1`, at most four workers total. Continue each pilot study through design, critical extraction/verification, moderator verification and RoB. Run contrasts/validate and `pilot-finish`. Correct resolvable technical errors autonomously. If a pilot study has a genuine external blocker, preserve it and continue other A399 work; final release still requires a completed pilot. Do not ask the user to approve pilot batches.
3. Claim at most 4 tasks with `python tools/tfm.py claim --limit 4 --owner orchestrator`.
4. Launch the exact named project subagent for each packet. Pass only task ID/type, study ID, packet path and output path. Keep A/B and FA/FB in distinct runs, without passing outputs across. Resume partial workers until they submit or release. No idle handoff to user after a successful batch.
5. Collect accepted/rejected/released states. Fix operational retries within the 3-attempt bound. A worker that ends without submission/release must be released with its exact reason. Continue independent studies.
6. `python tools/tfm.py checkpoint`. Repeat steps 2–6 while any READY tasks exist. If leases are active, collect/resume those workers; do not call this completion. Failed tasks/source blockers are aggregated; do not erase them by cancelling to force PASS.
7. Once extraction work is exhausted: `python tools/tfm.py contrasts`, `python tools/tfm.py validate`, `python tools/tfm.py qa-seed`. Process the new QA tasks in the same loop. Corrections must invalidate/reverify affected records. Repeat global validation after corrections. `python tools/tfm.py close-all` only after validation; no --force.
8. Run gates. If only genuine unresolved external/scientific blockers remain, produce one review CSV with `review-export work/human_review/questions.csv`, a DRAFT export, and a concise list of exact IDs/actions; do not ask for every routine item. If no blockers remain except the human audit, run `human-audit-export` and explain the one prepared human review step using work/human_review/audit.xlsx in INSTALL_RU.md. Do not enter verdicts.
9. After the human imports their decisions and asks to continue, rebuild/validate and run final `python tools/tfm.py export`. A result is final only when status=READY_TO_USE and all current gates pass. Verify MANIFEST file hashes with `verify-build` if available; no claim of completed 399-source processing before it occurs.

When an account quota, context, device sleep or service error interrupts: persist checkpoint and explain `claude --continue` then `/tfm-finalize`. Do not promise unattended continuation across platform/account limits.

Do not hand routine number reading or error-bar digitization to the human. Retry from original PDF pages at higher resolution/vector geometry, inspect captions/Methods/supplementary and adjudicate independent readings first. Mean-only legacy graph outputs must be revisited for bars. Missing bar type uses SE with explicit USER_ASSUMED_SE metadata. Keep other studies advancing while a record is being repaired. Missing/unreadable uncertainty can be documented without discarding a verified point target or inventing a variance. A real unresolved scientific contradiction affecting retained evidence is consolidated, not asked per row.
