"""Fit and save the selected V2 yield model (all PRIMARY_EXPANDED studies; tuning by grouped CV only).

Intervals come from the cross-fitted (out-of-fold) residuals of all 69 studies (s06), so no studies have to be
withheld from fitting as in V1. Saved: outputs/model/V2_YIELD_MODEL.joblib + model_manifest.json.
"""
from __future__ import annotations
import json, sys
import joblib, numpy as np, pandas as pd, optuna, sklearn
from v2_common import OUT, now, write_json, sha256
from v2_models import FEATURE_SETS, Prep, Baseline, SPACES, fit_model, group_mae, V2YieldModel

optuna.logging.set_verbosity(optuna.logging.WARNING)
MOD = OUT / "model"
MOD.mkdir(parents=True, exist_ok=True)
BASE = ["row_mean", "row_median", "study_mean", "study_median"]


def main():
    sel = json.loads((OUT / "ml" / "selection_report.json").read_text())["selection"]["PRIMARY_EXPANDED"]
    fam, fs = sel["chosen"].split("|")
    d = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    d["group_id"] = d.study_id.astype(str)
    y, g = d.lnRR.to_numpy(), d.group_id
    intervals = json.loads((OUT / "uncertainty" / "deployment_intervals.json").read_text())
    if fam in BASE:
        model, prep, params, cv = Baseline(fam).fit(None, y, g), None, {}, None
    else:
        ug = np.array(sorted(g.unique()))
        perm = np.random.default_rng(20261111).permutation(ug)
        splits = [set(perm[i::5]) for i in range(5)]

        def obj(t):
            p = SPACES[fam](t)
            sc = []
            for te in splits:
                m = g.isin(te).to_numpy()
                pr = Prep(FEATURE_SETS[fs])
                Xa = pr.fit_transform(d[~m], y[~m], g[~m])
                mdl = fit_model(fam, p, Xa, y[~m], g[~m])
                Xb = pr.transform(d[m])
                sc.append(group_mae(y[m], mdl.predict(np.asarray(Xb) if fam == "catboost" else Xb), g[m]))
            return float(np.mean(sc))
        st = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=20261111))
        st.optimize(obj, n_trials=25)
        params, cv = st.best_params, st.best_value
        prep = Prep(FEATURE_SETS[fs])
        X = prep.fit_transform(d, y, g)
        model = fit_model(fam, params, X, y, g)
    obj_ = V2YieldModel(fam, fs, params, prep, model, intervals)
    path = MOD / "V2_YIELD_MODEL.joblib"
    joblib.dump(obj_, path)
    coefs = None
    if fam in ("ridge", "quantile_l1", "elasticnet", "huber"):
        coefs = pd.Series(model.coef_, index=prep.columns).sort_values(key=np.abs, ascending=False)
        coefs.to_csv(MOD / "coefficients.csv", header=["coef"])
    man = {"created_at": now(), "family": fam, "feature_set": fs, "params": params, "tuning_cv_group_mae": cv,
           "features_used": (prep.num + prep.cat) if prep else [], "n_rows": int(len(d)), "n_studies": int(g.nunique()),
           "selection": sel, "intervals": intervals, "model_sha256": sha256(path),
           "data_sha256": sha256(OUT / "data" / "PRIMARY_EXPANDED.csv"),
           "python": sys.version.split()[0], "sklearn": sklearn.__version__, "optuna": optuna.__version__,
           "test_policy": "external 2024-2026 TEST never read; no tuning or selection on TEST"}
    write_json(MOD / "model_manifest.json", man)
    return man


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str)[:3000])
