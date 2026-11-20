"""H11 - (A) grouped learning curves (TFM 3.13) and (B) applicability domain / OOD (TFM 3.14) on TRAIN.

(A) Same 5 x 5 outer study folds. Inside each outer-training part a random fraction of STUDIES is kept
    (20 ... 100 %, 3 draws), models are refitted and scored on the untouched outer-test studies (group-MAE).
    Models: median (V2), multilevel-weighted mean (V4 analogue), quantile L1 on FH (fixed alpha 0.01, i.e. using
    the features), MetaForest-type forest on FH. A falling curve = data-limited; a flat curve near the median =
    little signal in the available features.
(B) FH design (in-fold robust scaling). Distance of a row = mean Euclidean distance to its k = 5 nearest TRAIN
    rows of OTHER studies. Threshold = 95th percentile of the leave-study-out distances inside the training part.
    Rows above it are OUT_OF_DOMAIN. Errors and interval coverage (V4 multilevel mean +/- frozen q = 0.806) are
    compared in vs out of domain. The TEST rows are scored descriptively with the full-TRAIN fit (TEST already
    evaluated; nothing is selected on it).
"""
from __future__ import annotations
import json, sys
import numpy as np, pandas as pd
from joblib import Parallel, delayed
from sklearn.linear_model import QuantileRegressor
from sklearn.ensemble import RandomForestRegressor
from h00_common import OUT, V2, V4, SEEDS, load_harmonized, outer_splits, group_mae, write_json, now
from h02_cv import Prep, FS, make_weights, study_weights, mlre_weights, impute_vi
import h01_features as H1

LA = OUT / "learning_ad"
LA.mkdir(parents=True, exist_ok=True)
FRACS = [0.2, 0.35, 0.5, 0.65, 0.8, 1.0]
K_NN = 5


def wmean_mlre(tr):
    w, _ = mlre_weights(tr.lnRR.to_numpy(), impute_vi(tr, tr), tr.group_id)
    return float(np.sum(w * tr.lnRR) / np.sum(w))


def fit_all(tr, te):
    y = tr.lnRR.to_numpy()
    out = {"median (V2)": np.full(len(te), np.median(y)), "multilevel mean (V4)": np.full(len(te), wmean_mlre(tr))}
    prep = Prep(FS["FH"], "robust").fit(tr, tr.group_id)
    Xa, Xb = prep.transform(tr), prep.transform(te)
    w = study_weights(tr.group_id)
    out["quantile L1, harmonized features"] = QuantileRegressor(quantile=0.5, alpha=0.01, solver="highs").fit(
        Xa, y, sample_weight=w).predict(Xb)
    out["weighted forest, harmonized features"] = RandomForestRegressor(
        n_estimators=200, min_samples_leaf=10, max_features=0.33, random_state=0, n_jobs=1).fit(
        Xa, y, sample_weight=make_weights("mlre", tr)).predict(Xb)
    return out


def lc_task(df, seed, fold, test_g, frac, rep):
    m = df.group_id.isin(test_g).to_numpy()
    tr, te = df[~m], df[m]
    ug = np.array(sorted(tr.group_id.unique()))
    if frac < 1:
        keep = np.random.default_rng(seed * 100 + fold * 10 + rep).choice(ug, max(5, round(frac * len(ug))), replace=False)
        tr = tr[tr.group_id.isin(keep)]
    preds = fit_all(tr, te)
    return [{"seed": seed, "fold": fold, "frac": frac, "rep": rep, "n_train_studies": tr.group_id.nunique(),
             "model": k, "group_mae": group_mae(te.lnRR, v, te.group_id)} for k, v in preds.items()]


def learning_curves(df):
    tasks = [(df, s, i, tg, f, r) for s in SEEDS for i, tg in enumerate(outer_splits(df.group_id, s))
             for f in FRACS for r in (range(3) if f < 1 else range(1))]
    res = Parallel(n_jobs=6, verbose=1)(delayed(lc_task)(*t) for t in tasks)
    L = pd.DataFrame([x for r in res for x in r])
    L.to_csv(LA / "learning_curves_folds.csv", index=False)
    S = L.groupby(["model", "frac"]).agg(n_train_studies=("n_train_studies", "mean"), mae=("group_mae", "mean"),
                                         sd=("group_mae", "std"), n=("group_mae", "size")).reset_index()
    # paired gain vs median per (seed, fold, frac, rep)
    piv = L.pivot_table(index=["seed", "fold", "frac", "rep"], columns="model", values="group_mae")
    g = []
    for mdl in piv.columns:
        if mdl == "median (V2)":
            continue
        d = (piv["median (V2)"] - piv[mdl]).groupby(level="frac")
        g.append(pd.DataFrame({"model": mdl, "gain_mean": d.mean(), "gain_lo": d.quantile(0.1), "gain_hi": d.quantile(0.9)}))
    G = pd.concat(g).reset_index()
    S.to_csv(LA / "learning_curves_summary.csv", index=False)
    G.to_csv(LA / "learning_curves_gain.csv", index=False)
    return S, G


# ------------------------------------------------------------------ applicability domain
def add_flags(d):
    txt = (d.f_composition.fillna("") + " | " + d.f_microorganism.fillna("") + " | " + d.f_strain.fillna("") + " | "
           + d.context_product_name_all.fillna("")).str.lower()
    txt = txt.str.replace(r"\bno (si|silicon|se|selenium)\b", " ", regex=True)
    cls = d.biostimulant_class.fillna("")
    mixture = cls.isin(H1.MIXTURE_CLASSES)
    for col, (rx, classes) in H1.COMP.items():
        hit = txt.str.contains(rx, regex=True)
        if col in H1.CONSTITUENT_ONLY:
            hit = hit & mixture
        d[col] = (hit | cls.isin(classes)).astype(int)
    d["comp_microbe_unspecified"] = (cls.isin(["MICROBIAL_UNSPECIFIED", "MICROBIAL_CONSORTIUM_MIXED"]) &
                                     (d[["comp_bacteria", "comp_amf", "comp_fungi_other"]].sum(1) == 0)).astype(int)
    d["comp_inorganic_other"] = ((cls == H1.OTHER_INORGANIC) & (d.comp_silicon + d.comp_selenium == 0)).astype(int)
    flags = [c for c in d.columns if c.startswith("comp_")]
    d["n_components"] = d[flags].sum(1)
    d["comp_living_microbe"] = ((d.comp_bacteria + d.comp_amf + d.comp_fungi_other + d.comp_microbe_unspecified) > 0
                                & (d.comp_cell_free == 0)).astype(int)
    n_arm = pd.concat([d.n_t, d.n_c], axis=1).mean(1)
    d["log_n_arm"] = np.log(n_arm.where(n_arm > 0))
    return d


def knn_dist(Xq, gq, Xr, gr, k=K_NN):
    Xq, Xr = np.asarray(Xq, float), np.asarray(Xr, float)
    D = np.sqrt(((Xq[:, None, :] - Xr[None, :, :]) ** 2).sum(-1))
    D[np.asarray(gq)[:, None] == np.asarray(gr)[None, :]] = np.inf
    D.sort(axis=1)
    return D[:, :k].mean(1)


def ad_fold(df, seed, fold, test_g, q_single):
    m = df.group_id.isin(test_g).to_numpy()
    tr, te = df[~m], df[m]
    prep = Prep(FS["FH"], "robust").fit(tr, tr.group_id)
    Xa, Xb = prep.transform(tr).to_numpy(), prep.transform(te).to_numpy()
    sc = Xa.std(0)
    sc[sc == 0] = 1
    Xa, Xb = Xa / sc, Xb / sc
    d_tr = knn_dist(Xa, tr.group_id, Xa, tr.group_id)
    thr = float(np.percentile(d_tr, 95))
    d_te = knn_dist(Xb, te.group_id, Xa, tr.group_id)
    mu_v4 = wmean_mlre(tr)
    med = float(np.median(tr.lnRR))
    o = te[["contrast_id", "group_id", "stress_family", "lnRR"]].copy()
    o["dist"], o["thr"], o["ood"] = d_te, thr, d_te > thr
    o["err_v4"], o["err_med"] = (o.lnRR - mu_v4).abs(), (o.lnRR - med).abs()
    o["covered_v4"] = o.err_v4 <= q_single
    o["seed"], o["fold"] = seed, fold
    return o


def applicability(df):
    reg = json.loads((V4 / "prereg" / "PREREG_V4_TEST_POSTHOC.json").read_text(encoding="utf-8"))
    q1 = reg["model_A_new"]["intervals_90"]["single_contrast_q"]
    res = Parallel(n_jobs=6)(delayed(ad_fold)(df, s, i, tg, q1) for s in SEEDS
                             for i, tg in enumerate(outer_splits(df.group_id, s)))
    A = pd.concat(res, ignore_index=True)
    A.to_csv(LA / "ad_cv_rows.csv.gz", index=False)
    # TEST rows, full TRAIN fit (descriptive)
    te = pd.read_csv(V2 / "outputs" / "v31" / "yield" / "test_inputs" / "TEST_PRIMARY.csv", low_memory=False)
    te = add_flags(te)
    te["group_id"] = "T_" + te.study_id.astype(str)
    prep = Prep(FS["FH"], "robust").fit(df, df.group_id)
    Xa, Xb = prep.transform(df).to_numpy(), prep.transform(te).to_numpy()
    sc = Xa.std(0)
    sc[sc == 0] = 1
    Xa, Xb = Xa / sc, Xb / sc
    thr = float(np.percentile(knn_dist(Xa, df.group_id, Xa, df.group_id), 95))
    T = te[["contrast_id", "study_id", "stress_family", "lnRR"]].copy()
    T["dist"] = knn_dist(Xb, te.group_id, Xa, df.group_id)
    T["thr"], T["ood"] = thr, T.dist > thr
    mu = reg["model_A_new"]["point_lnRR"]
    T["err_v4"] = (T.lnRR - mu).abs()
    T["covered_v4"] = T.err_v4 <= q1
    T.to_csv(LA / "ad_test_rows.csv", index=False)
    summ = {"cv": {k: {"share_rows": float(len(g) / len(A)), "group_mae_v4": group_mae(g.lnRR, g.lnRR - g.err_v4, g.group_id),
                       "coverage_v4": float(g.covered_v4.mean()), "n_rows": int(len(g))}
                   for k, g in A.groupby(A.ood.map({True: "out_of_domain", False: "in_domain"}))},
            "test": {k: {"n_rows": int(len(g)), "n_studies": int(g.study_id.nunique()), "mae_v4": float(g.err_v4.mean()),
                         "coverage_v4": float(g.covered_v4.mean())}
                     for k, g in T.groupby(T.ood.map({True: "out_of_domain", False: "in_domain"}))},
            "threshold_full_train": thr, "k": K_NN, "generated": now()}
    write_json(LA / "ad_summary.json", summ)
    return summ


if __name__ == "__main__":
    df = load_harmonized()
    what = sys.argv[1:] or ["lc", "ad"]
    if "lc" in what:
        S, G = learning_curves(df)
        print(S.round(3).to_string(index=False)); print(G.round(3).to_string(index=False))
    if "ad" in what:
        print(json.dumps(applicability(df), indent=1))
