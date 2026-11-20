"""Biomass V2 - repeated grouped nested CV with the frozen yield machinery (s04_train.py, v2_models.py imported
unchanged). Only (a) the data/output folders and (b) the F3/F4 definition descriptors are redirected:
yield_scope/harvest_window/denominator (yield-specific) are replaced by organ_scope_v2, biomass_denominator_v2 and
log_measurement_day. The patch is applied at import, so every joblib worker that unpickles run_fold_b() gets it.
Output: outputs/biomass_v2/ml/
"""
from __future__ import annotations
import sys, time
import pandas as pd
from joblib import Parallel, delayed
import v2_models as M
import s04_train as T
from v2_common import OUT, now, write_json

BIO = OUT / "biomass_v2"
F3B = {"num": M.F2["num"] + ["log_measurement_day"],
       "cat": M.F2["cat"] + ["organ_scope_v2", "biomass_denominator_v2"], "missing_ind": True}
FEATURE_SETS_B = {"F0": M.F0, "F1": M.F1, "F2": M.F2, "F3": F3B,
                  "F4": {**F3B, "eb_encode": ["stress_family", "biostimulant_class", "application_route"]}}
M.FEATURE_SETS = FEATURE_SETS_B          # in-memory only; v2_models.py on disk is unchanged
T.FEATURE_SETS = FEATURE_SETS_B
T.DATA, T.ML = BIO / "data", BIO / "ml"
T.ML.mkdir(parents=True, exist_ok=True)


def run_fold_b(*a):
    return T.run_fold(*a)


def plan():
    jobs = []
    prim = ["PRIMARY_EXPANDED", "V1_EQUIVALENT"]
    for ds in prim + ["STRICT_SENSITIVITY", "QUALITY_CORE", "SENSITIVITY_WHOLE_PLANT", "SENSITIVITY_SHOOT",
                      "SENSITIVITY_NO_ROB_HIGH", "SENSITIVITY_PLUS_BASIS_UNCONFIRMED_SYNTH"]:
        for b in T.BASELINES:
            jobs.append((ds, "B", b))
    for ds in prim:
        for fs in ["F0", "F1", "F2", "F3", "F4"]:
            for fam in ["ridge", "quantile_l1", "catboost"]:
                jobs.append((ds, fs, fam))
    for fam in ["elasticnet", "huber", "hgb", "mixed_ri"]:
        for fs in ["F1", "F3"]:
            jobs.append(("PRIMARY_EXPANDED", fs, fam))
    return jobs


def main(n_jobs=6):
    t0 = time.time()
    data, tasks = {}, []
    for ds, fs, fam in plan():
        if ds not in data:
            d = pd.read_csv(T.DATA / f"{ds}.csv", low_memory=False)
            d["group_id"] = d["study_id"].astype(str)
            data[ds] = d.reset_index(drop=True)
        d = data[ds]
        for seed in T.SEEDS:
            for i, test_g in enumerate(T.outer_splits(d.group_id, seed)):
                tasks.append((ds, d, fs, fam, seed, i, test_g))
    print(f"{len(tasks)} outer fits", flush=True)
    res = Parallel(n_jobs=n_jobs, verbose=5)(delayed(run_fold_b)(*t) for t in tasks)
    pd.concat([r[0] for r in res], ignore_index=True).to_csv(T.ML / "cv_predictions.csv.gz", index=False)
    pd.DataFrame([r[1] for r in res]).to_csv(T.ML / "cv_fold_metrics.csv", index=False)
    pd.DataFrame([h for r in res for h in r[2]]).to_csv(T.ML / "optuna_history.csv.gz", index=False)
    write_json(T.ML / "outer_splits.json", {ds: {str(s): [sorted(map(str, f)) for f in T.outer_splits(d.group_id, s)]
                                                 for s in T.SEEDS} for ds, d in data.items()})
    write_json(T.ML / "train_run.json", {"finished": now(), "minutes": round((time.time() - t0) / 60, 1),
                                         "seeds": T.SEEDS, "k": T.K, "n_outer_fits": len(tasks),
                                         "feature_sets": FEATURE_SETS_B})
    print("done", round((time.time() - t0) / 60, 1), "min")


if __name__ == "__main__":
    main()
