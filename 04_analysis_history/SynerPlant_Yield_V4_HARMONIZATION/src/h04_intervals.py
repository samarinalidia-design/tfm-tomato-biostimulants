"""H4 - prediction intervals: V2 reference methods vs location-scale (advice 5), same cross-fitting protocol as V2 s06:
for seed s / outer fold k the calibration residuals come only from the other folds' studies.

Methods
  group_cvplus_contrast        V2 deployed single-contrast interval (constant width)
  group_cvplus_simultaneous    V2 deployed all-contrasts-of-a-study interval (constant width)
  adaptive_stress_family       V2 exploratory (scale = shrunk mean |r| per stress family)
  ls_conformal                 NEW: scale model log|r| ~ ridge(stress family, system, yield scope, living microbe,
                               log sd of imputed vi, log n) fitted on calibration residuals (study weights);
                               normalized scores, group-weighted conformal quantile
  ls_conformal_simultaneous    NEW: same scale, max normalized score per study
  model_ls                     NEW (R rows only): parametric half-width from rma location-scale / rma.mv
  model_ls_conformal           NEW (R rows only): score |r| / model sd, conformal quantile (calibrated model scale)
Interval score (Gneiting & Raftery 2007, alpha = 0.10): width + 20 * distance outside; lower is better.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from h00_common import OUT, ALPHA, q_group_weighted, q_order, load_harmonized, write_json, now
from h02_cv import impute_vi, clean

IV = OUT / "intervals"
IV.mkdir(parents=True, exist_ok=True)
SCALE_CAT = ["stress_family", "cultivation_system", "yield_scope_v2"]
Z90 = 1.6448536269514722


def scale_design(df, levels=None):
    out = {}
    if levels is None:
        levels = {}
        for c in SCALE_CAT:
            v = clean(df[c])
            gc = df.groupby(v.values).group_id.nunique()
            levels[c] = sorted(l for l, n in gc.items() if n >= 5 and l != "MISSING")
    for c in SCALE_CAT:
        v = clean(df[c])
        for l in levels[c]:
            out[f"{c}={l}"] = (v == l).astype(float).to_numpy()
    out["living_microbe"] = df.comp_living_microbe.astype(float).to_numpy()
    out["log_sd_vi"] = 0.5 * np.log(df.vi_hat.to_numpy())
    out["log_n_arm"] = df.log_n_arm.fillna(np.log(3)).to_numpy()
    return pd.DataFrame(out, index=df.index), levels


def fit_scale(cal):
    X, lev = scale_design(cal)
    mu, sd = X.mean(), X.std().replace(0, 1)
    w = 1 / cal.group_id.map(cal.group_id.value_counts()).to_numpy()
    m = Ridge(alpha=10.0).fit((X - mu) / sd, np.log(cal.r.abs() + 0.02), sample_weight=w * len(w) / w.sum())

    def sigma(df):
        Xb, _ = scale_design(df, lev)
        Xb = Xb.reindex(columns=X.columns, fill_value=0.0)
        return np.exp(m.predict((Xb - mu) / sd))
    return sigma


def sigma_by_level(cal, col):
    a = cal.assign(ar=cal.r.abs()).groupby([col, "group_id"]).ar.mean().reset_index()
    glob = a.groupby("group_id").ar.mean().mean()
    lev = a.groupby(col).ar.agg(["mean", "count"])
    return (glob + (lev["mean"] - glob) * lev["count"] / (lev["count"] + 3)).to_dict(), float(glob)


def interval_score(r, hw, alpha=ALPHA):
    a = np.abs(r)
    return 2 * hw + (2 / alpha) * np.maximum(a - hw, 0)


def evaluate(p, feat, label):
    p = p.merge(feat, on="contrast_id", how="left")
    p["r"] = p.lnRR - p.pred
    rows = []
    for seed, ps in p.groupby("seed"):
        for fold, te in ps.groupby("fold"):
            cal = ps[ps.fold != fold]
            res = {"group_cvplus_contrast": np.full(len(te), q_group_weighted(cal.r, cal.group_id))}
            smax = cal.assign(a=cal.r.abs()).groupby("group_id").a.max()
            res["group_cvplus_simultaneous"] = np.full(len(te), q_order(smax))
            sig, glob = sigma_by_level(cal, "stress_family")
            qn = q_group_weighted(cal.r.abs() / cal.stress_family.map(sig).fillna(glob), cal.group_id)
            res["adaptive_stress_family"] = qn * te.stress_family.map(sig).fillna(glob).to_numpy()
            sfun = fit_scale(cal)
            sc_cal = cal.r.abs().to_numpy() / sfun(cal)
            s_te = sfun(te)
            res["ls_conformal"] = q_group_weighted(sc_cal, cal.group_id) * s_te
            smax_n = pd.Series(sc_cal, index=cal.index).groupby(cal.group_id).max()
            res["ls_conformal_simultaneous"] = q_order(smax_n) * s_te
            if "half90" in te.columns and te.half90.notna().all():
                res["model_ls"] = te.half90.to_numpy()
                sd_cal = cal.half90.to_numpy() / Z90
                res["model_ls_conformal"] = q_group_weighted(cal.r.abs().to_numpy() / sd_cal, cal.group_id) * \
                    te.half90.to_numpy() / Z90
            for m, hw in res.items():
                tmp = te[["contrast_id", "group_id", "stress_family", "lnRR"]].copy()
                tmp["covered"] = te.r.abs().to_numpy() <= hw
                tmp["half_width"], tmp["iscore"] = hw, interval_score(te.r.to_numpy(), hw)
                tmp["method"], tmp["seed"], tmp["fold"] = m, seed, fold
                rows.append(tmp)
    ev = pd.concat(rows, ignore_index=True)
    out = []
    for m, e in ev.groupby("method"):
        ps_ = e.groupby(["seed", "group_id"]).covered.agg(["mean", "all"])
        fam = e.groupby("stress_family").covered.mean()
        fam_n = e.groupby("stress_family").group_id.nunique()
        fam = fam[fam_n[fam.index] >= 5]
        out.append({"model": label, "method": m,
                    "target": "simultaneous" if m.endswith("simultaneous") else "single contrast",
                    "coverage_study_balanced": float(ps_["mean"].mean()),
                    "coverage_rows": float(e.covered.mean()),
                    "coverage_all_contrasts_of_study": float(ps_["all"].mean()),
                    "half_width_mean": float(e.half_width.mean()), "half_width_median": float(e.half_width.median()),
                    "interval_score_study_balanced": float(e.groupby("group_id").iscore.mean().mean()),
                    "min_family_coverage": float(fam.min()), "max_family_coverage": float(fam.max()),
                    "worst_family": str(fam.idxmin())})
    return pd.DataFrame(out), ev


def main():
    d = load_harmonized()
    # pre-experiment sampling variance: pooled CV^2 of the TRAIN arms / n of the arm (a row's own SD is NOT used,
    # it is only known after the experiment)
    cv2 = float(np.nanmedian(pd.concat([d.cv2_t, d.cv2_c])))
    nt = d.n_t.where(d.n_t > 0).fillna(d.n_t.median())
    nc = d.n_c.where(d.n_c > 0).fillna(d.n_c.median())
    d["vi_hat"] = cv2 / nt + cv2 / nc
    feat = d[["contrast_id", "stress_family", "cultivation_system", "yield_scope_v2", "comp_living_microbe",
              "vi_hat", "log_n_arm"]]
    py = pd.read_csv(OUT / "cv" / "cv_predictions.csv.gz")
    comp = pd.read_csv(OUT / "cv" / "comparison.csv")
    chosen = ["row_median|B|none|z"] + comp[comp.candidate != "row_median|B|none|z"].head(3).candidate.tolist()
    allres, evs, evs_all = [], [], []
    for c in chosen:
        s, ev = evaluate(py[py.candidate == c], feat, c)
        allres.append(s)
        evs_all.append(ev.assign(model=c))
        if c == "row_median|B|none|z":
            evs.append(ev.assign(model=c))
    rp = OUT / "rma" / "rma_predictions.csv"
    if rp.exists():
        r = pd.read_csv(rp)
        for c, x in r.groupby("candidate"):
            s, ev = evaluate(x, feat, "R:" + c)
            allres.append(s)
            evs_all.append(ev.assign(model="R:" + c))
    S = pd.concat(allres, ignore_index=True)
    # paired study bootstrap of the interval score vs the V2 deployed interval of the same target
    evall = pd.concat(evs_all, ignore_index=True)
    ref_m = {"single contrast": "group_cvplus_contrast", "simultaneous": "group_cvplus_simultaneous"}
    rng = np.random.default_rng(1)
    st = evall.groupby(["model", "method", "group_id", "seed"]).iscore.mean().groupby(["model", "method", "group_id"]).mean()
    lo, hi, rel = [], [], []
    for _, r in S.iterrows():
        a = st.loc[(r.model, r.method)]
        b = st.loc[("row_median|B|none|z", ref_m[r.target])]
        diff = (a - b.reindex(a.index)).to_numpy()
        bs = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(4000)])
        lo.append(np.percentile(bs, 2.5)); hi.append(np.percentile(bs, 97.5)); rel.append(diff.mean() / b.mean())
    S["iscore_rel_vs_V2"], S["iscore_diff_ci_lo"], S["iscore_diff_ci_hi"] = rel, lo, hi
    S["valid_coverage"] = np.where(S.target == "single contrast", S.coverage_study_balanced >= 0.89,
                                   S.coverage_all_contrasts_of_study >= 0.89)
    S["qualifies"] = S.valid_coverage & (S.iscore_rel_vs_V2 <= -0.05) & (S.iscore_diff_ci_hi < 0)
    S.to_csv(IV / "interval_comparison.csv", index=False)
    pd.concat(evs).to_csv(IV / "interval_rows_reference.csv.gz", index=False)
    write_json(IV / "run.json", {"finished": now(), "models": S.model.unique().tolist(), "alpha": ALPHA,
                                 "test_read": False})
    pd.set_option("display.width", 260)
    cols = ["model", "method", "coverage_study_balanced", "coverage_all_contrasts_of_study", "half_width_mean",
            "interval_score_study_balanced", "iscore_rel_vs_V2", "iscore_diff_ci_hi", "min_family_coverage", "qualifies"]
    print(S.sort_values(["method", "interval_score_study_balanced"])[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
