"""Yield V3 (EXPLORATORY, post-TEST): yield-component proxy for TRAIN studies that report fruit number and mean fruit
mass but no fruit yield.  ln(yield) = ln(number per plant) + ln(mean fruit mass)  =>  lnRR_proxy = lnRR_number +
lnRR_mass for the same SB/S arm pair (latest timepoint of each; per-plant fruit number only).
Variance: vi_number + vi_mass (independence assumed; the covariance is unknown -> sensitivity only).
Output: outputs/v3_yield/  (PROXY_CONTRASTS.csv, PRIMARY_PLUS_PROXY.csv, report.json). Never enters PRIMARY.
"""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from b03_build_biomass import connect3
from v2_common import OUT, now, write_json

V3Y = OUT / "v3_yield"
V3Y.mkdir(parents=True, exist_ok=True)


def main():
    con = connect3()
    cc = pd.read_sql("SELECT * FROM contrast_candidates WHERE contrast_type='SB_vs_S' AND endpoint IN "
                     "('FRUIT_YIELD','FRUIT_NUMBER','MEAN_FRUIT_MASS')", con)
    con.close()
    cc = cc[pd.to_numeric(cc.year, errors="coerce") <= 2023]
    has_yield = set(cc[cc.endpoint == "FRUIT_YIELD"].study_id)
    k = cc[cc.endpoint.isin(["FRUIT_NUMBER", "MEAN_FRUIT_MASS"]) & ~cc.study_id.isin(has_yield)].copy()
    k = k[(k.mean_t > 0) & (k.mean_c > 0) & k.effect.notna()]
    k["pair"] = k.study_id + "|" + k.experiment_key.astype(str) + "|" + k.arm_key_t + "||" + k.arm_key_c
    k["_tp"] = pd.to_numeric(k.timepoint_days, errors="coerce").fillna(-1)
    un = k.unit_norm.fillna("").astype(str).str.lower()
    k = k[~((k.endpoint == "FRUIT_NUMBER") & un.str.contains("m2|ha|plot"))]          # per-plant counts only
    k = k.sort_values(["pair", "endpoint", "_tp"], ascending=[True, True, False]).drop_duplicates(["pair", "endpoint"])
    w = k.pivot(index="pair", columns="endpoint", values=["effect", "var_effect", "contrast_id"]).dropna(
        subset=[("effect", "FRUIT_NUMBER"), ("effect", "MEAN_FRUIT_MASS")])
    meta = k.drop_duplicates("pair").set_index("pair")[["study_id", "experiment_key", "arm_key_t", "arm_key_c",
                                                        "stress_code", "bio_code", "year", "doi"]]
    px = meta.loc[w.index].copy()
    px["lnRR_number"] = w[("effect", "FRUIT_NUMBER")].astype(float)
    px["lnRR_mass"] = w[("effect", "MEAN_FRUIT_MASS")].astype(float)
    px["lnRR"] = px.lnRR_number + px.lnRR_mass
    px["vi"] = w[("var_effect", "FRUIT_NUMBER")].astype(float) + w[("var_effect", "MEAN_FRUIT_MASS")].astype(float)
    px["contrast_id"] = "PROXY:" + w[("contrast_id", "FRUIT_NUMBER")].astype(str)
    px["yield_tier"] = "COMPONENT_PROXY"
    px = px.reset_index(drop=True)
    px.to_csv(V3Y / "PROXY_CONTRASTS.csv", index=False)
    prim = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    cols = ["contrast_id", "study_id", "lnRR", "vi", "yield_tier"]
    both = pd.concat([prim[cols], px[cols]], ignore_index=True)
    both.to_csv(V3Y / "PRIMARY_PLUS_PROXY.csv", index=False)
    rep = {"generated_at": now(), "status": "EXPLORATORY_POST_TEST_SENSITIVITY_ONLY",
           "proxy_contrasts": int(len(px)), "proxy_studies": int(px.study_id.nunique()),
           "proxy_lnRR_median": float(px.lnRR.median()), "primary_studies": int(prim.study_id.nunique()),
           "combined_studies": int(both.study_id.nunique())}
    write_json(V3Y / "proxy_report.json", rep)
    return rep


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
