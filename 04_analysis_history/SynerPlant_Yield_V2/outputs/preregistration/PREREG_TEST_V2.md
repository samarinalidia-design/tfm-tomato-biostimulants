# Pre-registration — TEST 2024-2026 (registered 2026-11-18T09:07:34+00:00)

TEST status at registration: **not opened**.

## Primary
- Frozen Row Median lnRR = 0.2847; 90 % half-widths: single ±0.920, simultaneous ±1.318
- coverage_single: observed >= 0.85 (nominal 0.90); report exact binomial 95% CI over studies
- coverage_simultaneous: observed >= 0.85
- accuracy: TEST group-MAE within the 95% range of the TRAIN cross-validated fold MAE (<= 0.361 + 2 x 0.113 = 0.587); otherwise report transport failure

## Conditional model (effect as a function of expected yield loss)
- C1: ln(SB/S) = 0.1064 + (-0.5226) × D,  D = ln(1 − loss)
- C2: ln(SB/S) = 0.6400 × (−D)
- C3: ln(SB/S) = -0.0080 + (-0.4831) × D + (0.7686) × ln(B/C)
- 90 % half-width C1: single ±0.776 (CV coverage 0.919), simultaneous ±1.123 (CV coverage 0.900)
- criterion 1_gain: group-MAE of C1 at least 10% below the frozen median on the same TEST rows
- criterion 2_beyond_coupling: observed gain above the 95th percentile of the gains obtained in 500 null worlds built from the TEST data (study effects permuted across studies, fresh arm sampling error) - controls the shared-S artefact
- criterion 3_slope: between-study slope of ln(SB/S) on D on TEST: 95% study-bootstrap CI below 0 and outside the null-world 95% band
- criterion 4_coverage: C1 single-contrast interval coverage >= 0.85
- criterion verdict: CONFIRMED only if 1-3 hold; PARTIAL if 3 holds without 1; NOT CONFIRMED otherwise

## Forbidden
- re-fitting or re-tuning any model on TEST
- changing V2 inclusion rules after opening TEST
- dropping TEST studies after seeing their errors
- running s13 more than once

## SHA-256
- `outputs/model/V2_YIELD_MODEL.joblib` a866607ffbd080b6adaaccc8cd769bfa880fb58781b24b679f184c23d65246a9
- `outputs/model/model_manifest.json` 7a3015b57e60179abd0be01c98ed1af84937f6dbcb48f5234aa98c8c4bf6680e
- `exports/DATA_FREEZE_V2_20261118T080056Z/MANIFEST.json` 1af2bf44edc0c200b2bc40ec69da4f6ab9fea641bf0d175503d98d20260a7815
- `outputs/exploratory/stress_recovery/quadruples.csv` 7b651fe6f1320697125287a3e9a723fcfa6f44db1960d5a101d1b325d426957d
- `src/x01_stress_recovery.py` 2c992fa69069ce00afb495fc22b8594e1a045f731bfc447bf00615b660826718
- `src/x02_stress_intensity.py` c38d40dcccabfce18054ec348e607b10d08921c10949f0728453809c7164118e
- `src/s12_preregister.py` 3036f2b7f86e9a9f5996ff8f490f0b099d190e0b0777d702d0f6a1fecceca8a1
- `src/s13_test_evaluation.py` bd5e05af9310f4e3594633ce8e3fa742f27c3180143fe1f371996caba43bb892
- `src/s03_build_dataset.py` 496b52da8958220d780400a1b38f830ed8eb3e68aa76f4b5297a5f3f90322f11
- `src/v2_models.py` 9d0805289cfca1b0da7e803916dde244547d4844faec2237b1c40cf4d5b7218c
- `audit/corrections_register.json` bed1bb9be3ada6d3b5e48f33f357357a75758421f745867836c23a93f7d7aa37