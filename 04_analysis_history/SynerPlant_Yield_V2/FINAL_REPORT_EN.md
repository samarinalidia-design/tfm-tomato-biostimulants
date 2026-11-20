# SynerPlant Yield V2 — Final report

**Primary target:** fruit-yield lnRR = ln(Yield stress + biostimulant / Yield same stress, no biostimulant).
**Status of the release:** `READY_TO_USE` (`exports/DATA_FREEZE_V2_20261118T080056Z`). All 11 gates pass, including the
human audit of the changed contrasts (24/24 required sampled rows CORRECT; all 158 changed contrasts reviewed by the
author).
**TEST analysis:** pre-registered (`outputs/preregistration/PREREG_TEST_V2.md`, 2026-11-18 09:07 UTC) plus Addendum 1
(09:37 UTC); 20 files locked by SHA-256.
**External 2024–2026 TEST:** evaluated once on 2026-11-18 11:03 UTC (12 studies, 36 contrasts; §12). Primary model
transports (accuracy and simultaneous coverage pass; single-contrast coverage 0.847, threshold 0.85); conditional
stress-damage model NOT CONFIRMED; pooled yield effect replicates (TEST +88 %, TEST − TRAIN p = 0.71).
**Biomass (secondary):** V2 with its own pre-registered TEST (28 studies). All primary criteria pass; the effect
replicates (§13).
**Current figures:** `outputs/figures_TFM_A4/` (Fig. 1–11 + Table 1).

## Before → After (summary)

| | V1 | V2 |
|---|---|---|
| Yield contrasts in the primary training set | 371 | **404** (one per SB/S arm pair) |
| Independent studies | 52 | **69** (+17) |
| Biotic-stress studies with yield | 3 | **4** (the corpus contains no more, see §3) |
| Strict-definition studies | 12 | 12 (105 contrasts after duplicate removal) |
| Application count available (rows) | 184 | **235** |
| Selected predictor | weighted mean (V1 rule) | **Row Median** (pre-specified rule; no ML model qualified) |
| Group-balanced MAE, same data and splits (V1's 371 contrasts) | 0.432 (study-balanced mean ≈ V1 choice) | **0.394** (median), −9% |
| Group-balanced MAE, V2 PRIMARY_EXPANDED | — | **0.361** |
| 90% prediction half-width for a new contrast | ±2.86 lnRR (13 calibration studies) | **±0.92 lnRR**, measured coverage **90.8%** |
| 90% half-width, all contrasts of a new study at once | (same ±2.86) | **±1.32 lnRR**, measured coverage **90.7%** |
| Independent TEST 2024–2026 (12 studies) | not evaluated | group-MAE **0.415** (≤ 0.587 ✓); coverage single **0.847**, simultaneous **0.917** |
| Pooled yield effect (R, CR2) | — | TRAIN +72 %, TEST **+88 %**, TRAIN + TEST **+76 %** (40 studies) |

## 1. Data before and after
- **V1:** 371 contrasts from 52 studies (115 STRICT + 256 ASSUMED). The 30 "missing" contrasts (401 − 371) were
  confirmed to be alternative representations of an already-included SB/S arm pair: per-area vs per-plant values of
  the same harvest in 3 studies. They were correctly not double-counted.
- **V2 PRIMARY_EXPANDED:** 404 contrasts from 69 studies:
  - STRICT 105
  - ASSUMED 217
  - BROAD 67 (marketable or single/partial harvest)
  - RELATIVE_SHARED_UNIT 15 (both arms in one column of one table, unit not printed)
- **Why studies with yield were missing from V1:** 74 studies have yield SB-vs-S contrasts. 22 of them were absent
  from V1 because their contrasts were routed to:
  - the broad-definition mart (12 studies)
  - the unit-unresolved mart (4 studies)
  - the box-centre mart (3 studies)
  - descriptive marts only (dry fruit mass, non-marketable or early yield)
- **Remedy (the "coding" approach):**
  - The ratio lnRR is unit-free when both arms share one measurement.
  - So the yield definition is kept as explicit descriptors instead of being a filter: `yield_scope_v2`,
    `harvest_window_v2`, `denominator_v2` and `yield_tier`.
  - These descriptors were tested as features (F3) and checked in sensitivity sets.
- **Not admitted to PRIMARY:**
  - box-centre (author decision of 2026-11-06)
  - dry fruit mass
  - non-marketable or early-only yield
  - unresolved identity
- **Pre-specified sets:**
  - PRIMARY_EXPANDED
  - STRICT_SENSITIVITY
  - QUALITY_CORE (no high RoB, no source flags, STRICT+ASSUMED; 221 contrasts / 37 studies)
  - eight further sensitivity sets
  - V1_EQUIVALENT (the exact V1 371 ids, for like-for-like comparison)

## 2. Errors corrected and decisions taken (sources in `audit/corrections_register.json`)
| Case | Finding | Action |
|---|---|---|
| P0 10.1155/2023/2581608 Fig. 3k | Two independent original-source re-digitisations agree: vector geometry 1.000/2.000, raster 0.994/1.996 kg/plant. The **source itself** plots whole-kg means, so V1's extraction was right (to 0.05%). | Means set to exact vector values (lnRR unchanged), `AUTO_VERIFIED_V2`, flag SOURCE_VALUES_QUANTIZED, excluded from QUALITY_CORE |
| P0 10.3390/plants11212822 | Class missing in V1 | *Streptomyces griseus* → PGPR_BACTERIA (actinobacterium). **Shikimic** acid (not salicylic) → small natural molecule class |
| P0 10.1016/j.scienta.2021.110337 | Sens arm: NM received 754 L m⁻² (more than the farm reference of 704), Myc received 614. Not a stress, not matched | Contrast excluded |
| P0 10.21608/fjard.2023.311918 FastTunic | NAA + Na-nitrophenolate, labelled "chemical control" by the authors; synthetic PGR under EU 1107/2009 | One rule applied to all synthetic PGRs (also **thidiazuron**, which V1 had kept): excluded from PRIMARY, kept in a sensitivity set |
| P1 10.1016/j.scienta.2020.109290 Fig. 9 | Means confirmed independently against the Table 10 marginal means (≤0.5% difference). n = 15 pots, mean ± SE. Every bar has the same ~0.51 kg error bar | Means kept; variance treated as unreliable |
| P1 10.32604/phyton.2022.016227 | lnRR 3.32 matches Table 2 exactly (42.0 → 1166.6 g/plant, SD, n = 3). Matched control under the same 200 mM NaCl | Kept unchanged in all main sets |
| New: D_21039…, D_2163… | The same table cell was extracted 2–3 times with conflicting yield definitions | One contrast per arm pair |
| New: D_b205… | 9 cumulative harvest timepoints for the same arm pair | Terminal harvest only |
| New: D_d2cc… | Fig. 1C (per plant) and 1D (per m²) contradict each other in the source | Per-plant panel used; study flagged |
| New: study 231 | Caption says "total fruit production (g)", text says "average mass" | Ambiguous; excluded from PRIMARY (sensitivity only) |
| Relative-unit studies | D_1c70, D_9f55 (biotic; 54 plants per treatment verified), 72, D_02c1 | Included as RELATIVE_SHARED_UNIT |

- **Database integrity:**
  - Foreign keys pass.
  - All 5,560 pairwise lnRR values recompute exactly.
  - Every SB-vs-S contrast has the same stress code in both arms and no biostimulant in the control.
  - Overall status PASS (`audit/integrity_report.json`).
- **Human audit status (honest finding):**
  - "audit.items = 0" comes from the empty legacy table `wf_audit`. The gate `human_contrast_audit` reads
    `wf_contrast_audit` (1,290 verdicts), so the two numbers do not contradict each other.
  - The 1,290 verdicts were all CORRECT and were written within 22 seconds (bulk import).
  - 313 of them carry notes that describe data problems.
  - 8 are now stale.
  - V2 does not rely on them. A new compact package covers the 158 changed contrasts (k = 24 to review).

## 3. Recovered data and the biotic question
- I checked the originals of all 46 biotic-related studies among the frozen 399.
- Only 5 report fruit yield. The others are seedling or pot disease assays that end before harvest, which I checked
  in the PDFs, not only the database.
- V2 recovers D_9f55 (early blight, field). BIOTIC now has 4 studies / 47 contrasts.
- More biotic yield data cannot come from this corpus: new studies were excluded by the author's decision.

## 4. Features added and why

| Feature | Rule | Coverage of 69 studies |
|---|---|---|
| `application_count_v2` | explicit counts parsed from frequency text, otherwise missing | 62% |
| `stress_timing` | early / mid / reproductive / whole cycle | 59% |
| `substrate_type` | soil vs soilless | 96% |
| `salinity_dSm_equiv` | EC, or NaCl/10, TDS/640, salinity only | 29% |
| `drought_supply_pct` | % field capacity / ETc, with its basis | 23% |
| yield-definition descriptors (F3) | scope, harvest window, denominator | see §1 |
| hierarchical encodings (F4) | empirical-Bayes shrunken study-level means | — |

- All preprocessing was learned inside the training folds:
  - imputation with missing-value indicators (never zero)
  - pooling of rare levels (< 5 studies)
  - a ≥ 20 % study-coverage rule
- Doses were not put on one scale: microbial CFU appears in only 3 studies, and only the within-experiment
  relative dose is unit-free.
- The early-physiology auxiliary model is **not feasible**: at most 3 studies share one trait measured on the same
  arms (≥ 8 needed), and the traits come from an unverified layer, mostly measured at harvest.

## 5. Models tested
- **Validation design:** grouped CV by study, 5 folds × 5 fixed seeds, identical splits for all candidates.
  Optuna (TPE, seeded, 10–18 trials) ran only on inner 3-fold grouped CV. 1,750 outer fits in total.
- **Baselines:** Row Mean, Row Median, Study-balanced Mean, Study-balanced Median.
- **Model families:**
  - Ridge
  - ElasticNet
  - Huber
  - L1 median regression
  - random-intercept mixed model (new studies predicted with u = 0)
  - HistGradientBoosting (absolute loss)
  - CatBoost
- **Feature sets:** F0–F4.
- **Datasets:** PRIMARY, V1_EQUIVALENT, STRICT, QUALITY_CORE and four other sensitivity sets.

## 6. Selection
- **Rule (pre-specified):**
  - ≥ 2 % gain over the best baseline
  - ≥ 3 of 5 fold wins (median over seeds)
  - paired study-level bootstrap 95 % CI of the MAE difference < 0
  - the simplest model within 2 %
- **Result: Row Median** on PRIMARY, group-MAE 0.361 ± 0.006 (SD over seeds).
  - The best ML model, median regression on F4, reached 0.363. Its difference from the baseline has CI
    [−0.004, +0.006].
  - No model beat the baseline on any dataset.
  - Feature importances are all below 0.0014 lnRR.

## 7. Change in MAE, stability and intervals
- **Like-for-like (V1_EQUIVALENT, same splits):**
  - Study-balanced mean: 0.432, essentially V1's model and V1's 0.433.
  - Median: 0.394, i.e. −9 %.
  - The study-level bootstrap CI for this difference includes 0 (Mean − Median = +0.038, CI ≈ [−0.007, +0.083]).
    The median is preferable but not decisively better.
- **Stability:**
  - SD across seeds is 0.006.
  - SD across folds is 0.11, driven by which studies fall into a fold.
- **Intervals (Type B, verified on held-out studies):**
  - ±0.92 for one new contrast, coverage 90.8 %.
  - ±1.32 for all contrasts of a new study, coverage 90.7 %.
  - Most of the narrowing from ±2.86 comes from **cross-fitting on all 69 studies**, instead of taking the
    maximum error of 13 held-out calibration studies. Coverage was not traded away.
  - V1's method applied to V2 data gives ±1.99 with 95 % coverage, i.e. it was conservative.
  - Adaptive stress-specific intervals under-covered (89.4 %; 78.5 % simultaneous) and were not adopted.
- **Meta-analysis (Types C/D; 31 studies with sampling variance):**
  - Pooled lnRR 0.54, i.e. +72 % yield.
  - CR2 cluster-robust 95 % CI 0.35–0.73 (confirmed in R: `metafor::rma.mv` + `clubSandwich` CR2,
    Satterthwaite df 28.8, p = 2·10⁻⁶; R and Python agree to < 2·10⁻⁸; `outputs/meta/R_vs_python.csv`).
  - The prediction interval for a new study's true mean is −0.43 to 1.52.
  - τ²: 0.22 between studies, 0.12 within.
  - The four uncertainty types are reported separately: A = CV error bars, B = conformal prediction interval,
    C = CI of the pooled mean, D = meta-analytic prediction interval.

## 8. Real improvement vs. change in data
- **Real improvements:**
  - Corrected and consistent classification.
  - Duplicate removal.
  - 17 more independent studies.
  - Narrower prediction intervals with measured nominal coverage.
  - The median replacing the mean on identical data (−9 %, but its CI includes 0).
- **Due to the change in data:**
  - The fall from 0.394 to 0.361 between V1_EQUIVALENT and PRIMARY_EXPANDED is a different sample and is **not** a
    model improvement.
  - The meta-analytic effect estimates are similarly sample-dependent.

## 9. Remaining problems (`audit/UNRESOLVED_QUEUE.csv`)
- **Decisions for you (D):**
  - ambient-stress studies
  - the synthetic-PGR scope
  - broad definitions in PRIMARY
- **Source ambiguities:**
  - 231
  - D_952e
  - D_d2cc
  - the error bars of D_1747
- **V1 audit governance:** see §2.
- **Why yield is hard to predict:**
  - 36 % of the lnRR variance lies *within* studies, where design features hardly vary.
  - 13 % of contrasts have |lnRR| > 1. On those the median errs by 1.17 on average (bias −1.11).
  - HEAT is the worst-predicted stress family (MAE 0.56).
  - Heterogeneity between studies is large (τ_b ≈ 0.47).
- **Data that could really help:**
  - A measured, comparable stress exposure (root-zone ECe, soil water potential, relative transpiration) or the
    grower's prior estimate of the yield loss. The stress actually realised in the control explains most of the
    between-study variation (§11), but the printed stress dose does not.
  - Harmonised doses within biostimulant classes.
  - Many more studies per class × stress cell. Most cells have fewer than 5 studies.
  - Early physiology measured on the same arms.

## 10. Readiness
- **Independent TEST:** done (§12).
  - Model, intervals, conditional models, the TEST builder (`s14_build_test_dataset.py`, validated byte-identical on
    TRAIN) and the TEST evaluation code (`s13`, `s17`) were frozen and hashed before the TEST was opened.
  - The TEST extraction started under the V1 freeze; V2 never saw TEST data before the one-time evaluation
    (Addendum 1, §5). `TEST_EVALUATED.lock` prevents a second run.
- **Ready for publication:**
  - The data audit, sensitivity design and intervals are publication-grade.
  - The scientific conclusion is that, with these 69 studies, design descriptors do **not** improve prediction of
    the biostimulant yield response beyond a robust central value. This is a substantive, reportable result.
  - The confirmatory R meta-analysis is done (§7).

## 11. After the freeze: the stress gradient (exploratory, pre-registered for the TEST)
- **X1, realised damage** (`outputs/exploratory/stress_recovery/`):
  - In 42 factorial studies with all four arms, the stronger the stress damage D = ln(S/C), the larger the
    biostimulant effect.
  - Between-study slope −0.59 (95 % CI −0.74 to −0.41). The shared-S coupling artefact alone gives −0.02.
  - Study-level damage explains 57 % of the between-study variance.
  - The biostimulant recovers about two thirds of the log-loss (median 0.64).
  - Within studies the association equals the artefact, so there is no within-study gradient.
- **X2, printed stress dose** (`outputs/exploratory/stress_intensity/`):
  - 98 arm codings were re-extracted; 94 were confirmed in the PDF.
  - Expected damage from Maas–Hoffman / FAO-33 does not predict the realised damage across studies (Spearman 0.02,
    25 studies), although levels are correctly ordered within studies (86 % of pairs).
  - Printed doses therefore cannot replace the realised damage.
- **Conditional model:** if the expected yield loss is known, ln(SB/S) = 0.106 − 0.523·D.
  - Group-MAE 0.279 vs 0.348 for the median on the same 42 studies (−20 %).
  - 90 % interval ±0.78, CV coverage 91.9 %.
  - Pre-registered with frozen coefficients and coupling-controlled success criteria. Only the TEST can confirm it.
    **It was not confirmed (§12).**

## 12. Independent TEST 2024–2026 (one-time, pre-registered evaluation)
Source: TEST project `exports/DATA_FREEZE_20261118T105532769144Z` (READY_TO_USE, 25/25 acceptance gates; no overlap
with TRAIN; studies 2024-01-01 to 2026-11-03; human contrast audit 243/243). Converted with the frozen V2 rules by
`s14` (36 included contrasts from 12 studies; 37 excluded by the V2 rules, 5 duplicates; 24 factorial contrasts from 9
studies). Evaluated once by `s13` (2026-11-18 11:03 UTC); secondary meta-analyses by `s17`. Nothing was re-fitted.
Results: `outputs/test_evaluation/TEST_REPORT.json`, `TEST_meta.json`; Fig. 5.

**Primary hypothesis — frozen median (0.285) and its intervals:**

| Criterion | Threshold | TRAIN (grouped CV) | TEST | Verdict |
|---|---|---|---|---|
| Group-MAE (lnRR) | ≤ 0.587 | 0.361 | **0.415** | pass |
| Coverage, single contrast (±0.92), study-balanced | ≥ 0.85 | 0.908 | **0.847** | fail (by 0.003) |
| Coverage, all contrasts of a study (±1.32) | ≥ 0.85 | 0.907 | **0.917** (95 % CI 0.62–1.00) | pass |

- MAE 0.480, RMSE 0.663, bias −0.32: the TEST effects are on average larger than the frozen median.
- All 9 contrasts outside the single-contrast interval belong to the two TEST studies with the largest effects
  (lnRR ≈ 1.2–1.6). With 12 studies, 0.847 is statistically indistinguishable from 0.85, but the pre-registered
  threshold is not met and this is reported as such.

**Conditional stress-damage models (9 studies, 24 contrasts):**

| Model | TRAIN CV group-MAE | TEST group-MAE | Gain vs TEST median (0.280) | Null-world 95th pct |
|---|---|---|---|---|
| C1 damage (primary) | 0.279 | 0.328 | −17 % | 0.029 |
| C2 recovery share | 0.259 | 0.327 | −17 % | 0.074 |
| C3 damage + unstressed effect | 0.215 | 0.251 | +10 % | 0.113 |

- The between-study slope of ln(SB/S) on D is −0.01 on TEST (95 % CI −2.9 to 1.5; TRAIN −0.59).
- Criteria 1–3 fail; C1 coverage passes (1.00). Verdict: **NOT CONFIRMED**. The TRAIN gain of the conditional model
  did not transport to new studies. C3's 10 % gain lies inside the coupling-artefact band.

**Secondary meta-analyses (R metafor + CR2; 9 TEST studies have sampling variances):**

| Set | Studies | Pooled lnRR | Effect | 95 % CI (CR2) | 95 % PI, new study |
|---|---|---|---|---|---|
| TRAIN | 31 | 0.544 | +72 % | 0.354–0.734 | −0.43 to 1.52 |
| TEST | 9 | 0.630 | +88 % | 0.190–1.070 | −0.73 to 1.99 |
| TRAIN + TEST | 40 | 0.563 | +76 % | 0.395–0.732 | −0.42 to 1.55 |
| TEST − TRAIN | — | +0.083 (p = 0.71) | — | −0.388 to 0.553 | — |

The TEST pooled effect is consistent with TRAIN and lies inside the TRAIN prediction interval: the yield benefit of
biostimulants under stress replicates on independent, later studies.

## 13. Secondary target: dry biomass V2 (pre-registered, independent TEST)
Done after the yield TEST in `db/TFM_V3_WORKING.sqlite`; the V2 release is preserved by
`exports/WORKING_VERSION_V2.0_TEST_EVALUATED.json` (170 hashed files). Code: `b03` data, `b04` CV, `b05` selection /
intervals / meta, `bx01` stress gradient, `b12` registration, `b14` TEST builder, `b13` one-time evaluation; the
frozen yield modules are imported unchanged. Results: `outputs/biomass_v2/`; Fig. 6–7.

**Data.** Target ln(dry biomass SB / S), shoot or whole plant, one contrast per SB/S arm pair (latest timepoint).
- V1: 708 contrasts / 145 studies → V2 PRIMARY: **766 / 153**. Recovered: 49 contrasts whose arm pair had no
  terminal row (6 new studies), 17 dry-basis contrasts with unstated unit (4 studies; lnRR is unit-free).
- Root, leaf, stem and other-organ masses are excluded (different construct). Fresh/unspecified basis (80 contrasts,
  9 studies) is sensitivity only.
- Integrity: recomputed lnRR equals the stored effect in all rows. Pre-specified suspicion flags (not model-based):
  |lnRR| > 1.5, control range > 50× within a study, constant error bars, conference record. Review against the stored
  source quotes:
  - study 279 is internally inconsistent in its source (Duncan letters contradict the means; all saline treatments
    exceed the unstressed control) → sensitivity only (`audit/v3_register.json`, B-S001);
  - studies 18 and 170 are correct;
  - three figure-digitised values await a PDF check. The corpus on Google Drive was offline on 2026-11-18.

**Models (same grouped 5×5 nested CV and selection rule as for yield).**

| | V1 | V2 |
|---|---|---|
| Selected predictor | mean | **row mean** (no model passed the rule) |
| Group-MAE, CV | 0.257 (V1 splits) | **0.242** |
| Best descriptor model | — | ridge F2 0.236 (−2.7 %, 4/5 fold wins, bootstrap CI upper +0.002) |
| 90 % interval, single contrast | ±1.22 (36 calibration studies) | **±0.53**, coverage 90.7 % (153 studies) |
| 90 % interval, all contrasts of a study | — | **±0.75**, coverage 90.3 % |

**Stress gradient (109 factorial studies).**
- Between-study slope of ln(SB/S) on D = ln(S/C): −0.33 (95 % CI −0.49 to −0.19). The coupling artefact is −0.02.
- Study damage explains 19 % of the between-study variance (null 0.5 %).
- CV gain vs the median:
  - C1 (damage) 5 %;
  - C3 (damage + unstressed effect ln(B/C)) 26 %, net of the coupling artefact.

**Independent TEST** (registered 2026-11-18 11:40 UTC, evaluated once 11:42 UTC; 28 studies, 144 contrasts).

| Criterion | Threshold | TRAIN CV | TEST | Verdict |
|---|---|---|---|---|
| Group-MAE | ≤ 0.297 | 0.242 | **0.285** | pass |
| Coverage, single (±0.53) | ≥ 0.85 | 0.907 | **0.909** | pass |
| Coverage, simultaneous (±0.75) | ≥ 0.85 | 0.903 | **0.893** | pass |

- **Conditional models** (20 studies, 104 contrasts):
  - C1 is 18 % better than the median, beyond the 95 % null-world gain (8 %), and its coverage is 0.87.
  - The between-study slope is −0.54 (95 % CI −0.68 to −0.14): below 0 but not fully outside the null band
    (−0.41 to 0.36). The pre-registered rule therefore gives **NOT CONFIRMED** for C1. Criteria 1, 2 and 4 hold;
    criterion 3 fails.
  - Secondary C3 is 34 % better than the median (null 8 %): **passes**.
- **Meta-analysis** (R metafor + CR2):
  - TRAIN +36 % (lnRR 0.305, CI 0.252–0.359, 78 studies);
  - TEST +39 % (0.329, CI 0.150–0.509, 21 studies);
  - TEST − TRAIN +0.015 (p = 0.87);
  - TRAIN + TEST +36 % (99 studies).
- **Disclosure:** the biomass TEST came from the same TEST project whose yield results were already known. Biomass
  TEST values were not read before the registration.

## 14. Yield V3: is there an error that drives the results? (exploratory, post-TEST)
- **Leave-one-study-out meta-analysis** (`outputs/v3_influence/`, Fig. 8):
  - removing any single study moves the pooled yield effect by at most 0.056 lnRR (+72 % → +63 % in the worst
    case); every CI excludes 0;
  - for biomass the largest shift is 0.008.
- **Group-MAE of the median:** 0.356 with all 69 studies, 0.336 without the largest one, 0.299 without the largest
  three. Those studies are D_19afb23b (lnRR up to 3.3), D_9ade6969 and D_24fe4181.
  - D_19afb23b and D_174774a4 were already verified against the source in V2.
  - D_9ade6969 is a conference record; its values match its table.
  - D_24fe4181 is figure-digitised; its PDF check is pending.
  - No data error was found. The large effects appear real, so error correction cannot materially lower the yield
    error.
- **Why few yield studies:** only 85 of the 399 studies measured fruit yield, and 74 of them have an SB-vs-S
  contrast. V2 already uses 69 (93 %). A yield-component proxy (fruit number × mean fruit mass) adds 6 studies (27
  contrasts) as a sensitivity set only (`outputs/v3_yield/`).

## 15. Meta-analysis diagnostics: forest plots, moderators, publication bias (exploratory)
`src/meta_extra.R` and `src/s21_meta_figures.py` produce `outputs/v3_meta_extra/` and Fig. 9–11. The model is the
same as the confirmatory one: rma.mv REML, study/contrast, CR2. These analyses were not pre-registered.
- **Forest plots** (Fig. 9 yield, 31 studies; Fig. 10 biomass, 78 studies). Study aggregates are within-study
  contrasts combined with ρ = 0.5. Nearly all studies are on the positive side.
- **Moderators** (CR2-HTZ Wald tests; levels with fewer than 4 studies pooled as "other"):
  - no moderator explains the between-study variance (pseudo-R² of τ² ≤ 0.03 everywhere):

    | Moderator | Yield p | Biomass p |
    |---|---|---|
    | Stress family | 0.20 | 0.79 |
    | Biostimulant class | 0.52 | 0.13 |
    | Route | 0.32 | 0.25 |
    | Cultivation system | 0.41 | 0.32 |

  - this agrees with the ML result that design descriptors do not predict the effect.
- **Small-study effects and publication bias** (Fig. 11):

| | Yield | Biomass |
|---|---|---|
| Multilevel Egger: slope on SE (CR2) | p = 0.21 | p = 0.98 |
| Study-level Egger / Begg | p = 0.10 / 0.08 | p = 0.14 / 0.27 |
| PET-PEESE estimate | lnRR 0.504 (+66 %) | 0.305 (+36 %) |
| Trim-and-fill (study level) | 0 studies imputed; +80 % | 12 imputed (left); +29 % (CI 0.19–0.32) |
| I² | ≈ 100 % | 98 % |

  - No test reaches p < 0.05.
  - Every bias-adjusted estimate stays clearly positive: yield +66 % to +80 %, biomass +29 % to +36 %.
  - With I² ≈ 98–100 %, funnel asymmetry methods have low power and trim-and-fill is unreliable. The conclusion is
    therefore "no evidence that small-study bias explains the effect", not "no bias".

## 16. V3.1: corrections after an external review of the TRAIN data (post-TEST, exploratory)
A reviewer audited the V3.0 Excel export. Every reported issue was checked in the data, and the key cases in the
originals. Implementation: `src/v31_build.py` (a correction layer on top of the frozen builds) and
`audit/v31_register.json`. Results: `outputs/v31/`; Excel: `exports/EXCEL_TRAIN_TEST_V3.1/`.

**Contrast fixes.**
- Two non-stressed contrasts moved out (study 41: pre-stress first harvest and well-watered reference).
- Three non-biostimulant "treatments" moved out: solvent control (706), NPK alone (653), and a culture medium
  without bacteria (yield, D_1c707674).
- Three contrasts re-based on the correct control:
  - chitosan vs the acetic-acid solvent control (706);
  - AMF + NPK vs NPK (653).
- Result: yield 404 → 403 contrasts (69 studies); biomass 766 → 762 (153 studies).
- The same generic rules remove nothing from the TEST sets.

**Feature fixes** (new `*_v3` columns; V2 columns kept for traceability):
- Drought measures are kept apart: % field capacity, % ETc/irrigation, FTSW, withheld irrigation events or days,
  and substrate water-holding capacity. The false 8 % (withheld rounds) and 68 % (substrate WHC) are removed.
- Salinity measures are kept apart: NaCl mM, EC of water/solution, TDS, and soil ECe. Soil ECe is no longer mixed
  with water EC; the V2 value of 0.4 dS/m irrigation-water EC used for a saline-soil study is corrected.
- Stress timing is negation-aware: 13 yield and 14 biomass rows changed, e.g. "before flowering" ≠ reproductive.
- Stress duration is recovered from context: yield 44 → 61 rows, biomass 211 → 276.
- Dose units are recovered (yield 88 rows, biomass 317), giving a canonical dose family and log dose for 284 / 529
  rows.

**Already handled in V2.** Study weights: every model is fitted with weight 1/n per study (`v2_models.py`), and the
median is weighted. Variance: 183 / 404 yield and 338 / 762 biomass contrasts have vi; 153 and 274 of these are
reported rather than assumed.

**PDF checks of the four extreme values that were pending** (originals supplied by the author):
- yield D_24fe4181, Agriculture 13:6, Fig. 7 — confirmed, and the control choice was checked in the Methods;
- biomass 23, Front. Plant Sci., Fig. 3 — confirmed;
- biomass 75, J. Fungi 9:384, Fig. 1b — confirmed;
- biomass D_3a8befa8, HortScience 56:414, Fig. 1 — confirmed.

None is an extraction error.

**Model comparison on the corrected TRAIN** (same 5×5 grouped nested CV and selection rule):

| | Yield V2 → V3.1 | Biomass V2 → V3.1 |
|---|---|---|
| Selected (rule) | row median 0.361 → 0.361 | row mean 0.242 → 0.240 |
| Best descriptor model | quantile L1 0.363 → 0.364 | ridge F2 0.236 → **ridge F2v3 0.233** (−3.0 %, 4/5 fold wins, CI upper +0.002) |
| CatBoost (best set) | 0.368 → 0.365 | 0.240 → 0.235 |

The corrections slightly improve the descriptor models for biomass, but no model passes the pre-specified rule,
whose bootstrap CI must lie below 0. For yield nothing changes. The conclusions of §12–15 stand. V3.1 is
exploratory: both TESTs were already used, so a re-evaluation on TEST could only be post-hoc.

**Conclusion:**
- Achieved:
  - data quality and recovery
  - leakage-free validation
  - reproducibility
  - honest intervals that are 3× narrower than V1; on the independent TEST, accuracy and the study-level interval
    hold, the single-contrast interval reaches 0.847 of the nominal 0.90
  - a confirmed pooled effect (+72 % TRAIN, +88 % TEST, +76 % combined; R CR2) that replicates on independent data
- Not achieved:
  - an ML model that beats the median from pre-experiment descriptors. This is a limit of the available evidence,
    not of the tuning.
  - a transportable explanation of the between-study heterogeneity for yield: the stress-damage gradient found in
    TRAIN was not confirmed on the TEST.
- **Biomass (secondary target, §13):**
  - all primary criteria pass on the independent TEST, with intervals 2.3× narrower than V1;
  - the effect replicates (+36 % TRAIN, +39 % TEST);
  - the stress-damage model improves on the median on TEST by 18 % beyond the coupling artefact, but it misses the
    strict pre-registered slope criterion;
  - the damage + unstressed-effect model (C3) passes as a secondary hypothesis.

## Appendix — Q&A on publishability and the TEST (added by the author, 2026-11-18)

1. Yes, the results are informative and publishable, but as a finding about the evidence, not as a prediction-model paper.

The informative parts:
- The average effect is real and stable. Biostimulants under stress raise tomato yield by about +72% on average (pooled lnRR 0.54, 95% CI 0.35–0.73). This holds in every sensitivity set (strict definition, quality core, reported-variance only, V1's sample).
- The effect varies a lot between studies. The 95% prediction interval for a new study's true effect runs from −0.43 to 1.52. So a new experiment can easily show no benefit, even though the average benefit is large. Growers and reviewers care about this.
- The negative result is a finding. With 69 independent studies, stress type, biostimulant class, route, timing, dose, growing system and yield definition do not predict the response better than the median. Seven model families and five feature sets were tested with proper grouped, nested validation. That is a real answer to "can we predict which biostimulant works under which stress from published study descriptors?"
- The intervals are honest. For a new result, the 90% interval is ±0.92 with coverage verified on held-out studies, versus V1's ±2.86. That is a methodological contribution.
- The data audit itself is reportable. It found a source figure plotting whole-kilogram means, duplicated table cells, contradictory panels, and a bulk-entered V1 audit. These support a broader point about extraction quality in agronomic meta-analyses.

How to frame it so reviewers accept it:
- Present the negative result as "absence of evidence under current reporting", not "moderators don't matter". The limits are specific:
  - stress intensity is reported in only 23–29% of studies;
  - doses cannot be put on one scale;
  - most class × stress combinations have fewer than 5 studies;
  - 36% of the variation is within studies, where design features barely change.
- Don't present the median as "the model". Present it as the benchmark that ML failed to beat.
- Before submitting, finish the R confirmation of the meta-analysis (metafor + clubSandwich), as the project contract requires.
- Expect one criticism: many models were compared. You're protected because the rule was fixed in advance and the winner is the simplest option.

For the TFM thesis, this is fully sufficient and well defended.

2. Yes, moving to the TEST makes sense, but its job changes. It is no longer "does ML beat the baseline". It becomes "do our conclusions hold on newer studies (2024–2026)?" In particular:
- Interval coverage: do about 90% of new results fall inside ±0.92? This is the strongest confirmatory result you can get, and it directly validates the heterogeneity claim.
- Error: is it close to the cross-validated 0.36? If so, the CV estimate wasn't optimistic.
- Mean effect: is the median (lnRR ≈ 0.28, about +33%) still right for newer products, or has the effect shifted over time?

Things to settle before touching the TEST:
- The three open scope decisions (ambient-stress studies, synthetic growth regulators, broad yield definitions). They define what is being predicted, and changing them after the TEST would invalidate it.
- Pre-register a secondary comparison. If you want to know whether features help on newer data, write down now that median regression with features (F4) will be scored next to the median. I can add this to the freeze. This is the only legitimate way to look at ML again.
- Run the TEST once, with no tuning afterwards.

On cost: the model side costs nothing, since it is frozen. The real cost is building the TEST database (extraction, audit) in the separate project. Even 20–30 TEST studies are enough to check coverage: with about 25 studies, a 90% coverage estimate has roughly ±6% uncertainty. A full 2024–2026 corpus isn't needed.

My recommendation: settle the three scope decisions, let me add the pre-registered F4 comparison to the freeze, then build a moderate-sized TEST set and run it once. That turns the thesis from "we couldn't predict it" into "we showed, on new data, how much a new experiment's outcome can be anticipated", which is a stronger result.
