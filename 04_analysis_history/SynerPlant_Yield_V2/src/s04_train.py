"""Stage V/VI - repeated grouped nested CV, baselines, model families, F0-F4 ablation, model selection.

Outer: 5 group folds (study = independent unit) x 5 fixed seeds; identical splits for every candidate.
Inner: Optuna TPE (fixed seed) on 3 group folds of the outer-training studies only.
The external 2024-2026 TEST is never read.
"""
from __future__ import annotations
import json, time, sys
import numpy as np, pandas as pd, optuna
from joblib import Parallel, delayed
from v2_common import OUT, now, write_json
from v2_models import (FEATURE_SETS, Prep, Baseline, SPACES, N_TRIALS, fit_model, group_mae)

optuna.logging.set_verbosity(optuna.logging.WARNING)
ML = OUT / "ml"
ML.mkdir(parents=True, exist_ok=True)
DATA = OUT / "data"
SEEDS = [20261111, 20261112, 20261113, 20261114, 20261115]
K = 5
BASELINES = ["row_mean", "row_median", "study_mean", "study_median"]


def outer_splits(groups: pd.Series, seed: int, k: int = K):
    """Random study-to-fold assignment, balanced on study count (round robin over a seeded permutation)."""
    ug = np.array(sorted(groups.unique()))
    perm = np.random.default_rng(seed).permutation(ug)
    return [set(perm[i::k]) for i in range(k)]


def inner_splits(groups: pd.Series, seed: int, k: int = 3):
    ug = np.array(sorted(groups.unique()))
    perm = np.random.default_rng(seed).permutation(ug)
    return [set(perm[i::k]) for i in range(k)]


def tune(family, fs, tr: pd.DataFrame, seed: int):
    y, g = tr.lnRR.to_numpy(), tr.group_id
    splits = inner_splits(g, seed)
    cache = []
    for test_g in splits:
        m = g.isin(test_g).to_numpy()
        prep = Prep(FEATURE_SETS[fs])
        Xa = prep.fit_transform(tr[~m], y[~m], g[~m])
        Xb = prep.transform(tr[m])
        cache.append((Xa, y[~m], g[~m], Xb, y[m], g[m]))

    def obj(trial):
        p = SPACES[family](trial)
        sc = []
        for Xa, ya, ga, Xb, yb, gb in cache:
            mdl = fit_model(family, p, Xa, ya, ga)
            sc.append(group_mae(yb, mdl.predict(np.asarray(Xb) if family == "catboost" else Xb), gb))
        return float(np.mean(sc))

    st = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    st.optimize(obj, n_trials=N_TRIALS[family])
    hist = [{"trial": t.number, "value": t.value, **t.params} for t in st.trials]
    return st.best_params, st.best_value, hist


def run_fold(dataset, df, fs, family, seed, fold_id, test_g):
    m = df.group_id.isin(test_g).to_numpy()
    tr, te = df[~m], df[m]
    t0 = time.time()
    if family in BASELINES:
        mdl = Baseline(family).fit(None, tr.lnRR.to_numpy(), tr.group_id)
        pred, params, inner, hist = mdl.predict(te), {}, np.nan, []
    else:
        params, inner, hist = tune(family, fs, tr, seed + fold_id)
        prep = Prep(FEATURE_SETS[fs])
        Xa = prep.fit_transform(tr, tr.lnRR.to_numpy(), tr.group_id)
        mdl = fit_model(family, params, Xa, tr.lnRR.to_numpy(), tr.group_id)
        Xb = prep.transform(te)
        pred = mdl.predict(np.asarray(Xb) if family == "catboost" else Xb)
    out = te[["contrast_id", "study_id", "group_id", "lnRR"]].copy()
    out["pred"] = pred
    out["dataset"], out["fs"], out["family"], out["seed"], out["fold"] = dataset, fs, family, seed, fold_id
    met = {"dataset": dataset, "fs": fs, "family": family, "seed": seed, "fold": fold_id,
           "n_test_rows": int(len(te)), "n_test_groups": int(te.group_id.nunique()),
           "group_mae": group_mae(te.lnRR, pred, te.group_id), "mae": float(np.mean(np.abs(te.lnRR - pred))),
           "rmse": float(np.sqrt(np.mean((te.lnRR - pred) ** 2))), "inner_best": inner,
           "params": json.dumps(params), "seconds": round(time.time() - t0, 2)}
    hist = [{**h, "dataset": dataset, "fs": fs, "family": family, "seed": seed, "fold": fold_id} for h in hist]
    return out, met, hist


def plan():
    jobs = []
    prim = ["PRIMARY_EXPANDED", "V1_EQUIVALENT"]
    for ds in prim + ["STRICT_SENSITIVITY", "QUALITY_CORE", "SENSITIVITY_STRICT_PLUS_ASSUMED", "SENSITIVITY_NO_ROB_HIGH",
                      "SENSITIVITY_PLUS_BOX_AMBIG_SYNTH", "SENSITIVITY_NO_SOURCE_FLAGS"]:
        for b in BASELINES:
            jobs.append((ds, "B", b))
    for ds in prim:
        for fs in ["F0", "F1", "F2", "F3", "F4"]:
            for fam in ["ridge", "quantile_l1", "catboost"]:
                jobs.append((ds, fs, fam))
    for fam in ["elasticnet", "huber", "hgb", "mixed_ri"]:
        for fs in ["F1", "F3"]:
            jobs.append(("PRIMARY_EXPANDED", fs, fam))
    return jobs


def main(n_jobs=6, only=None):
    t0 = time.time()
    data = {}
    tasks = []
    for ds, fs, fam in plan():
        if only and ds not in only:
            continue
        if ds not in data:
            d = pd.read_csv(DATA / f"{ds}.csv", low_memory=False)
            d["group_id"] = d["study_id"].astype(str)
            data[ds] = d.reset_index(drop=True)
        d = data[ds]
        for seed in SEEDS:
            for i, test_g in enumerate(outer_splits(d.group_id, seed)):
                tasks.append((ds, d, fs, fam, seed, i, test_g))
    print(f"{len(tasks)} outer fits", flush=True)
    res = Parallel(n_jobs=n_jobs, verbose=5)(delayed(run_fold)(*t) for t in tasks)
    preds = pd.concat([r[0] for r in res], ignore_index=True)
    mets = pd.DataFrame([r[1] for r in res])
    hist = pd.DataFrame([h for r in res for h in r[2]])
    preds.to_csv(ML / "cv_predictions.csv.gz", index=False)
    mets.to_csv(ML / "cv_fold_metrics.csv", index=False)
    hist.to_csv(ML / "optuna_history.csv.gz", index=False)
    split_record = {ds: {str(s): [sorted(map(str, f)) for f in outer_splits(d.group_id, s)] for s in SEEDS}
                    for ds, d in data.items()}
    write_json(ML / "outer_splits.json", split_record)
    write_json(ML / "train_run.json", {"finished": now(), "minutes": round((time.time() - t0) / 60, 1),
                                       "seeds": SEEDS, "k": K, "n_outer_fits": len(tasks)})
    print("done", round((time.time() - t0) / 60, 1), "min")


if __name__ == "__main__":
    main(only=sys.argv[1:] or None)
