"""Exploratory grouped permutation importance (held-out studies) for the best non-baseline PRIMARY candidate.

For each outer fold the model is refitted with the hyper-parameters tuned in that fold (stored in cv_fold_metrics),
then each RAW feature (its one-hot block / missing indicator together) is permuted across the held-out rows and the
increase in group-balanced MAE is recorded. Not causal; with near-baseline models importances are near zero.
"""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from v2_common import OUT, write_json, now
from v2_models import FEATURE_SETS, Prep, fit_model, group_mae
from s04_train import outer_splits, SEEDS

ML = OUT / "ml"


def main():
    sel = json.loads((ML / "selection_report.json").read_text())["selection"]["PRIMARY_EXPANDED"]
    cand = sel["chosen"] if sel["chosen"].split("|")[0] not in ("row_mean", "row_median", "study_mean", "study_median") \
        else (sel["best_nonbaseline"] or {}).get("candidate")
    if not cand:
        return None
    fam, fs = cand.split("|")
    d = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    d["group_id"] = d.study_id.astype(str)
    fm = pd.read_csv(ML / "cv_fold_metrics.csv")
    fm = fm[(fm.dataset == "PRIMARY_EXPANDED") & (fm.family == fam) & (fm.fs == fs)]
    feats = FEATURE_SETS[fs]["num"] + FEATURE_SETS[fs]["cat"]
    rows = []
    rng = np.random.default_rng(7)
    for seed in SEEDS:
        for i, te_g in enumerate(outer_splits(d.group_id, seed)):
            p = json.loads(fm[(fm.seed == seed) & (fm.fold == i)].params.iloc[0])
            m = d.group_id.isin(te_g).to_numpy()
            tr, te = d[~m], d[m].copy()
            prep = Prep(FEATURE_SETS[fs])
            Xa = prep.fit_transform(tr, tr.lnRR.to_numpy(), tr.group_id)
            mdl = fit_model(fam, p, Xa, tr.lnRR.to_numpy(), tr.group_id)
            pr = lambda df: mdl.predict(np.asarray(prep.transform(df)) if fam == "catboost" else prep.transform(df))
            base = group_mae(te.lnRR, pr(te), te.group_id)
            for f in feats:
                inc = []
                for _ in range(5):
                    t2 = te.copy()
                    t2[f] = rng.permutation(t2[f].to_numpy())
                    inc.append(group_mae(t2.lnRR, pr(t2), t2.group_id) - base)
                rows.append({"feature": f, "seed": seed, "fold": i, "increase": float(np.mean(inc)),
                             "used_in_fold": f in (prep.num + prep.cat)})
    r = pd.DataFrame(rows)
    t = r.groupby("feature").agg(importance_mean=("increase", "mean"), importance_sd=("increase", "std"),
                                 share_folds_used=("used_in_fold", "mean")).reset_index().sort_values("importance_mean")
    t["candidate"] = cand
    t.to_csv(ML / "permutation_importance.csv", index=False)
    write_json(ML / "permutation_importance_meta.json", {"generated_at": now(), "candidate": cand,
                                                          "method": "grouped held-out permutation, 5 repeats x 25 folds"})
    return t


if __name__ == "__main__":
    print(main())
