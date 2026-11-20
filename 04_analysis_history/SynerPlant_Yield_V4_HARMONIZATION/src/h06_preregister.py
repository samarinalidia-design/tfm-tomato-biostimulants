"""H6 - pre-registration of the ONE post-hoc TEST evaluation of V4 (written BEFORE any TEST value is read).

Frozen here: point estimate and 90 % intervals of the new model (A) and of the comparator (B, V3.1 row median, same
construction), the metrics, the success criteria and SHA-256 of every input/code file and of the TEST file itself
(only its bytes are hashed; no value is parsed).
"""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from h00_common import V4, V2, OUT, SEEDS, sha256, write_json, now, q_group_weighted, q_order

PRE = V4 / "prereg"
PRE.mkdir(exist_ok=True)
TEST_FILE = V2 / "outputs" / "v31" / "yield" / "test_inputs" / "TEST_PRIMARY.csv"
Z90 = 1.6448536269514722


def deployed_q(p):
    """V2 s06 deployment rule: per seed, q over all cross-fitted residuals of the 69 TRAIN studies; median over seeds."""
    single, simul = [], []
    for _, ps in p.groupby("seed"):
        r = ps.lnRR - ps.pred
        single.append(q_group_weighted(r, ps.group_id))
        simul.append(q_order(r.abs().groupby(ps.group_id).max()))
    return float(np.median(single)), float(np.median(simul))


def main():
    if (PRE / "PREREG_V4_TEST_POSTHOC.json").exists():
        raise SystemExit("REFUSED: pre-registration already exists; it is never overwritten")
    fit = json.loads((OUT / "rma" / "full_train_fit.json").read_text())
    rp = pd.read_csv(OUT / "rma" / "rma_predictions.csv")
    rp["group_id"] = rp.group_id.astype(str)
    a1, a2 = deployed_q(rp[rp.candidate == "rma_mv|intercept"])
    py = pd.read_csv(OUT / "cv" / "cv_predictions.csv.gz")
    py["group_id"] = py.group_id.astype(str)
    b1, b2 = deployed_q(py[py.candidate == "row_median|B|none|z"])
    tr = pd.read_csv(V4 / "data" / "TRAIN_HARMONIZED.csv", usecols=["lnRR", "study_id"])
    med = float(np.median(tr.lnRR))

    files = ["input/PRIMARY_EXPANDED_V31.csv", "input/input_manifest.json", "data/TRAIN_HARMONIZED.csv",
             "src/h00_common.py", "src/h01_features.py", "src/h02_cv.py", "src/h03_rma_mv.R", "src/h04_intervals.py",
             "src/h05_rma_summary.py", "src/h06_fit_full.R", "src/h06_preregister.py", "src/h07_test_posthoc.py",
             "outputs/cv/cv_predictions.csv.gz", "outputs/cv/comparison.csv", "outputs/rma/rma_predictions.csv",
             "outputs/rma/rma_comparison.csv", "outputs/rma/full_train_fit.json",
             "outputs/intervals/interval_comparison.csv", "README_V4.md"]
    reg = {
        "title": "SynerPlant Yield V4 - pre-registered POST-HOC re-use of the 2024-2026 TEST",
        "registered_at_utc": now(),
        "status_label": "POST_HOC_TEST_REUSE",
        "honesty_statement": (
            "The TEST was already evaluated once (V2, 2026-11-18 11:03 UTC) and its V2 results (group-MAE 0.415, "
            "bias -0.32, single coverage 0.847) were known when the V4 idea was formed. V4 was selected on TRAIN "
            "cross-validation only, and no V4 code has read TEST values, but this evaluation is NOT an independent "
            "confirmation. Report it as a second look at a known TEST."),
        "selection_basis": "TRAIN grouped CV 5x5 (outputs/intervals/interval_comparison.csv, outputs/rma/rma_comparison.csv)",
        "test_file": {"path": str(TEST_FILE), "sha256": sha256(TEST_FILE), "version": "V3.1 TEST (same build rules as the V3.1 TRAIN)",
                      "read_before_registration": "bytes hashed only; no value parsed"},
        "model_A_new": {
            "name": "multilevel random-effects mean (rma.mv, study/contrast, REML, shared-control covariance)",
            "point_lnRR": fit["mu"], "point_pct": 100 * (np.exp(fit["mu"]) - 1),
            "fit": fit,
            "intervals_90": {"single_contrast_q": a1, "simultaneous_q": a2,
                             "construction": "group-weighted CV+ / max-score CV+ on cross-fitted residuals (V2 s06 rule)"},
            "secondary_model_PI": "half = 1.645*sqrt(sigma2_study + sigma2_contrast + vi_prior + se^2), "
                                  "vi_prior = cv2_pooled/n_t + cv2_pooled/n_c (n imputed with TRAIN medians); own SD not used"},
        "model_B_comparator": {"name": "row median of V3.1 TRAIN (V2/V3.1 deployed rule)", "point_lnRR": med,
                               "intervals_90": {"single_contrast_q": b1, "simultaneous_q": b2}},
        "metrics": ["group-MAE", "MAE", "RMSE", "bias (pred - obs, study-balanced)",
                    "coverage single (study-balanced)", "coverage simultaneous (share of studies fully covered)",
                    "interval score single, study-balanced (alpha 0.10)", "interval score simultaneous, study-balanced",
                    "paired study bootstrap (4000) of A - B for group-MAE and interval score"],
        "criteria": {
            "H1_primary_interval": "interval score single A < B AND coverage single A >= 0.85",
            "H2_simultaneous": "coverage simultaneous A >= 0.85",
            "H3_bias": "|bias A| < |bias B|",
            "H4_accuracy_noninferiority": "group-MAE A <= 0.587 (V2 transport threshold) AND group-MAE A - B <= 0.05",
            "verdict": "SUPPORTED if H1 and H2 and H4; PARTIAL if H1 or H3 holds; otherwise NOT_SUPPORTED. "
                       "With 12 TEST studies the bootstrap CIs are reported, not used as pass criteria."},
        "guards": ["refuse if any hashed file changed", "refuse if V4 lock exists", "refuse if TEST studies overlap TRAIN",
                   "the V2 TEST lock and V2 outputs are not modified"],
    }
    reg["hashes_sha256"] = {f: sha256(V4 / f) for f in files}
    write_json(PRE / "PREREG_V4_TEST_POSTHOC.json", reg)
    md = [f"# PREREG V4 - post-hoc TEST re-use ({reg['registered_at_utc']})", "", reg["honesty_statement"], "",
          f"**A (new):** lnRR {fit['mu']:.4f} (+{reg['model_A_new']['point_pct']:.1f} %), q single {a1:.4f}, q simultaneous {a2:.4f}",
          f"**B (V3.1 median):** lnRR {med:.4f}, q single {b1:.4f}, q simultaneous {b2:.4f}", "",
          "## Criteria"] + [f"- **{k}**: {v}" for k, v in reg["criteria"].items()] + [
          "", f"TEST file SHA-256: `{reg['test_file']['sha256']}`", f"{len(files)} files hashed."]
    (PRE / "PREREG_V4_TEST_POSTHOC.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
