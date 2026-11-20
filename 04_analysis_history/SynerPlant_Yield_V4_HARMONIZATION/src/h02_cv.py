"""H2 - grouped nested CV comparison of harmonization strategies on TRAIN (V3.1, 403 contrasts / 69 studies).

Outer: 5 study folds x 5 seeds, the SAME assignment as V2/V3.1 (s04_train.outer_splits). Inner: 3 study folds on the
outer-training studies, grid search, objective = group-balanced MAE. Every fitted quantity (imputation, scaling,
rare-level pooling, vi imputation, variance components, shrinkage factors, hyper-parameters) is learned on the
outer-training part only.

Strategies (advice items):
  1  representation : FH = V3.1 physical measures + composition flags + dose family + design precision (h01)
  2  partial pooling: pp_hier = median anchor + empirical-Bayes shrunken effects of stress family, biostimulant class
                      and their cell (rare cells shrink to the parent level); mixed_ri on FH
  3  precision      : sample weights 'study' (V2) vs 'mlre' (multilevel random-effects weights, vi imputed in-fold
                      from pooled CV and n) vs 'hybrid' (geometric mean); rf_meta = MetaForest-type weighted forest
  4  robust scaling : median/IQR scaling vs z-scaling (FH)
  5  location-scale : see h04_intervals.py (uses the predictions written here)
"""
from __future__ import annotations
import itertools, json, sys, time
import numpy as np, pandas as pd
from joblib import Parallel, delayed
from sklearn.linear_model import QuantileRegressor
from sklearn.ensemble import RandomForestRegressor
from h00_common import (OUT, SEEDS, load_harmonized, outer_splits, inner_splits, group_mae, paired_bootstrap,
                        fold_wins, GAIN_MIN, WINS_MIN, now, write_json)

sys.path.insert(0, str(__import__("h00_common").V2 / "src"))
from v2_models import RandomInterceptRidge, F1 as V2_F1  # noqa: E402  (read-only reuse)

CV = OUT / "cv"
CV.mkdir(parents=True, exist_ok=True)
MIN_GROUP_COVERAGE, RARE_MIN_GROUPS = 0.20, 5

NUM3 = ["log_application_count", "relative_dose", "relative_stress_level", "salinity_dSm_equiv_v3",
        "drought_supply_pct_v3", "stress_duration_days_v3"]
COMP = ["comp_bacteria", "comp_amf", "comp_fungi_other", "comp_seaweed", "comp_humic", "comp_protein_aa",
        "comp_chitosan", "comp_silicon", "comp_selenium", "comp_organic_amend", "comp_hormone",
        "comp_osmolyte_antiox", "comp_botanical", "comp_cell_free", "comp_living_microbe"]
FS = {
    "F1": {"num": V2_F1["num"], "flag": [], "cat": V2_F1["cat"]},
    "F2v3": {"num": NUM3, "flag": [], "cat": V2_F1["cat"] + ["stress_timing_v3", "substrate_type"]},
    "FH": {"num": NUM3 + ["log_dose_within_family_v3", "n_components", "log_n_arm"], "flag": COMP,
           "cat": ["stress_family", "application_route", "cultivation_system", "stress_timing_v3", "substrate_type",
                   "dose_family_v3", "yield_scope_v2", "harvest_window_v2"]},
}
FS["FHc"] = {**FS["FH"], "cat": FS["FH"]["cat"] + ["biostimulant_class"]}


# ------------------------------------------------------------------ in-fold preprocessing
def clean(s):
    return s.astype(object).where(s.notna() & ~s.astype(str).isin(["UNMAPPED", "NOT_REPORTED", "nan"]),
                                  "MISSING").astype(str)


class Prep:
    def __init__(self, fs, scaling="z"):
        self.fs, self.scaling = fs, scaling

    def fit(self, df, groups):
        ng = groups.nunique()
        self.num = [c for c in self.fs["num"] if groups[df[c].notna().to_numpy()].nunique() / ng >= MIN_GROUP_COVERAGE]
        self.flag = [c for c in self.fs["flag"] if groups[(df[c] == 1).to_numpy()].nunique() >= RARE_MIN_GROUPS]
        self.cat = []
        self.levels = {}
        for c in self.fs["cat"]:
            v = clean(df[c])
            if groups[(v != "MISSING").to_numpy()].nunique() / ng < MIN_GROUP_COVERAGE:
                continue
            gc = pd.Series(groups.values, index=v.index).groupby(v).nunique()
            self.levels[c] = sorted(l for l, n in gc.items() if n >= RARE_MIN_GROUPS and l != "MISSING")
            self.cat.append(c)
        self.center, self.scale = {}, {}
        for c in self.num:
            x = df[c]
            if self.scaling == "robust":
                med = float(np.nanmedian(x))
                iqr = float(np.nanpercentile(x, 75) - np.nanpercentile(x, 25))
                self.center[c], self.scale[c] = med, (iqr if iqr > 0 else (np.nanstd(x) or 1.0))
            else:
                xf = x.fillna(np.nanmedian(x))
                self.center[c], self.scale[c] = float(xf.mean()), float(xf.std() or 1.0)
            self.center[c + "__fill"] = float(np.nanmedian(x))
        self.columns = self.transform(df, fit=True).columns.tolist()
        return self

    def transform(self, df, fit=False):
        out = {}
        for c in self.num:
            x = df[c]
            out[c] = ((x.fillna(self.center[c + "__fill"]) - self.center[c]) / self.scale[c]).to_numpy()
            out[c + "__missing"] = x.isna().astype(float).to_numpy()
        for c in self.flag:
            out[c] = df[c].fillna(0).astype(float).to_numpy()
        for c in self.cat:
            v = clean(df[c])
            lv = self.levels[c]
            v2 = v.where(v.isin(lv) | (v == "MISSING"), "OTHER_RARE")
            for l in lv + ["OTHER_RARE", "MISSING"]:
                out[f"{c}={l}"] = (v2 == l).astype(float).to_numpy()
        X = pd.DataFrame(out, index=df.index)
        if not fit:
            X = X.reindex(columns=self.columns, fill_value=0.0)
        return X


# ------------------------------------------------------------------ precision weights (advice 3)
def impute_vi(tr, df):
    """vi of lnRR; missing values imputed with training-fold pooled CV^2 and training-fold median n per arm."""
    cv2 = float(np.nanmedian(pd.concat([tr.cv2_t, tr.cv2_c])))
    nt_med, nc_med = float(np.nanmedian(tr.n_t)), float(np.nanmedian(tr.n_c))
    nt = df.n_t.where(df.n_t > 0, nt_med).fillna(nt_med)
    nc = df.n_c.where(df.n_c > 0, nc_med).fillna(nc_med)
    cvt = df.cv2_t.fillna(cv2)
    cvc = df.cv2_c.fillna(cv2)
    vi = df.vi.where(df.vi > 0, cvt / nt + cvc / nc)
    return vi.clip(lower=1e-4).to_numpy()


def mlre_weights(y, vi, groups):
    """Approximate weights of a 2-level random-effects model (study / contrast): moments estimates of tau2_between
    and tau2_within, study weight 1/(tau_b + (tau_w + mean vi)/m), split inside the study by 1/(vi + tau_w)."""
    d = pd.DataFrame({"y": y, "vi": vi, "g": np.asarray(groups)})
    m = d.groupby("g").y.transform("size")
    sw = d.groupby("g").y.var(ddof=1).dropna()
    ni = d.groupby("g").size()
    within = float(np.average(sw, weights=ni[sw.index] - 1)) if len(sw) else 0.0
    tau_w = max(within - float(d.vi.mean()), 1e-4)
    gm = d.groupby("g").y.mean()
    tau_b = max(float(gm.var(ddof=1) - np.mean((tau_w + d.groupby("g").vi.mean()) / ni)), 1e-4)
    inner = 1 / (d.vi + tau_w)
    inner_share = inner / inner.groupby(d.g).transform("sum")
    W = 1 / (tau_b + (tau_w + d.groupby("g").vi.transform("mean")) / m)
    w = (W * inner_share).to_numpy()
    return w * len(w) / w.sum(), {"tau2_between": tau_b, "tau2_within": tau_w}


def study_weights(groups):
    g = pd.Series(np.asarray(groups))
    w = (1.0 / g.map(g.value_counts())).to_numpy()
    return w * len(w) / w.sum()


def make_weights(kind, tr):
    ws = study_weights(tr.group_id)
    if kind == "study":
        return ws
    wm, _ = mlre_weights(tr.lnRR.to_numpy(), impute_vi(tr, tr), tr.group_id)
    if kind == "mlre":
        return wm
    w = np.sqrt(ws * wm)
    return w * len(w) / w.sum()


# ------------------------------------------------------------------ partial pooling model (advice 2)
class HierPool:
    """y = median + shrunk(stress) + shrunk(class | after stress) + shrunk(stress x class cell | after both).
    Each level effect is the mean over studies (one vote per study-level) of the current residual, shrunk with
    n_studies / (n_studies + k); k = sigma2_study_resid / tau2_level from moments, then multiplied by `kmult`."""

    FACTORS = ["stress_family", "biostimulant_class", "cell"]

    def __init__(self, kmult=1.0):
        self.kmult = kmult

    @staticmethod
    def _cells(df):
        return clean(df.stress_family) + "|" + clean(df.biostimulant_class)

    def _key(self, df, f):
        return self._cells(df) if f == "cell" else clean(df[f])

    def fit(self, df, y, groups):
        self.anchor = float(np.median(y))
        r = np.asarray(y) - self.anchor
        self.maps = {}
        for f in self.FACTORS:
            key = self._key(df, f)
            sm = pd.DataFrame({"k": key.values, "g": np.asarray(groups), "r": r}).groupby(["k", "g"]).r.mean().reset_index()
            lev = sm.groupby("k").r.agg(["mean", "count", "var"])
            s2 = float(np.nanmean(lev["var"])) if lev["var"].notna().any() else float(sm.r.var())
            tau2 = max(float(np.average((lev["mean"]) ** 2, weights=lev["count"])) - s2 / max(lev["count"].mean(), 1), 1e-4)
            k = self.kmult * s2 / tau2
            eff = lev["mean"] * lev["count"] / (lev["count"] + k)
            self.maps[f] = eff.to_dict()
            r = r - key.map(self.maps[f]).fillna(0).to_numpy()
        return self

    def predict(self, df):
        p = np.full(len(df), self.anchor)
        for f in self.FACTORS:
            p = p + self._key(df, f).map(self.maps[f]).fillna(0).to_numpy()
        return p


# ------------------------------------------------------------------ candidates
GRIDS = {
    "quantile_l1": [{"alpha": a} for a in (1e-3, 3e-3, 1e-2, 3e-2, 1e-1)],
    "mixed_ri": [{"alpha": a} for a in (1, 10, 30, 100, 300)],
    "rf_meta": [{"min_samples_leaf": l, "max_features": f} for l in (10, 25) for f in (0.33, 0.66)],
    "pp_hier": [{"kmult": k} for k in (0.5, 1.0, 2.0, 4.0)],
}


def candidates():
    c = [("row_median", "B", "none", "z"), ("study_median", "B", "none", "z")]
    for fs in ["F1", "F2v3", "FH", "FHc"]:
        c.append(("quantile_l1", fs, "study", "z"))
    c += [("quantile_l1", "FH", "study", "robust"), ("quantile_l1", "FHc", "study", "robust"),
          ("quantile_l1", "FH", "mlre", "robust"), ("quantile_l1", "FH", "hybrid", "robust"),
          ("quantile_l1", "F1", "mlre", "z"), ("quantile_l1", "F1", "hybrid", "z"),
          ("mixed_ri", "FH", "none", "robust"), ("mixed_ri", "FHc", "none", "robust"),
          ("pp_hier", "B", "none", "z"),
          ("rf_meta", "FH", "study", "z"), ("rf_meta", "FH", "mlre", "z"), ("rf_meta", "FHc", "mlre", "z")]
    return c


def fit_predict(fam, fs, wkind, scaling, p, tr, te):
    y = tr.lnRR.to_numpy()
    if fam == "row_median":
        return np.full(len(te), float(np.median(y)))
    if fam == "study_median":
        w = study_weights(tr.group_id)
        o = np.argsort(y)
        c = np.cumsum(w[o]) / w.sum()
        return np.full(len(te), float(y[o][np.searchsorted(c, 0.5)]))
    if fam == "pp_hier":
        return HierPool(**p).fit(tr, y, tr.group_id).predict(te)
    prep = Prep(FS[fs], scaling).fit(tr, tr.group_id)
    Xa, Xb = prep.transform(tr), prep.transform(te)
    if fam == "mixed_ri":
        return RandomInterceptRidge(alpha=p["alpha"]).fit(Xa, y, tr.group_id).predict(Xb)
    w = make_weights(wkind, tr)
    if fam == "quantile_l1":
        return QuantileRegressor(quantile=0.5, alpha=p["alpha"], solver="highs").fit(Xa, y, sample_weight=w).predict(Xb)
    if fam == "rf_meta":
        m = RandomForestRegressor(n_estimators=300, min_samples_leaf=p["min_samples_leaf"],
                                  max_features=p["max_features"], random_state=0, n_jobs=1)
        return m.fit(Xa, y, sample_weight=w).predict(Xb)
    raise ValueError(fam)


def run_fold(cand, df, seed, fold, test_g):
    fam, fs, wkind, scaling = cand
    t0 = time.time()
    m = df.group_id.isin(test_g).to_numpy()
    tr, te = df[~m], df[m]
    grid = GRIDS.get(fam, [{}])
    best, inner = grid[0], np.nan
    if len(grid) > 1:
        scores = []
        isp = inner_splits(tr.group_id, seed + fold)
        for p in grid:
            sc = []
            for ig in isp:
                im = tr.group_id.isin(ig).to_numpy()
                sc.append(group_mae(tr.lnRR[im], fit_predict(fam, fs, wkind, scaling, p, tr[~im], tr[im]), tr.group_id[im]))
            scores.append(np.mean(sc))
        best, inner = grid[int(np.argmin(scores))], float(np.min(scores))
    pred = fit_predict(fam, fs, wkind, scaling, best, tr, te)
    name = f"{fam}|{fs}|{wkind}|{scaling}"
    out = te[["contrast_id", "study_id", "group_id", "lnRR"]].copy()
    out["pred"], out["candidate"], out["seed"], out["fold"] = pred, name, seed, fold
    met = {"candidate": name, "family": fam, "fs": fs, "weights": wkind, "scaling": scaling, "seed": seed,
           "fold": fold, "group_mae": group_mae(te.lnRR, pred, te.group_id), "inner_best": inner,
           "params": json.dumps(best), "seconds": round(time.time() - t0, 2)}
    return out, met


def summarize(preds, mets, ref="row_median|B|none|z"):
    rows = []
    pref, mref = preds[preds.candidate == ref], mets[mets.candidate == ref]
    for cand, p in preds.groupby("candidate"):
        ss = p.groupby("seed").apply(lambda x: group_mae(x.lnRR, x.pred, x.group_id), include_groups=False)
        y, yp = p.lnRR.to_numpy(), p.pred.to_numpy()
        r = {"candidate": cand, "group_mae": ss.mean(), "group_mae_sd_seeds": ss.std(ddof=1),
             "mae": float(np.mean(np.abs(y - yp))), "rmse": float(np.sqrt(np.mean((y - yp) ** 2))),
             "r2_oof": float(1 - ((y - yp) ** 2).sum() / ((y - y.mean()) ** 2).sum()),
             "bias_pred_minus_obs": float(np.mean(yp - y)),
             "bias_study_balanced": float((p.pred - p.lnRR).groupby(p.group_id).mean().mean())}
        if cand != ref:
            d, lo, hi, pb = paired_bootstrap(p, pref)
            wmed, wfrac = fold_wins(mets[mets.candidate == cand], mref)
        else:
            d, lo, hi, pb, wmed, wfrac = 0, 0, 0, 1, 0, 0
        r.update({"diff_vs_ref": d, "diff_ci_lo": lo, "diff_ci_hi": hi, "p_boot_not_better": pb,
                  "median_fold_wins_of_5": wmed, "share_seeds_3plus_wins": wfrac})
        rows.append(r)
    s = pd.DataFrame(rows)
    g_ref = float(s.loc[s.candidate == ref, "group_mae"].iloc[0])
    s["gain_vs_ref"] = (g_ref - s.group_mae) / g_ref
    s["passes_rule"] = (s.candidate != ref) & (s.gain_vs_ref >= GAIN_MIN) & (s.median_fold_wins_of_5 >= WINS_MIN) \
        & (s.diff_ci_hi < 0)
    return s.sort_values("group_mae")


def main(n_jobs=6):
    t0 = time.time()
    df = load_harmonized()
    tasks = [(c, df, s, i, tg) for c in candidates() for s in SEEDS for i, tg in enumerate(outer_splits(df.group_id, s))]
    print(len(tasks), "outer fits", flush=True)
    res = Parallel(n_jobs=n_jobs, verbose=2)(delayed(run_fold)(*t) for t in tasks)
    preds = pd.concat([r[0] for r in res], ignore_index=True)
    mets = pd.DataFrame([r[1] for r in res])
    preds.to_csv(CV / "cv_predictions.csv.gz", index=False)
    mets.to_csv(CV / "cv_fold_metrics.csv", index=False)
    s = summarize(preds, mets)
    s.to_csv(CV / "comparison.csv", index=False)
    # tuned parameters chosen per fold (stability)
    mets.groupby(["candidate", "params"]).size().rename("n_folds").reset_index().to_csv(CV / "chosen_params.csv", index=False)
    write_json(CV / "run.json", {"finished": now(), "minutes": round((time.time() - t0) / 60, 1), "seeds": SEEDS,
                                 "n_outer_fits": len(tasks), "reference": "row_median|B|none|z",
                                 "rule": {"gain_min": GAIN_MIN, "wins_min_of_5": WINS_MIN, "bootstrap_ci_hi_lt_0": True},
                                 "test_read": False})
    pd.set_option("display.width", 250)
    print(s[["candidate", "group_mae", "group_mae_sd_seeds", "gain_vs_ref", "diff_ci_lo", "diff_ci_hi",
             "median_fold_wins_of_5", "bias_study_balanced", "passes_rule"]].to_string(index=False))


if __name__ == "__main__":
    main()
