"""H7 - ONE post-hoc evaluation of the 2024-2026 TEST exactly as pre-registered in prereg/PREREG_V4_TEST_POSTHOC.json.

    python h07_test_posthoc.py            # the one run (writes outputs/test_posthoc/*, creates the lock)
    python h07_test_posthoc.py --verify   # only checks hashes and lock
Label of every output: POST_HOC_TEST_REUSE (the TEST had been evaluated once by V2 before).
"""
from __future__ import annotations
import json, sys
import numpy as np, pandas as pd
from scipy import stats
from h00_common import V4, sha256, write_json, now

PRE = V4 / "prereg" / "PREREG_V4_TEST_POSTHOC.json"
TO = V4 / "outputs" / "test_posthoc"
LOCK = TO / "TEST_POSTHOC_EVALUATED.lock"
Z90 = 1.6448536269514722
ALPHA = 0.10


def binom_ci(k, n):
    lo = stats.beta.ppf(0.025, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
    return [float(lo), float(hi)]


def iscore(a, hw):
    return 2 * hw + (2 / ALPHA) * np.maximum(a - hw, 0)


def evaluate(t, point, q1, q2, hw_row=None):
    r = t.lnRR - point
    a = r.abs()
    g = t.study_id
    h1 = pd.Series(q1 if hw_row is None else hw_row, index=t.index)
    cs = (a <= h1).groupby(g).mean()
    cm = (a <= q2).groupby(g).all()
    out = {"group_mae": float(a.groupby(g).mean().mean()), "mae": float(a.mean()), "rmse": float(np.sqrt((r ** 2).mean())),
           "bias_study_balanced": float((-r).groupby(g).mean().mean()), "bias_rows": float((-r).mean()),
           "coverage_single": float(cs.mean()), "coverage_simultaneous": float(cm.mean()),
           "coverage_simultaneous_ci95": binom_ci(int(cm.sum()), int(cm.size)),
           "half_width_single_mean": float(h1.mean()), "half_width_simultaneous": float(q2),
           "interval_score_single": float(pd.Series(iscore(a, h1), index=t.index).groupby(g).mean().mean()),
           "interval_score_simultaneous": float(pd.Series(iscore(a, q2), index=t.index).groupby(g).mean().mean())}
    per_study = pd.DataFrame({"ae": a.groupby(g).mean(), "is1": pd.Series(iscore(a, h1), index=t.index).groupby(g).mean(),
                              "cov1": cs, "covall": cm})
    return out, per_study


def boot(da, db, seed=20261118, B=4000):
    d = (da - db.reindex(da.index)).to_numpy()
    rng = np.random.default_rng(seed)
    bs = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(B)])
    return {"diff": float(d.mean()), "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}


def main():
    reg = json.loads(PRE.read_text(encoding="utf-8"))
    bad = [f for f, h in reg["hashes_sha256"].items() if sha256(V4 / f) != h]
    tf = reg["test_file"]
    if sha256(__import__("pathlib").Path(tf["path"])) != tf["sha256"]:
        bad.append("TEST file")
    if "--verify" in sys.argv:
        print("INTACT" if not bad else f"BROKEN {bad}", "| evaluated:", LOCK.exists())
        sys.exit(1 if bad else 0)
    if bad:
        sys.exit(f"REFUSED: pre-registered files changed: {bad}")
    if LOCK.exists():
        sys.exit(f"REFUSED: already evaluated ({LOCK.read_text()})")
    t = pd.read_csv(tf["path"], low_memory=False)
    train = set(pd.read_csv(V4 / "data" / "TRAIN_HARMONIZED.csv", usecols=["study_id"]).study_id.astype(str))
    t["study_id"] = t.study_id.astype(str)
    overlap = set(t.study_id) & train
    if overlap:
        sys.exit(f"REFUSED: TEST studies overlap TRAIN: {sorted(overlap)}")
    t = t[np.isfinite(t.lnRR)].reset_index(drop=True)

    A, B = reg["model_A_new"], reg["model_B_comparator"]
    ra, psa = evaluate(t, A["point_lnRR"], A["intervals_90"]["single_contrast_q"], A["intervals_90"]["simultaneous_q"])
    rb, psb = evaluate(t, B["point_lnRR"], B["intervals_90"]["single_contrast_q"], B["intervals_90"]["simultaneous_q"])
    f = A["fit"]
    nt = t.n_t.where(t.n_t > 0).fillna(f["n_t_median"]) if "n_t" in t else f["n_t_median"]
    nc = t.n_c.where(t.n_c > 0).fillna(f["n_c_median"]) if "n_c" in t else f["n_c_median"]
    vi = f["cv2_pooled"] / nt + f["cv2_pooled"] / nc
    hw = Z90 * np.sqrt(f["sigma2_study"] + f["sigma2_contrast"] + vi + f["se"] ** 2)
    rpi, _ = evaluate(t, A["point_lnRR"], None, A["intervals_90"]["simultaneous_q"], hw_row=np.asarray(hw))

    comp = {"group_mae_A_minus_B": boot(psa.ae, psb.ae), "interval_score_single_A_minus_B": boot(psa.is1, psb.is1)}
    H1 = ra["interval_score_single"] < rb["interval_score_single"] and ra["coverage_single"] >= 0.85
    H2 = ra["coverage_simultaneous"] >= 0.85
    H3 = abs(ra["bias_study_balanced"]) < abs(rb["bias_study_balanced"])
    H4 = ra["group_mae"] <= 0.587 and (ra["group_mae"] - rb["group_mae"]) <= 0.05
    verdict = "SUPPORTED" if (H1 and H2 and H4) else ("PARTIAL" if (H1 or H3) else "NOT_SUPPORTED")
    rep = {"label": "POST_HOC_TEST_REUSE", "evaluated_at": now(), "registration": reg["registered_at_utc"],
           "honesty_statement": reg["honesty_statement"],
           "n_contrasts": int(len(t)), "n_studies": int(t.study_id.nunique()),
           "A_new_multilevel_mean": ra, "A_secondary_model_PI": {k: rpi[k] for k in
                                                                ("coverage_single", "half_width_single_mean", "interval_score_single")},
           "B_V31_median": rb, "paired_bootstrap_by_study": comp,
           "criteria": {"H1_primary_interval": bool(H1), "H2_simultaneous": bool(H2), "H3_bias": bool(H3),
                        "H4_accuracy_noninferiority": bool(H4)}, "verdict": verdict}
    TO.mkdir(parents=True, exist_ok=True)
    write_json(TO / "TEST_POSTHOC_REPORT.json", rep)
    pd.concat({"A": psa, "B": psb}, axis=1).to_csv(TO / "per_study.csv")
    LOCK.write_text(f"evaluated {rep['evaluated_at']} under registration {reg['registered_at_utc']}", encoding="utf-8")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
