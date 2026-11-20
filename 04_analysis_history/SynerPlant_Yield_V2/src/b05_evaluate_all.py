"""Biomass V2 - selection (s05), intervals (s06), Python meta (s07) and confirmatory R meta (s16), all imported
unchanged and redirected to outputs/biomass_v2/. V1 reference values are replaced by the V1 BIOMASS run
(SynerPlant_Local_ML/outputs/biomass: mean baseline group-MAE 0.2571, conformal q 1.2246 on 36 calibration groups)."""
from __future__ import annotations
import json
import s05_evaluate as E
import s06_uncertainty as U
import s07_meta as MT
import s16_meta_R as R
from v2_common import OUT, V1_ML, write_json

BIO = OUT / "biomass_v2"
for p in ("ml", "uncertainty", "meta"):
    (BIO / p).mkdir(parents=True, exist_ok=True)
v1m = json.loads((V1_ML / "outputs" / "biomass" / "candidate_manifest.json").read_text())
E.ML, E.DATA = BIO / "ml", BIO / "data"
E.V1_REFERENCE = {"group_mae": v1m["selected_cv_group_MAE"], "note": "V1 BIOMASS run (mean baseline); different "
                  "CV splits/sample/calibration hold-out; not directly comparable"}
U.ML, U.DATA, U.UNC = BIO / "ml", BIO / "data", BIO / "uncertainty"
MT.DATA, MT.META = BIO / "data", BIO / "meta"
R.META = BIO / "meta"


class _OutProxy:                      # s16 builds OUT / "data" -> redirect to the biomass data folder
    def __truediv__(self, x):
        return BIO / x


def main():
    sel = E.main()
    S, agg = U.main()
    dep = BIO / "uncertainty" / "deployment_intervals.json"
    a = json.loads(dep.read_text())
    a["v1_half_width"], a["v1_calibration_studies"] = v1m["conformal_q_lnRR"], v1m["model_calibration_groups"]
    write_json(dep, a)
    MT.main()
    R.OUT = _OutProxy()
    t = R.main()
    return sel, a, t


if __name__ == "__main__":
    import pandas as pd
    sel, a, t = main()
    print(json.dumps(sel["selection"]["PRIMARY_EXPANDED"], indent=1, default=str))
    print(json.dumps({k: a[k] for k in ("single_contrast_q", "simultaneous_q", "calibration_studies", "model",
                                        "v1_half_width")}, indent=1))
    pd.set_option("display.width", 250)
    print(t[["set", "k_studies", "R_mu", "R_pct", "R_CI95_CR2", "R_PI95_new_study", "abs_diff_mu"]].to_string())
