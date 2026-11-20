"""Pre-registration of the BIOMASS TEST analysis (written BEFORE any biomass TEST data are opened; immutable).

Freezes with SHA-256: the biomass V2 data build (b03), the selected primary predictor and its conformal half-widths
(b05), the conditional stress-damage models C1-C3 fitted once on the TRAIN factorial quadruples (bx01; functions
fit_all / predict / conformal of the frozen s12 are re-used), the TEST builder (b14, validated identical on TRAIN)
and the one-time evaluation (b13). Thresholds are derived from TRAIN cross-validation, as for yield.
  python b12_preregister_biomass.py           write (refuses if it exists)
  python b12_preregister_biomass.py --verify  check every hash
"""
from __future__ import annotations
import json, sys
import numpy as np, pandas as pd
from s12_preregister import fit_all, conformal
from v2_common import V2, OUT, now, sha256, write_json

BIO = OUT / "biomass_v2"
PR = BIO / "preregistration"
REG = PR / "PREREG_TEST_BIOMASS.json"
TEST_FREEZE = V2.parent.parent / "TFM_TEST_2024_2026_Agent_System" / "exports" / "DATA_FREEZE_20261118T105532769144Z"
HASHED = ["src/b03_build_biomass.py", "src/b04_train.py", "src/b05_evaluate_all.py", "src/bx01_biomass_stress.py",
          "src/b12_preregister_biomass.py", "src/b13_test_biomass.py", "src/b14_build_test_biomass.py",
          "src/s03_build_dataset.py", "src/v2_models.py", "src/s04_train.py", "src/s05_evaluate.py",
          "src/s06_uncertainty.py", "src/s12_preregister.py", "src/s13_test_evaluation.py", "src/x01_stress_recovery.py",
          "audit/corrections_register.json", "audit/v3_register.json",
          "outputs/biomass_v2/data/PRIMARY_EXPANDED.csv", "outputs/biomass_v2/data/dataset_build_report.json",
          "outputs/biomass_v2/ml/selection_report.json", "outputs/biomass_v2/ml/cv_fold_metrics.csv",
          "outputs/biomass_v2/uncertainty/deployment_intervals.json",
          "outputs/biomass_v2/stress_recovery/quadruples.csv", "outputs/biomass_v2/meta/R_confirmatory.json",
          "outputs/biomass_v2/test_inputs_validation.json"]


def verify():
    reg = json.loads(REG.read_text(encoding="utf-8"))
    bad = [k for k, h in reg["hashes_sha256"].items() if not (V2 / k).exists() or sha256(V2 / k) != h]
    lock = (BIO / "test_evaluation" / "TEST_EVALUATED.lock").exists()
    print(f"Biomass registration {reg['registered_at_utc']}: {len(reg['hashes_sha256'])} hashed files "
          f"{'INTACT' if not bad else 'BROKEN: ' + str(bad)}; biomass TEST evaluated: {lock}")
    return 1 if bad else 0


def main():
    if REG.exists():
        print("Biomass registration exists; it is immutable. Nothing written.")
        return json.loads(REG.read_text(encoding="utf-8"))
    val = json.loads((BIO / "test_inputs_validation.json").read_text())
    if not val.get("PASS"):
        sys.exit("REFUSED: biomass TEST builder validation did not pass")
    PR.mkdir(parents=True, exist_ok=True)
    sel = json.loads((BIO / "ml" / "selection_report.json").read_text())["selection"]["PRIMARY_EXPANDED"]
    dep = json.loads((BIO / "uncertainty" / "deployment_intervals.json").read_text())
    mets = pd.read_csv(BIO / "ml" / "cv_fold_metrics.csv")
    fam, fs = sel["chosen"].split("|")
    fm = mets[(mets.dataset == "PRIMARY_EXPANDED") & (mets.family == fam) & (mets.fs == fs)].group_mae
    if fam not in ("row_median", "row_mean", "study_median", "study_mean"):
        sys.exit("A non-baseline model was selected: extend b12/b13 to freeze it before registering")
    prim = pd.read_csv(BIO / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    gid = prim.study_id.astype(str)
    if fam == "row_median":
        point = float(prim.lnRR.median())
    elif fam == "row_mean":
        point = float(prim.lnRR.mean())
    elif fam == "study_mean":
        point = float(prim.groupby(gid).lnRR.mean().mean())
    else:
        point = float(prim.groupby(gid).lnRR.mean().median())
    q = pd.read_csv(BIO / "stress_recovery" / "quadruples.csv", low_memory=False)
    q["group_id"] = q.study_id.astype(str)
    coef, conf = fit_all(q), conformal(q)
    R = json.loads((BIO / "meta" / "R_confirmatory.json").read_text(encoding="utf-8"))
    thr = float(fm.mean() + 2 * fm.std())
    reg = {
        "title": "SynerPlant Biomass V2 - pre-registered analysis of the independent 2024-2026 TEST (dry biomass)",
        "registered_at_utc": now(),
        "test_status_at_registration": "Biomass TEST data NOT OPENED by any V2/V3 code. Disclosure: the yield TEST "
                                       "(same TEST project, 12 studies) was evaluated on 2026-11-18 11:03 UTC; biomass "
                                       "values of the TEST were never read before this registration.",
        "target": "lnRR = ln(dry biomass SB / dry biomass S), shoot or whole plant, one contrast per SB/S arm pair",
        "primary_hypothesis": {
            "model": sel["chosen"], "frozen_point_lnRR": point,
            "intervals_90": {"single_contrast_q": dep["single_contrast_q"], "simultaneous_q": dep["simultaneous_q"]},
            "train_cv": {"group_mae_mean": float(fm.mean()), "group_mae_fold_sd": float(fm.std())},
            "success_criteria": {
                "coverage_single": "observed >= 0.85 (nominal 0.90), study-balanced",
                "coverage_simultaneous": "observed >= 0.85; exact binomial 95% CI over studies reported",
                "accuracy": f"TEST group-MAE <= TRAIN CV mean + 2 fold-SD = {thr:.4f}; otherwise transport failure"},
            "accuracy_threshold": thr},
        "conditional_models": {
            "definition": "D = ln(S/C) biomass loss caused by the stress; eB = ln(B/C); taken from factorial TEST arms",
            "coefficients_frozen_on_TRAIN_quadruples": coef, "n_train_studies": int(q.study_id.nunique()),
            "conformal_90": conf, "primary_conditional": "C1", "secondary": ["C2", "C3"],
            "minimum_TEST_studies": 8,
            "success_criteria": {
                "1_gain": "group-MAE of C1 at least 10% below the frozen TRAIN median on the same TEST rows",
                "2_beyond_coupling": "gain above the 95th percentile of 500 TEST null worlds",
                "3_slope": "between-study slope on D: 95% study-bootstrap CI below 0 and outside the null 95% band",
                "4_coverage": "C1 single-contrast coverage >= 0.85",
                "verdict": "CONFIRMED only if 1-3 hold; PARTIAL if 3 holds without 1; NOT CONFIRMED otherwise",
                "C3_secondary": "C3 is reported with the same gain / null criteria (1, 2) as a secondary hypothesis"}},
        "meta_analysis_TRAIN_frozen": {k: {x: v[x] for x in ("k_studies", "mu_lnRR", "pct_effect", "ci95_CR2",
                                                             "pi95_new_study_mean")}
                                       for k, v in R.items() if isinstance(v, dict) and "mu_lnRR" in v},
        "secondary_TEST_meta": "TEST pooled lnRR, TEST - TRAIN difference, TRAIN + TEST (meta_test.R, same model)",
        "test_rules": {"builder": "b14_build_test_biomass.py --test-sqlite <TEST freeze sqlite>",
                       "year_window": "< 2024 excluded", "study_specific_TRAIN_decisions": "not applied",
                       "test_freeze": str(TEST_FREEZE),
                       "test_freeze_manifest_sha256": sha256(TEST_FREEZE / "MANIFEST.json")},
        "forbidden": ["re-fitting or re-tuning on TEST", "changing biomass rules after opening TEST",
                      "dropping TEST studies after seeing errors", "running b13 more than once"],
        "builder_validation": val,
        "hashes_sha256": {f: sha256(V2 / f) for f in HASHED},
    }
    write_json(REG, reg)
    md = [f"# Pre-registration — biomass TEST 2024-2026 ({reg['registered_at_utc']})", "",
          reg["test_status_at_registration"], "",
          f"**Primary**: {sel['chosen']}, frozen lnRR {point:.4f}; 90 % half-widths single ±{dep['single_contrast_q']:.3f}, "
          f"simultaneous ±{dep['simultaneous_q']:.3f}. Accuracy threshold group-MAE ≤ {thr:.3f}; coverage ≥ 0.85.", "",
          f"**Conditional** (fitted on {q.study_id.nunique()} TRAIN factorial studies):",
          f"- C1: ln(SB/S) = {coef['C1']['intercept']:.4f} + ({coef['C1']['b_D']:.4f})·D",
          f"- C2: ln(SB/S) = {coef['C2']['r']:.4f}·(−D)",
          f"- C3: ln(SB/S) = {coef['C3']['intercept']:.4f} + ({coef['C3']['b_D']:.4f})·D + ({coef['C3']['c_eB']:.4f})·ln(B/C)",
          *[f"- {k}: {v}" for k, v in reg["conditional_models"]["success_criteria"].items()], "",
          "## SHA-256", *[f"- `{k}` {v}" for k, v in reg["hashes_sha256"].items()]]
    (PR / "PREREG_TEST_BIOMASS.md").write_text("\n".join(md), encoding="utf-8")
    print("Biomass registration written", reg["registered_at_utc"])
    return reg


if __name__ == "__main__":
    if "--verify" in sys.argv:
        sys.exit(verify())
    main()
