# Biostimulants for tomato under abiotic stress — evidence database, extraction system and analysis (TFM)

Code, frozen evidence databases and analysis outputs of the master's thesis (TFM, Agrobiología Ambiental)
on the efficacy of biostimulants for tomato (*Solanum lycopersicum*) under abiotic stress:
a verified relational database built with an AI-assisted (Claude multi-agent) extraction system,
three-level meta-analysis and grouped-validation machine learning (version V5, 2026-11-20).

## Repository layout

| Folder | Content |
|---|---|
| `00_extraction_notebooks_v4_3/` | Deterministic document-extraction layer (Docling / PyMuPDF / OCR) and figure-recovery notebooks, V4.3 (outputs stripped). |
| `01_agent_system_train_dev/` | Multi-agent extraction and verification system used for the TRAIN_DEV corpus (399 studies, publications ≤ 2023): agent definitions (`.claude/agents`), guard hooks, validating CLI `tools/tfm.py`, configuration, JSON schemas, tests, documentation (`README_RU.md`, `CLAUDE.md`). |
| `02_agent_system_external_test/` | Same system applied to the temporally independent EXTERNAL_TEST corpus (80 studies, 2024–2026). |
| `03_data_freeze/` | Frozen exports of both databases: analysis marts (`A_*`), `evidence_long`, `contrast_candidates`, covariance of shared controls, QA tables, `acceptance_report.json` and freeze manifest with SHA-256. |
| `04_analysis_history/` | Earlier analysis stages: `SynerPlant_Yield_V2` (audit, corrections register, first models) and `SynerPlant_Yield_V4_HARMONIZATION` (pre-registered V4 analysis and post-hoc test). |
| `05_analysis_train_expansion_v5/` | Current analysis. `v5/` holds the V5 pipeline (scripts `v5_01`–`v5_16`, R meta-analysis, model freeze with SHA-256, results, figures Fig1–Fig22, FigB1–B4, FigM1–M5, Excel workbooks, `README_V5.md`, `SUMMARY_V5_RU.md`); `scripts/`, `data/`, `results/` hold expansion rounds 1–7. `v5/tfm_docx/` contains the code that writes the thesis Methods and Results. |

## Databases (release assets)

The SQLite databases exceed GitHub's file-size limit and are attached to the release
[`data-freeze-v5`](../../releases/tag/data-freeze-v5):

* `TFM_DATABASE_TRAIN_DEV_DATA_FREEZE_20261113.zip` — `TFM_DATABASE_CLASS_A_FINAL.sqlite` + `.xlsx` (TRAIN_DEV);
* `TFM_DATABASE_EXTERNAL_TEST_DATA_FREEZE_20261118.zip` — the same for EXTERNAL_TEST.

SHA-256 of the unzipped files are listed in `RELEASE_ASSETS_AND_EXCLUSIONS.json` and match the freeze manifests in `03_data_freeze/`.

## What is not included

* Full texts, supplements and rendered page images of the source articles (copyright). Every value in the databases
  is traceable to its source by DOI, file identifier, page and locator (`provenance_qa`, `wf_source_receipts`).
* Agent working folders (`work/`, `db/`), virtual environments, intermediate drafts, very large run logs and CSV files
  that duplicate a Parquet file (listed in `RELEASE_ASSETS_AND_EXCLUSIONS.json`).
* The blinded gold-standard study that is currently in progress.

## Reproducing the V5 analysis

Python 3.12 (pandas, numpy, scikit-learn, scipy, matplotlib, openpyxl, pyarrow) and R 4.5 (metafor 5.2, clubSandwich).
Unzip the databases into the corresponding `03_data_freeze/` folders, adjust the input paths at the top of
`05_analysis_train_expansion_v5/v5/scripts/v5_common.py` / `v5_01_build.py`, and run the steps listed in
`05_analysis_train_expansion_v5/v5/README_V5.md`.

## Licence

* **Code** (Python, R, notebooks, agent definitions, hooks, configuration, schemas and tests): MIT License, see [`LICENSE`](LICENSE).
* **Data** (frozen database exports in `03_data_freeze/`, the databases attached to the release `data-freeze-v5`, analysis tables,
  results and figures): Creative Commons Attribution 4.0 International (CC BY 4.0), see [`LICENSE-DATA`](LICENSE-DATA).
* The licences do not cover the source articles, which are not included; extracted values remain attributable to their original publications (DOI in the database).

## How to cite

Samarina, L. (2026). *tfm-tomato-biostimulants: evidence database, AI-assisted extraction system and analysis code for biostimulant
efficacy in tomato under stress (data freeze V5)* [Data set and software]. GitHub. https://github.com/samarinalidia-design/tfm-tomato-biostimulants

## Notes on interpretation

* Variances imputed from the coefficient of variation are flagged; they are never presented as reported by the authors.
* The EXTERNAL_TEST evaluation of V5 is labelled `POST_HOC_TEST_REUSE` because the test set had been used in V4.
