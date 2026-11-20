"""V3.1 (post-TEST, exploratory): repeated grouped nested CV on the corrected TRAIN sets with the frozen machinery
(s04_train, v2_models, s05_evaluate imported unchanged; paths and feature sets redirected in memory).
Target from env V31_TARGET (yield | biomass) so that joblib workers apply the same patch on import.
  set V31_TARGET=yield && python -c "import r04_v31_train as R; R.main()"
"""
from __future__ import annotations
import os, time
import pandas as pd
from joblib import Parallel, delayed
import v2_models as M
import s04_train as T
from v2_common import OUT, now, write_json

TARGET = os.environ.get("V31_TARGET", "yield")
BASE = OUT / "v31" / TARGET
NUM3 = ["log_application_count", "relative_dose", "relative_stress_level", "salinity_dSm_equiv_v3",
        "drought_supply_pct_v3", "stress_duration_days_v3"]
CAT1 = M.F1["cat"]
EXTRA = ["organ_scope_v2"] if TARGET == "biomass" else []
F2v3 = {"num": NUM3, "cat": CAT1 + ["stress_timing_v3", "substrate_type"] + EXTRA, "missing_ind": True}
F5 = {"num": ["log_application_count", "stress_duration_days_v3", "salinity_dSm_equiv_v3", "drought_supply_pct_v3",
              "log_dose_within_family_v3"],
      "cat": ["stress_family", "biostimulant_class", "application_route", "cultivation_system", "stress_timing_v3",
              "dose_family_v3"] + EXTRA, "missing_ind": True}
FS = {"F1": M.F1, "F2": M.F2, "F2v3": F2v3, "F5": F5}
M.FEATURE_SETS = FS
T.FEATURE_SETS = FS
T.DATA, T.ML = BASE / "data", BASE / "ml"
T.ML.mkdir(parents=True, exist_ok=True)


def run_fold_v31(*a):
    return T.run_fold(*a)


def plan():
    jobs = [("PRIMARY_EXPANDED", "B", b) for b in T.BASELINES]
    jobs += [("PRIMARY_EXPANDED", fs, fam) for fs in FS for fam in ("ridge", "quantile_l1", "catboost")]
    jobs += [("PRIMARY_EXPANDED", "F5", fam) for fam in ("elasticnet", "hgb", "mixed_ri")]
    return jobs


def main(n_jobs=6):
    t0 = time.time()
    d = pd.read_csv(T.DATA / "PRIMARY_EXPANDED.csv", low_memory=False)
    d["group_id"] = d.study_id.astype(str)
    d = d.reset_index(drop=True)
    for name, sub in [("V1_EQUIVALENT", d[d.in_v1_train.astype(bool)]),
                      ("STRICT_SENSITIVITY", d[d.yield_tier.astype(str).str.upper() == "STRICT"])]:
        sub.to_csv(T.DATA / f"{name}.csv", index=False)          # files read by s05's variance decomposition
    tasks = [("PRIMARY_EXPANDED", d, fs, fam, s, i, g) for _, fs, fam in plan() for s in T.SEEDS
             for i, g in enumerate(T.outer_splits(d.group_id, s))]
    print(TARGET, len(tasks), "outer fits", flush=True)
    res = Parallel(n_jobs=n_jobs, verbose=2)(delayed(run_fold_v31)(*t) for t in tasks)
    pd.concat([r[0] for r in res], ignore_index=True).to_csv(T.ML / "cv_predictions.csv.gz", index=False)
    pd.DataFrame([r[1] for r in res]).to_csv(T.ML / "cv_fold_metrics.csv", index=False)
    write_json(T.ML / "train_run.json", {"finished": now(), "minutes": round((time.time() - t0) / 60, 1),
                                         "target": TARGET, "feature_sets": FS, "n_outer_fits": len(tasks)})
    import s05_evaluate as E
    E.ML, E.DATA = T.ML, T.DATA
    return E.main()
