"""Pre-registration of the TEST analysis (written BEFORE any 2024-2026 TEST data are opened).

Freezes, with SHA-256:
  * PRIMARY model  : V2 frozen Row Median + conformal half-widths (unchanged, outputs/model/)
  * CONDITIONAL    : effect as a function of the expected yield loss caused by the stress, D = ln(1 - loss)
                     C1  y = a + b*D                 (LAD, study-balanced weights)
                     C2  y = r * (-D)                (recovered share of the log-loss; r = training median)
                     C3  y = a + b*D + c*ln(B/C)     (secondary, needs the unstressed B and C arms)
    coefficients are estimated ONCE here on the 42 factorial TRAIN_DEV studies and are not re-fitted on TEST;
    90 % conformal half-widths come from cross-fitted (grouped 5x5) residuals.
  * REJECTED       : nominal-intensity predictors (X2: no across-study validity) - not to be tested as primary.
  * decision rules and the coupling-artefact control for TEST.
Refuses to overwrite an existing registration (immutability); delete nothing by hand.
"""
from __future__ import annotations
import json, sys, datetime as dt
import numpy as np, pandas as pd
from sklearn.linear_model import QuantileRegressor
from v2_common import V2, OUT, now, sha256, write_json
from s04_train import outer_splits, SEEDS

PR = OUT / "preregistration"
PR.mkdir(parents=True, exist_ok=True)
REG = PR / "PREREG_TEST_V2.json"
ALPHA = 0.10


def lad(X, y, w):
    return QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs").fit(X, y, sample_weight=w * len(w) / w.sum())


def fit_all(d):
    w = 1 / d.group_id.map(d.group_id.value_counts()).to_numpy()
    c1 = lad(d[["D"]], d.y, w)
    c3 = lad(d[["D", "eB"]], d.y, w)
    r = float(np.median(d.RL.dropna()))
    return {"C1": {"intercept": float(c1.intercept_), "b_D": float(c1.coef_[0])},
            "C2": {"r": r, "fallback_if_D_above_-0.05": float(np.median(d.y))},
            "C3": {"intercept": float(c3.intercept_), "b_D": float(c3.coef_[0]), "c_eB": float(c3.coef_[1])},
            "median_train": float(np.median(d.y))}


def predict(coef, d, model):
    if model == "C1":
        return coef["C1"]["intercept"] + coef["C1"]["b_D"] * d.D
    if model == "C2":
        return np.where(d.D <= -0.05, coef["C2"]["r"] * -d.D, coef["C2"]["fallback_if_D_above_-0.05"])
    if model == "C3":
        return coef["C3"]["intercept"] + coef["C3"]["b_D"] * d.D + coef["C3"]["c_eB"] * d.eB
    if model == "median":
        return np.full(len(d), coef["median_train"])


def conformal(d):
    """Cross-fitted residuals (grouped 5x5): single-contrast pooled-CDF quantile and per-study max quantile."""
    from s06_uncertainty import q_group_weighted, q_order
    out = {}
    for m in ("C1", "C2", "C3", "median"):
        qs, qm, cov_s, cov_m = [], [], [], []
        for seed in SEEDS:
            res = pd.Series(np.nan, index=d.index)
            for te_g in outer_splits(d.group_id, seed):
                te = d.group_id.isin(te_g)
                coef = fit_all(d[~te])
                res[te] = d.y[te] - predict(coef, d[te], m)
            qs.append(q_group_weighted(res, d.group_id))
            qm.append(q_order(res.abs().groupby(d.group_id).max()))
            # coverage check: leave each fold's studies out of the calibration
            for f, te_g in enumerate(outer_splits(d.group_id, seed)):
                te = d.group_id.isin(te_g)
                q1 = q_group_weighted(res[~te], d.group_id[~te])
                q2 = q_order(res[~te].abs().groupby(d.group_id[~te]).max())
                a = res[te].abs()
                cov_s += list(a.groupby(d.group_id[te]).apply(lambda x: (x <= q1).mean()))
                cov_m += list(a.groupby(d.group_id[te]).apply(lambda x: bool((x <= q2).all())))
        out[m] = {"single_contrast_q": float(np.median(qs)), "simultaneous_q": float(np.median(qm)),
                  "cv_coverage_single": float(np.mean(cov_s)), "cv_coverage_simultaneous": float(np.mean(cov_m))}
    return out


def main(force=False):
    if REG.exists() and not force:
        print(f"Registration already exists ({REG.name}); it is immutable. Nothing written.")
        return json.loads(REG.read_text())
    q = pd.read_csv(OUT / "exploratory" / "stress_recovery" / "quadruples.csv", low_memory=False)
    q["group_id"] = q.study_id.astype(str)
    coef = fit_all(q)
    conf = conformal(q)
    prim = json.loads((OUT / "model" / "model_manifest.json").read_text())
    fz = sorted((V2 / "exports").glob("DATA_FREEZE_V2_*/MANIFEST.json"))[-1]
    hashed = [OUT / "model" / "V2_YIELD_MODEL.joblib", OUT / "model" / "model_manifest.json", fz,
              OUT / "exploratory" / "stress_recovery" / "quadruples.csv", V2 / "src" / "x01_stress_recovery.py",
              V2 / "src" / "x02_stress_intensity.py", V2 / "src" / "s12_preregister.py",
              V2 / "src" / "s13_test_evaluation.py", V2 / "src" / "s03_build_dataset.py", V2 / "src" / "v2_models.py",
              V2 / "audit" / "corrections_register.json"]
    reg = {
        "title": "SynerPlant Yield V2 - pre-registered analysis of the independent 2024-2026 TEST",
        "registered_at_utc": now(),
        "test_status_at_registration": "NOT OPENED: no TEST file has been read by any V2 code",
        "primary_hypothesis": {
            "model": prim["selection"]["chosen"],
            "frozen_median_lnRR": float(pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv").lnRR.median()),
            "intervals_90": {"single_contrast_q": prim["intervals"]["single_contrast_q"],
                             "simultaneous_q": prim["intervals"]["simultaneous_q"]},
            "metrics": ["group-balanced MAE (lnRR)", "MAE", "RMSE", "bias", "coverage single (study-balanced)",
                        "coverage simultaneous (share of studies fully covered)"],
            "success_criteria": {
                "coverage_single": "observed >= 0.85 (nominal 0.90); report exact binomial 95% CI over studies",
                "coverage_simultaneous": "observed >= 0.85",
                "accuracy": "TEST group-MAE within the 95% range of the TRAIN cross-validated fold MAE "
                            "(<= 0.361 + 2 x 0.113 = 0.587); otherwise report transport failure"}},
        "conditional_models": {
            "definition": "D = ln(S/C) = ln(1 - expected relative yield loss caused by the stress); in deployment D is "
                          "the user's prior estimate; on TEST it is taken from the factorial S and C arms",
            "coefficients_frozen_on_42_TRAIN_studies": coef,
            "conformal_90": conf,
            "primary_conditional": "C1",
            "secondary": ["C2", "C3"],
            "eligible_TEST_rows": "TEST SB-vs-S yield contrasts built with the V2 rules whose experiment also has "
                                  "C (no stress, no biostimulant) and, for C3, B arms in the same unit/timepoint",
            "minimum_TEST_studies": 8,
            "success_criteria": {
                "1_gain": "group-MAE of C1 at least 10% below the frozen median on the same TEST rows",
                "2_beyond_coupling": "observed gain above the 95th percentile of the gains obtained in 500 "
                                     "null worlds built from the TEST data (study effects permuted across studies, "
                                     "fresh arm sampling error) - controls the shared-S artefact",
                "3_slope": "between-study slope of ln(SB/S) on D on TEST: 95% study-bootstrap CI below 0 and "
                           "outside the null-world 95% band",
                "4_coverage": "C1 single-contrast interval coverage >= 0.85",
                "verdict": "CONFIRMED only if 1-3 hold; PARTIAL if 3 holds without 1; NOT CONFIRMED otherwise"}},
        "rejected_before_TEST": {"nominal_intensity_models": "X2: Maas-Hoffman/FAO-33 expected damage and raw "
                                 "intensity scales have no across-study validity (Spearman 0.02; CV worse than median)"},
        "forbidden": ["re-fitting or re-tuning any model on TEST", "changing V2 inclusion rules after opening TEST",
                      "dropping TEST studies after seeing their errors", "running s13 more than once"],
        "dataset_rules": "TEST contrasts must be built with the frozen V2 rules (corrections_register.json, "
                         "s03_build_dataset.py tiers/dedup/exclusions) from the TEST DATA_FREEZE; mapping of "
                         "moderators is irrelevant for the median and the conditional models (they use no moderators)",
        "hashes_sha256": {str(p.relative_to(V2)).replace("\\", "/"): sha256(p) for p in hashed},
    }
    write_json(REG, reg)
    md = [f"# Pre-registration — TEST 2024-2026 (registered {reg['registered_at_utc']})", "",
          "TEST status at registration: **not opened**.", "",
          "## Primary", f"- Frozen Row Median lnRR = {reg['primary_hypothesis']['frozen_median_lnRR']:.4f}; 90 % "
          f"half-widths: single ±{prim['intervals']['single_contrast_q']:.3f}, simultaneous ±{prim['intervals']['simultaneous_q']:.3f}",
          *[f"- {k}: {v}" for k, v in reg["primary_hypothesis"]["success_criteria"].items()], "",
          "## Conditional model (effect as a function of expected yield loss)",
          f"- C1: ln(SB/S) = {coef['C1']['intercept']:.4f} + ({coef['C1']['b_D']:.4f}) × D,  D = ln(1 − loss)",
          f"- C2: ln(SB/S) = {coef['C2']['r']:.4f} × (−D)",
          f"- C3: ln(SB/S) = {coef['C3']['intercept']:.4f} + ({coef['C3']['b_D']:.4f}) × D + ({coef['C3']['c_eB']:.4f}) × ln(B/C)",
          f"- 90 % half-width C1: single ±{conf['C1']['single_contrast_q']:.3f} (CV coverage {conf['C1']['cv_coverage_single']:.3f}), "
          f"simultaneous ±{conf['C1']['simultaneous_q']:.3f} (CV coverage {conf['C1']['cv_coverage_simultaneous']:.3f})",
          *[f"- criterion {k}: {v}" for k, v in reg["conditional_models"]["success_criteria"].items()], "",
          "## Forbidden", *[f"- {x}" for x in reg["forbidden"]], "",
          "## SHA-256", *[f"- `{k}` {v}" for k, v in reg["hashes_sha256"].items()]]
    (PR / "PREREG_TEST_V2.md").write_text("\n".join(md), encoding="utf-8")
    return reg


if __name__ == "__main__":
    r = main(force="--force-new-registration" in sys.argv)
    print(json.dumps({k: r[k] for k in ("registered_at_utc",)}, indent=1))
    print(json.dumps(r["conditional_models"]["coefficients_frozen_on_42_TRAIN_studies"], indent=1))
    print(json.dumps(r["conditional_models"]["conformal_90"], indent=1))
