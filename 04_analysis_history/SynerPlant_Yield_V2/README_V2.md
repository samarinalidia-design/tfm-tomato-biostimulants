# SynerPlant Yield V2 — how to use (no programming needed)

**Primary target:** fruit-yield lnRR = ln(Yield under stress + biostimulant / Yield under the same stress without it).
Secondary target (biomass) is unchanged from V1 and was not re-modelled in V2.

## Two buttons
| What | How |
|---|---|
| Rebuild everything (checks → corrections → datasets → training → intervals → figures → freeze) | double-click `RUN_ALL_WINDOWS.bat` (≈20 min) |
| Look at the results | double-click `OPEN_DASHBOARD_WINDOWS.bat` (opens http://127.0.0.1:8502 on this computer only) |

To finish the release, open `audit/HUMAN_AUDIT_V2_PACKAGE.xlsx` and fill in the verdict and your name for the
**24 rows marked `required_sample = TRUE`**. Then run `RUN_ALL_WINDOWS.bat` again. The freeze status changes from
`READY_FOR_HUMAN_AUDIT` to `READY_TO_USE` only if every required row is `CORRECT`.

## What is where
| Folder / file | Content |
|---|---|
| `db/TFM_V2_WORKING.sqlite` | corrected working copy of the V1 freeze database (V1 itself untouched); new tables `v2_changelog`, `v2_decisions`, `v2_yield_contrasts` |
| `audit/corrections_register.json` | every V2 decision with source evidence (policy A–D) |
| `audit/UNRESOLVED_QUEUE.csv` | open scientific questions and the safe choice taken meanwhile |
| `audit/integrity_report.json`, `audit/integrity_details/` | relational / acceptance checks |
| `audit/evidence/` | page renders, vector and raster re-digitisation for P0/P1 cases |
| `outputs/data/` | analysis sets (PRIMARY_EXPANDED, STRICT_SENSITIVITY, QUALITY_CORE, sensitivity sets, V1_EQUIVALENT), contrast register with inclusion/exclusion reasons, feature completeness, V1↔V2 comparison (CSV) |
| `outputs/ml/` | grouped-CV predictions, fold metrics, Optuna history, model comparison, ablation, subgroup and per-study errors, selection report |
| `outputs/uncertainty/` | interval methods, empirical coverage, widths, deployed intervals |
| `outputs/meta/` | meta-analytic CI and prediction intervals |
| `outputs/model/` | saved model + manifest + model card |
| `outputs/figures/` | publication figures (PNG 300 dpi, SVG, PDF) |
| `exports/DATA_FREEZE_V2_*` | freeze manifest with SHA-256 of every file and the acceptance gates |
| `FINAL_REPORT_EN.md` | the report (also shown in the dashboard) |
| `src/` | the pipeline (s01 … s11), run in order by RUN_ALL |

## Rules kept
Original V1 database, archives, code and results are read-only. Agent checks are labelled `AUTO_VERIFIED_V2`, never
`HUMAN_VERIFIED`. The independent 2024–2026 TEST was never opened.
