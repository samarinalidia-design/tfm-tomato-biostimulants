# TFM figures — complete current set (fruit-yield target; biomass secondary)

All figures: English, multi-panel, A4 text width (17.8 cm), PNG 300 dpi + PDF + SVG.

| File | TFM section | Content | Origin |
|---|---|---|---|
| Fig1_data_V1_to_V2 | 3.11 / 4.2 | training data before/after the source-verified audit | copy of V2 `outputs/figures_TFM_A4` |
| Fig2_model_performance | 4.8 | V1 vs V2 models, all families, ablation, error sources | copy V2 |
| Fig3_uncertainty | 4.11 | prediction intervals and verified coverage, meta CI vs PI | copy V2 |
| Fig4_stress_gradient | 4.6 | stress-damage gradient and recovered share | copy V2 |
| Fig5_TRAIN_vs_TEST | 4.9 | pre-registered one-time 2024–2026 TEST (yield) | copy V2 |
| Fig6_biomass_V1_to_V2 | 4.8 (secondary) | biomass data, models, intervals | copy V2 |
| Fig7_biomass_TEST | 4.9 (secondary) | one-time biomass TEST | copy V2 |
| Fig8_influence | 4.14 | leave-one-study-out influence | copy V2 |
| Fig9_forest_yield | 4.4 / 4.5 | yield forest plot and subgroups | copy V2 |
| Fig10_forest_biomass | 4.4 / 4.5 | biomass forest plot and subgroups | copy V2 |
| Fig11_publication_bias | 4.14 | funnels, Egger, PET-PEESE, trim-and-fill | copy V2 |
| Fig12_V4_harmonization_TRAIN | 4.8 / 4.14 | harmonization advice tested on TRAIN CV | V4 |
| Fig13_V4_TEST_posthoc | 4.9 / 4.11 | post-hoc second look at TEST (verdict PARTIAL) | V4 |
| Fig14_meta_summary | 4.4 / 4.5 | pooled effects, heterogeneity, moderators, chance of a gain | V4 |
| Fig15_evidence_landscape | 4.2 / 4.3 / 4.6 | stress × biostimulant evidence map, years, systems, countries | V4 |
| Fig16_PRISMA_flow | 4.1 | current PRISMA flow, TRAIN_DEV and TEST (replaces historical Figura 2) | V4 |
| Fig17_learning_curves | 4.9 | grouped learning curves | V4 |
| Fig18_applicability_domain | 4.12 | applicability domain / OOD | V4 |
| Fig19_interactions | 4.6 / 4.7 | S × B and A × B interactions | V4 |
| Fig20_moderators | 4.5 / 4.12 | permutation importance, moderator meta-regressions | V4 |
| Fig21_database | 3.6 / 4.2 | relational database: entities and counts, endpoints, contrast types, provenance and quality, risk of bias | V4 (read-only query of `TFM_V3_WORKING.sqlite`) |
| Table1_V1_vs_V2.csv | 4.2 | V1 → V2 summary | copy V2 |
| Table2_V4.csv | 4.8–4.11 | V2/V3.1 median → V4 multilevel mean | V4 |

## Data files used for training and testing (latest version V3.1)
| File | Sheets |
|---|---|
| SynerPlant_YIELD_TRAIN_TEST_V3.1.xlsx | README · TRAIN 403 contrasts / 69 studies · TRAIN_removed · TRAIN_changes · TEST 36 / 12 · TRAIN_factorial · TEST_factorial |
| SynerPlant_BIOMASS_TRAIN_TEST_V3.1.xlsx | README · TRAIN 762 / 153 · TRAIN_removed · TRAIN_changes · TEST 144 / 28 · TRAIN_factorial · TEST_factorial |

Byte-identical copies of `SynerPlant_Yield_V2/exports/EXCEL_TRAIN_TEST_V3.1/` (SHA-256 checked).
The V4 analyses (Fig12–Fig20) use the yield TRAIN sheet; the V4 composition flags are added in code (`src/h01_features.py`).
Sheets `*_factorial` hold the C/S/B/SB quadruples used for the stress-gradient models (Fig4, Fig5, Fig7).

## Copied, not moved
Fig1–Fig11 and Table1 are **copies**. The originals stay in `SynerPlant_Yield_V2/outputs/figures_TFM_A4`, because their
SHA-256 values are recorded in `SynerPlant_Yield_V2/exports/WORKING_VERSION_V2.0/V3.0/V3.1_*.json`; moving them would
break those integrity records.

## Not included (superseded)
- `SynerPlant_Local_ML_Starter/SynerPlant_Local_ML/outputs/{yield,biomass,run1_D1-D4_before_D5}/figures_TFM` and
  `outputs/statistics/{yield,biomass,interactions}`: V1 data (371 contrasts, V1 intervals ±2.86). Replaced by
  Fig2/Fig3/Fig6 (models, intervals), Fig8–Fig11/Fig14 (meta-analysis), Fig17 (learning curves), Fig19 (S × B, A × B).
- `SynerPlant_Yield_V2/outputs/figures/F1–F7`: earlier single-panel V2 drafts, merged into Fig1–Fig3.
- `SynerPlant_Yield_V2/outputs/{exploratory,biomass_v2}/stress_recovery/X1_stress_recovery`: exploratory drafts
  whose content is in Fig4 (yield) and Fig6 (biomass).

Scripts: `src/h08_figures.py` (Fig12, Fig13, Table2), `src/h09_meta_landscape_figures.py` (Fig14, Fig15),
`src/h12_more_figures.py` (Fig16–Fig20; analyses `h10_interactions_meta.R`, `h11_learning_ad.py`),
`src/h13_database_figure.py` (Fig21). V2 figures: `SynerPlant_Yield_V2/src/s15, s18, s20, s21`.
