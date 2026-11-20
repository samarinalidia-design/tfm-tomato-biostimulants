# Pre-registration — biomass TEST 2024-2026 (2026-11-18T11:40:13+00:00)

Biomass TEST data NOT OPENED by any V2/V3 code. Disclosure: the yield TEST (same TEST project, 12 studies) was evaluated on 2026-11-18 11:03 UTC; biomass values of the TEST were never read before this registration.

**Primary**: row_mean|B, frozen lnRR 0.3190; 90 % half-widths single ±0.527, simultaneous ±0.755. Accuracy threshold group-MAE ≤ 0.297; coverage ≥ 0.85.

**Conditional** (fitted on 109 TRAIN factorial studies):
- C1: ln(SB/S) = 0.1401 + (-0.3544)·D
- C2: ln(SB/S) = 0.5699·(−D)
- C3: ln(SB/S) = 0.0328 + (-0.2795)·D + (0.7050)·ln(B/C)
- 1_gain: group-MAE of C1 at least 10% below the frozen TRAIN median on the same TEST rows
- 2_beyond_coupling: gain above the 95th percentile of 500 TEST null worlds
- 3_slope: between-study slope on D: 95% study-bootstrap CI below 0 and outside the null 95% band
- 4_coverage: C1 single-contrast coverage >= 0.85
- verdict: CONFIRMED only if 1-3 hold; PARTIAL if 3 holds without 1; NOT CONFIRMED otherwise
- C3_secondary: C3 is reported with the same gain / null criteria (1, 2) as a secondary hypothesis

## SHA-256
- `src/b03_build_biomass.py` 68f83898a11c93e3375d6b3f0206f96915577bd1f53f4670a4413acc1a9b69fc
- `src/b04_train.py` 7b77a08fcd1be78a1da8b59c3576899cde5f143b7dcb2bd3f596d9b89d238ee5
- `src/b05_evaluate_all.py` c5d26f1fc102636779d3d6a02cdb835dd24f741c908eaddeb284e330db6cb16f
- `src/bx01_biomass_stress.py` 594e84551a61a77af09a84f4eeb0b1370121429f1d14d012eda3f479d92fba9d
- `src/b12_preregister_biomass.py` b88c15c454ee800174d19f3555873fc932c9674fc6117c2d1b54b404e987c616
- `src/b13_test_biomass.py` 81c6b0ce97458e9f04f3647de087f16aa0cfc190430fc0e728e98684fc053cae
- `src/b14_build_test_biomass.py` e5f6bc332e9f192ad724acddded630cbdf9ec69766c8348070655e532c324dea
- `src/s03_build_dataset.py` 496b52da8958220d780400a1b38f830ed8eb3e68aa76f4b5297a5f3f90322f11
- `src/v2_models.py` 9d0805289cfca1b0da7e803916dde244547d4844faec2237b1c40cf4d5b7218c
- `src/s04_train.py` 75bd9449c3c597fc45b0a6d2e807f4dd0dbd7cc204b41fae4989c890affcceea
- `src/s05_evaluate.py` 6444cc398efffdb3721eef22f78ace318646f0a7d1922f726c87886b1fa42791
- `src/s06_uncertainty.py` 90465422344663f89e309ba6959f015f010b824c88e50cd039619a0885557c92
- `src/s12_preregister.py` 3036f2b7f86e9a9f5996ff8f490f0b099d190e0b0777d702d0f6a1fecceca8a1
- `src/s13_test_evaluation.py` bd5e05af9310f4e3594633ce8e3fa742f27c3180143fe1f371996caba43bb892
- `src/x01_stress_recovery.py` 2c992fa69069ce00afb495fc22b8594e1a045f731bfc447bf00615b660826718
- `audit/corrections_register.json` bed1bb9be3ada6d3b5e48f33f357357a75758421f745867836c23a93f7d7aa37
- `audit/v3_register.json` 61fe3a1931ac42390068f0e3f1e7d7c441b69f4bdc489f35ac142e5073951ed1
- `outputs/biomass_v2/data/PRIMARY_EXPANDED.csv` 3461eb5c21d25eb1741c5e33b3950bed5691ba22ac0d14678f3eda7bf274711c
- `outputs/biomass_v2/data/dataset_build_report.json` 2514a0b85ebbe4f3b8c4d48459b12f4109a1c6a2b1dd3e2918f98d94c08dce2e
- `outputs/biomass_v2/ml/selection_report.json` 1161fdeea0bf2277c06a4043555ca1e172c982b1d741cb7f9415dccfd13eb29a
- `outputs/biomass_v2/ml/cv_fold_metrics.csv` 2c53312d400396f04ad78e6e1bd85e0ce18c4f20a86622851c5053d48d69b7fc
- `outputs/biomass_v2/uncertainty/deployment_intervals.json` dc177e3618cc8298f7b38fa5a4a439d3bef418f85ad3552b45d0a124a823761d
- `outputs/biomass_v2/stress_recovery/quadruples.csv` c91a6a9d5bcf68724db1d26fc15d0e526129b3fce271193a85aebb64facff7f6
- `outputs/biomass_v2/meta/R_confirmatory.json` 9aa67cacf2d9a31f2f3b36cc0c79b2658ea3e8ebe6697309c49bcae6e77e8747
- `outputs/biomass_v2/test_inputs_validation.json` 635a42b3e56f6061cf2df37662b297d71f0e36e659fa587b49ad881196a99d55