"""Stage VII - prediction intervals (Type B) with verified empirical coverage.

Four uncertainty types are kept apart:
  A  CV error bars       spread of CV metrics across folds/seeds            (s05, model_comparison.csv)
  B  conformal PI        interval for a FUTURE experimental effect          (this file)
  C  meta-analytic CI    uncertainty of the pooled mean effect              (s07_meta.py)
  D  meta-analytic PI    between-study heterogeneity of true effects        (s07_meta.py)

Evaluation protocol (identical for every method): for seed s and outer fold k the held-out studies T_k are the test
set; calibration scores come ONLY from studies outside T_k, using their own out-of-fold predictions (cross-fitting,
CV+ style). Coverage is therefore measured on studies never used to calibrate the interval that covers them.
"""
from __future__ import annotations
import json, math
import numpy as np, pandas as pd
from v2_common import OUT, now, write_json

ML = OUT / "ml"
DATA = OUT / "data"
UNC = OUT / "uncertainty"
UNC.mkdir(parents=True, exist_ok=True)
ALPHA = 0.10


def conformal_index(n, alpha=ALPHA):
    return math.ceil((1 - alpha) * (n + 1))


def q_order(scores, alpha=ALPHA):
    s = np.sort(np.asarray(scores))
    k = conformal_index(len(s), alpha)
    return np.inf if k > len(s) else float(s[k - 1])


def q_group_weighted(r, g, alpha=ALPHA):
    """Pooled-CDF group quantile: each calibration study has total weight 1 (Dunn et al. 2022, 'pooling CDFs'),
    with the finite-sample level (1-alpha)(1+1/K)."""
    df = pd.DataFrame({"r": np.abs(r), "g": g})
    df["w"] = 1 / df.g.map(df.g.value_counts())
    df = df.sort_values("r")
    K = df.g.nunique()
    lev = min((1 - alpha) * (1 + 1 / K), 1.0)
    c = df.w.cumsum() / K
    i = np.searchsorted(c.to_numpy(), lev - 1e-12)
    return np.inf if i >= len(df) else float(df.r.iloc[i])


def q_subsample(r, g, alpha=ALPHA, B=200, seed=0):
    """One residual per study, split-conformal order statistic; median over B subsamples."""
    df = pd.DataFrame({"r": np.abs(r), "g": g})
    rng = np.random.default_rng(seed)
    grp = [x.r.to_numpy() for _, x in df.groupby("g")]
    qs = [q_order([a[rng.integers(len(a))] for a in grp], alpha) for _ in range(B)]
    return float(np.median(qs))


def sigma_by_level(cal, col):
    """Group-balanced mean |residual| per level, shrunk to the global value (k = 3 studies)."""
    a = cal.assign(ar=cal.r.abs()).groupby([col, "g"]).ar.mean().reset_index()
    glob = a.groupby("g").ar.mean().mean()
    lev = a.groupby(col).ar.agg(["mean", "count"])
    s = glob + (lev["mean"] - glob) * lev["count"] / (lev["count"] + 3)
    return s.to_dict(), float(glob)


def evaluate(p: pd.DataFrame, meta: pd.DataFrame, label: str):
    p = p.merge(meta, on="contrast_id", how="left")
    p["r"] = p.lnRR - p.pred
    p["g"] = p.group_id
    rows = []
    for seed, ps in p.groupby("seed"):
        for fold, te in ps.groupby("fold"):
            cal = ps[ps.fold != fold]
            K = cal.g.nunique()
            res = {}
            res["group_cvplus_contrast"] = np.full(len(te), q_group_weighted(cal.r, cal.g))
            res["subsample_one_per_study"] = np.full(len(te), q_subsample(cal.r, cal.g, seed=seed + fold))
            smax = cal.assign(a=cal.r.abs()).groupby("g").a.max()
            res["group_cvplus_simultaneous"] = np.full(len(te), q_order(smax))
            # V1 replica: 25% of the non-test studies as a split calibration set, score = max |r| per study
            rng = np.random.default_rng(seed * 10 + fold)
            cg = rng.choice(smax.index.to_numpy(), size=max(1, round(0.25 * K)), replace=False)
            res["v1_split_max_25pct"] = np.full(len(te), q_order(smax[cg]))
            # adaptive: normalized by stress-family level of |residual|
            sig, glob = sigma_by_level(cal, "stress_family")
            sc = cal.r.abs() / cal.stress_family.map(sig).fillna(glob)
            qn = q_group_weighted(sc, cal.g)
            res["adaptive_stress_family"] = qn * te.stress_family.map(sig).fillna(glob).to_numpy()
            for m, hw in res.items():
                cov = (te.r.abs().to_numpy() <= hw)
                tmp = te[["contrast_id", "g", "stress_family", "yield_tier", "lnRR"]].copy()
                tmp["covered"], tmp["half_width"], tmp["method"], tmp["seed"], tmp["fold"] = cov, hw, m, seed, fold
                rows.append(tmp)
    ev = pd.concat(rows, ignore_index=True)
    out = []
    for m, e in ev.groupby("method"):
        per_study = e.groupby(["seed", "g"]).covered.agg(["mean", "all"])
        seed_cov = e.groupby(["seed", "g"]).covered.mean().groupby("seed").mean()
        out.append({"model": label, "method": m, "target": "simultaneous (all contrasts of a new study)"
                    if m in ("group_cvplus_simultaneous", "v1_split_max_25pct") else "single new contrast",
                    "nominal": 1 - ALPHA,
                    "coverage_contrast_study_balanced": float(per_study["mean"].mean()),
                    "coverage_contrast_rows": float(e.covered.mean()),
                    "coverage_all_contrasts_of_study": float(per_study["all"].mean()),
                    "coverage_sd_over_seeds": float(seed_cov.std(ddof=1)),
                    "half_width_mean": float(np.mean(e.half_width[np.isfinite(e.half_width)])),
                    "half_width_median": float(np.median(e.half_width[np.isfinite(e.half_width)])),
                    "share_infinite": float((~np.isfinite(e.half_width)).mean())})
    sub = ev.groupby(["method", "stress_family"]).agg(n=("contrast_id", "size"), coverage=("covered", "mean"),
                                                     half_width=("half_width", "mean")).reset_index()
    sub["model"] = label
    return pd.DataFrame(out), sub, ev


def main():
    sel = json.loads((ML / "selection_report.json").read_text())["selection"]
    preds = pd.read_csv(ML / "cv_predictions.csv.gz")
    d = pd.read_csv(DATA / "PRIMARY_EXPANDED.csv", low_memory=False)
    meta = d[["contrast_id", "stress_family", "yield_tier"]]
    cands = {"chosen": sel["PRIMARY_EXPANDED"]["chosen"], "best_baseline": sel["PRIMARY_EXPANDED"]["best_baseline"]}
    if sel["PRIMARY_EXPANDED"].get("best_nonbaseline"):
        cands["best_nonbaseline"] = sel["PRIMARY_EXPANDED"]["best_nonbaseline"]["candidate"]
    summ, subs = [], []
    for lab, cand in dict.fromkeys(cands.items()):
        p = preds[(preds.dataset == "PRIMARY_EXPANDED") & (preds.family + "|" + preds.fs == cand)]
        s, sb, ev = evaluate(p, meta, f"{lab}:{cand}")
        summ.append(s)
        subs.append(sb)
        if lab == "chosen":
            ev.to_csv(UNC / "interval_evaluation_rows_chosen.csv.gz", index=False)
    S = pd.concat(summ, ignore_index=True)
    S.to_csv(UNC / "interval_methods_comparison.csv", index=False)
    pd.concat(subs).to_csv(UNC / "interval_coverage_by_stress_family.csv", index=False)

    # deployment intervals: all cross-fitted residuals of the chosen model (69 studies, averaged over seeds)
    p = preds[(preds.dataset == "PRIMARY_EXPANDED") & (preds.family + "|" + preds.fs == cands["chosen"])].merge(meta, on="contrast_id")
    p["r"] = p.lnRR - p.pred
    dep = {}
    for seed, ps in p.groupby("seed"):
        smax = ps.assign(a=ps.r.abs()).groupby("group_id").a.max()
        sig, glob = sigma_by_level(ps.rename(columns={"group_id": "g"}), "stress_family")
        dep[seed] = {"single_contrast_q": q_group_weighted(ps.r, ps.group_id),
                     "simultaneous_q": q_order(smax),
                     "subsample_q": q_subsample(ps.r, ps.group_id, seed=seed),
                     "adaptive_unit_q": q_group_weighted(ps.r.abs() / ps.stress_family.map(sig).fillna(glob), ps.group_id),
                     "adaptive_sigma": sig, "adaptive_sigma_global": glob}
    agg = {k: float(np.median([v[k] for v in dep.values()])) for k in
           ["single_contrast_q", "simultaneous_q", "subsample_q", "adaptive_unit_q"]}
    agg["adaptive_sigma_by_stress_family"] = {k: float(np.median([v["adaptive_sigma"].get(k, np.nan) for v in dep.values()]))
                                              for k in dep[next(iter(dep))]["adaptive_sigma"]}
    agg["adaptive_sigma_global"] = float(np.median([v["adaptive_sigma_global"] for v in dep.values()]))
    agg["calibration_studies"] = int(p.group_id.nunique())
    agg["alpha"] = ALPHA
    agg["model"] = cands["chosen"]
    agg["v1_half_width"] = 2.8570517090811203
    agg["v1_calibration_studies"] = 13
    write_json(UNC / "deployment_intervals.json", agg)
    write_json(UNC / "uncertainty_types.json", {
        "A_cv_error_bars": "SD of group-MAE across 5 outer folds x 5 seeds (outputs/ml/model_comparison.csv: fold_group_mae_sd, group_mae_sd_seeds)",
        "B_conformal_prediction_interval": "this folder: interval for a future contrast (single) or for all contrasts of a new study (simultaneous)",
        "C_meta_CI": "outputs/meta/meta_summary.json: CI of the pooled mean lnRR",
        "D_meta_PI": "outputs/meta/meta_summary.json: prediction interval of a new study's TRUE mean effect (heterogeneity)",
        "do_not_mix": "A describes model-assessment noise, B future observations incl. within-study scatter, C the mean, D the spread of true study effects"})
    return S, agg


if __name__ == "__main__":
    S, agg = main()
    pd.set_option("display.width", 250)
    print(S.to_string())
    print(json.dumps(agg, indent=1))
