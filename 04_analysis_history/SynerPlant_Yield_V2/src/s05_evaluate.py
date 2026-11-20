"""Stage VI - evaluation, model selection and comparability analysis from the stored grouped-CV predictions."""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from v2_common import OUT, now, write_json

ML = OUT / "ml"
DATA = OUT / "data"
BASELINES = ["row_mean", "row_median", "study_mean", "study_median"]
COMPLEXITY = {"row_mean": 0, "row_median": 0, "study_mean": 0, "study_median": 0, "ridge": 1, "quantile_l1": 1,
              "elasticnet": 1, "huber": 1, "mixed_ri": 2, "hgb": 3, "catboost": 3}
V1_REFERENCE = {"group_mae": 0.43335057420719353, "note": "V1 run (D5), different CV splits/sample/calibration hold-out; "
                "not directly comparable"}
GAIN_MIN, WINS_MIN, N_BOOT = 0.02, 3, 4000


def gmae(y, p, g):
    return float(pd.Series(np.abs(np.asarray(y) - np.asarray(p))).groupby(np.asarray(g)).mean().mean())


def summarize(mets, preds):
    rows = []
    for (ds, fs, fam), m in mets.groupby(["dataset", "fs", "family"]):
        p = preds[(preds.dataset == ds) & (preds.fs == fs) & (preds.family == fam)]
        seed_scores = p.groupby("seed").apply(lambda x: gmae(x.lnRR, x.pred, x.group_id), include_groups=False)
        y, yp = p.lnRR.to_numpy(), p.pred.to_numpy()
        ss_res = ((y - yp) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        rows.append({"dataset": ds, "fs": fs, "family": fam, "candidate": f"{fam}|{fs}",
                     "group_mae": seed_scores.mean(), "group_mae_sd_seeds": seed_scores.std(ddof=1),
                     "fold_group_mae_mean": m.group_mae.mean(), "fold_group_mae_sd": m.group_mae.std(ddof=1),
                     "mae": float(np.mean(np.abs(y - yp))), "rmse": float(np.sqrt(np.mean((y - yp) ** 2))),
                     "r2_oof": float(1 - ss_res / ss_tot), "bias_mean_pred_minus_obs": float(np.mean(yp - y)),
                     "n_rows": int(p.contrast_id.nunique()), "n_groups": int(p.group_id.nunique()),
                     "complexity": COMPLEXITY[fam]})
    return pd.DataFrame(rows)


def study_level_errors(p):
    """Mean absolute error per study averaged over seeds (each row has one OOF prediction per seed)."""
    a = p.assign(ae=(p.lnRR - p.pred).abs()).groupby(["group_id", "seed"]).ae.mean().groupby("group_id").mean()
    return a


def paired_bootstrap(pa, pb, seed=1):
    ea, eb = study_level_errors(pa), study_level_errors(pb)
    idx = ea.index.intersection(eb.index)
    diff = (ea[idx] - eb[idx]).to_numpy()
    rng = np.random.default_rng(seed)
    bs = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(N_BOOT)])
    return float(diff.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), float((bs >= 0).mean())


def wins(mets, ds, cand, base):
    a = mets[(mets.dataset == ds) & (mets.family + "|" + mets.fs == cand)].set_index(["seed", "fold"]).group_mae
    b = mets[(mets.dataset == ds) & (mets.family + "|" + mets.fs == base)].set_index(["seed", "fold"]).group_mae
    w = (a < b).groupby(level=0).sum()
    return int(w.median()), float((w >= WINS_MIN).mean())


def main():
    mets = pd.read_csv(ML / "cv_fold_metrics.csv")
    preds = pd.read_csv(ML / "cv_predictions.csv.gz")
    summ = summarize(mets, preds)
    sel = {}
    tables = []
    for ds, s in summ.groupby("dataset"):
        s = s.copy()
        bl = s[s.family.isin(BASELINES)].sort_values("group_mae")
        best_b = bl.iloc[0]
        s["best_baseline"] = best_b.candidate
        s["gain_vs_best_baseline"] = 1 - s.group_mae / best_b.group_mae
        pb = preds[(preds.dataset == ds) & (preds.family + "|" + preds.fs == best_b.candidate)]
        out = []
        for r in s.itertuples():
            pa = preds[(preds.dataset == ds) & (preds.family + "|" + preds.fs == r.candidate)]
            d, lo, hi, p = paired_bootstrap(pa, pb) if r.candidate != best_b.candidate else (0, 0, 0, 1)
            wmed, wfrac = wins(mets, ds, r.candidate, best_b.candidate) if r.candidate != best_b.candidate else (0, 0)
            out.append({"diff_vs_baseline": d, "diff_ci_lo": lo, "diff_ci_hi": hi, "p_boot_not_better": p,
                        "median_fold_wins_of_5": wmed, "share_seeds_with_3plus_wins": wfrac})
        s = pd.concat([s.reset_index(drop=True), pd.DataFrame(out)], axis=1)
        s["passes_rule"] = (~s.family.isin(BASELINES)) & (s.gain_vs_best_baseline >= GAIN_MIN) & \
            (s.median_fold_wins_of_5 >= WINS_MIN) & (s.diff_ci_hi < 0)
        q = s[s.passes_rule].sort_values("group_mae")
        if len(q):
            best = q.iloc[0]
            # prefer the simplest qualifying model within 2% of the best qualifying one
            simple = q[q.group_mae <= best.group_mae * 1.02].sort_values(["complexity", "group_mae"]).iloc[0]
            chosen, why = simple.candidate, "passes >=2% gain, >=3/5 fold wins (median over seeds) and bootstrap CI<0; simplest within 2%"
        else:
            chosen, why = best_b.candidate, "no candidate passed the prespecified rule; best baseline retained"
        sel[ds] = {"chosen": chosen, "reason": why, "best_baseline": best_b.candidate,
                   "best_baseline_group_mae": float(best_b.group_mae),
                   "best_nonbaseline": s[~s.family.isin(BASELINES)].sort_values("group_mae").iloc[0][
                       ["candidate", "group_mae", "gain_vs_best_baseline", "diff_ci_lo", "diff_ci_hi",
                        "median_fold_wins_of_5"]].to_dict() if (~s.family.isin(BASELINES)).any() else None}
        tables.append(s)
    allsum = pd.concat(tables, ignore_index=True).sort_values(["dataset", "group_mae"])
    allsum.to_csv(ML / "model_comparison.csv", index=False)

    # ablation table (PRIMARY + V1_EQUIVALENT)
    ab = allsum[allsum.fs.isin(["F0", "F1", "F2", "F3", "F4"]) & allsum.family.isin(["ridge", "quantile_l1", "catboost"])]
    ab = ab.pivot_table(index=["dataset", "family"], columns="fs", values="group_mae").reset_index()
    ab.to_csv(ML / "ablation_F0_F4.csv", index=False)

    # per-study errors, subgroups, extremes for the chosen PRIMARY model and the best baseline
    d = pd.read_csv(DATA / "PRIMARY_EXPANDED.csv", low_memory=False)
    meta_cols = ["contrast_id", "stress_family", "biostimulant_class", "yield_tier", "cultivation_system",
                 "risk_of_bias", "source_quality_flags", "any_figure_source", "doi"]
    chosen = sel["PRIMARY_EXPANDED"]["chosen"]
    cands = {"chosen": chosen, "best_baseline": sel["PRIMARY_EXPANDED"]["best_baseline"]}
    bn = sel["PRIMARY_EXPANDED"]["best_nonbaseline"]
    if bn:
        cands["best_nonbaseline"] = bn["candidate"]
    sub_rows, study_rows = [], []
    for lab, cand in cands.items():
        p = preds[(preds.dataset == "PRIMARY_EXPANDED") & (preds.family + "|" + preds.fs == cand)].merge(
            d[meta_cols], on="contrast_id", how="left")
        p["ae"] = (p.lnRR - p.pred).abs()
        p["extreme"] = np.where(p.lnRR.abs() > 1, "|lnRR|>1", "|lnRR|<=1")
        for col in ["stress_family", "yield_tier", "cultivation_system", "risk_of_bias", "extreme",
                    "biostimulant_class", "any_figure_source"]:
            for lv, g in p.groupby(col, dropna=False):
                sub_rows.append({"model": lab, "candidate": cand, "subgroup": col, "level": str(lv),
                                 "n_rows": int(g.contrast_id.nunique()), "n_studies": int(g.group_id.nunique()),
                                 "group_mae": gmae(g.lnRR, g.pred, g.group_id),
                                 "bias": float((g.pred - g.lnRR).mean())})
        st = p.groupby("group_id").agg(n=("contrast_id", "nunique"), mean_lnRR=("lnRR", "mean"),
                                       sd_lnRR=("lnRR", "std"), mae=("ae", "mean"),
                                       mean_pred=("pred", "mean"), stress=("stress_family", "first"),
                                       tier=("yield_tier", "first"), doi=("doi", "first")).reset_index()
        st["model"], st["candidate"] = lab, cand
        study_rows.append(st)
    pd.DataFrame(sub_rows).to_csv(ML / "subgroup_performance.csv", index=False)
    pd.concat(study_rows).to_csv(ML / "per_study_errors.csv", index=False)

    # variance decomposition of lnRR (why predictability is limited)
    vd = {}
    for ds in ["PRIMARY_EXPANDED", "V1_EQUIVALENT", "STRICT_SENSITIVITY"]:
        x = pd.read_csv(DATA / f"{ds}.csv", low_memory=False)
        tot = x.lnRR.var()
        within = x.groupby("study_id").lnRR.var().fillna(0)
        wn = x.groupby("study_id").size()
        pooled_within = float((within * (wn - 1)).sum() / (wn - 1).sum())
        vd[ds] = {"total_var": float(tot), "pooled_within_study_var": pooled_within,
                  "share_within": float(pooled_within / tot), "n_rows": int(len(x)), "n_studies": int(x.study_id.nunique()),
                  "lnRR_mean": float(x.lnRR.mean()), "lnRR_median": float(x.lnRR.median()),
                  "share_abs_gt_1": float((x.lnRR.abs() > 1).mean())}
    rep = {"generated_at": now(), "selection": sel, "variance_decomposition": vd, "v1_reference": V1_REFERENCE,
           "rule": {"gain_min": GAIN_MIN, "wins_min_of_5": WINS_MIN, "bootstrap": f"paired study-level, {N_BOOT} resamples, 95% CI of MAE difference < 0"}}
    write_json(ML / "selection_report.json", rep)
    return rep


if __name__ == "__main__":
    r = main()
    print(json.dumps(r["selection"], indent=1, default=str))
    print(json.dumps(r["variance_decomposition"], indent=1))
