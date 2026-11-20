"""Biomass V2 - stress-damage gradient (analogue of x01 for dry biomass). Factorial C/S/B/SB quadruples from the
V3 working DB (endpoint DRY_BIOMASS), linked to the biomass PRIMARY_EXPANDED contrasts. The analysis functions
(decompose, bootstrap, null worlds, grouped CV of median / C1 / C2 / C3) are imported unchanged from x01.
Output: outputs/biomass_v2/stress_recovery/
"""
from __future__ import annotations
import json
import numpy as np, pandas as pd
import x01_stress_recovery as X1
from v2_common import OUT, now, write_json
from b03_build_biomass import connect3

BIO = OUT / "biomass_v2"
XB = BIO / "stress_recovery"
XB.mkdir(parents=True, exist_ok=True)
X1.X = XB                     # figure() writes here


def build(db_path=None, primary_csv=None):
    con = connect3(db_path)
    sxb = pd.read_sql("SELECT contrast_id AS sxb_id, study_id, experiment_key, tv_ids FROM an_contrasts "
                      "WHERE endpoint='DRY_BIOMASS' AND contrast_type='SxB'", con)
    tv = pd.read_sql("SELECT tv_id, role, mean, sd, n, arm_key FROM an_target_values WHERE endpoint='DRY_BIOMASS'",
                     con).set_index("tv_id")
    con.close()
    rows = []
    for r in sxb.itertuples():
        ids = json.loads(r.tv_ids)
        if len(ids) != 4 or not set(ids) <= set(tv.index):
            continue
        cell = {tv.loc[i, "role"]: i for i in ids}
        if set(cell) != {"C", "S", "B", "SB"}:
            continue
        o = {"sxb_id": r.sxb_id, "study_id": r.study_id, "experiment_key": r.experiment_key}
        for k, i in cell.items():
            o[f"tv_{k}"], o[f"m_{k}"], o[f"sd_{k}"], o[f"n_{k}"], o[f"arm_{k}"] = \
                i, tv.loc[i, "mean"], tv.loc[i, "sd"], tv.loc[i, "n"], tv.loc[i, "arm_key"]
        rows.append(o)
    q = pd.DataFrame(rows)
    q = q[(q[["m_C", "m_S", "m_B", "m_SB"]] > 0).all(axis=1)]
    p = pd.read_csv(primary_csv or BIO / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    p["tv_SB"] = p.tv_ids.map(lambda s: json.loads(s)[0])
    p["tv_S"] = p.tv_ids.map(lambda s: json.loads(s)[1])
    keep = ["contrast_id", "study_id", "lnRR", "stress_family", "biostimulant_class", "bio_tier", "organ_scope_v2",
            "tv_SB", "tv_S", "arm_key_t", "arm_key_c"]
    m1 = q.merge(p[keep], on=["study_id", "tv_SB", "tv_S"], how="inner")
    m = m1.assign(link="SAME_VALUES").drop_duplicates("contrast_id")
    m["y"] = np.log(m.m_SB / m.m_S)
    m["D"] = np.log(m.m_S / m.m_C)
    m["eB"] = np.log(m.m_B / m.m_C)
    m["ln_SB_C"] = np.log(m.m_SB / m.m_C)
    m["interaction"] = m.y - m.eB
    m["RL"] = np.where(m.D <= -0.05, m.y / -m.D, np.nan)
    m["RF"] = np.where((m.m_C - m.m_S) >= 0.05 * m.m_C, (m.m_SB - m.m_S) / (m.m_C - m.m_S), np.nan)
    m["group_id"] = m.study_id.astype(str)
    cvs, ns = [], []
    for k in ("C", "S", "B", "SB"):
        ok = m[f"sd_{k}"].notna() & m[f"n_{k}"].notna() & (m[f"n_{k}"] > 0)
        cvs += list((m.loc[ok, f"sd_{k}"] / m.loc[ok, f"m_{k}"]).to_numpy())
        ns += list(m.loc[ok, f"n_{k}"].to_numpy())
    cv0, n0 = float(np.median(cvs)), float(np.median(ns))
    for k in ("C", "S", "B", "SB"):
        se = m[f"sd_{k}"] / (np.sqrt(m[f"n_{k}"]) * m[f"m_{k}"])
        m[f"se_{k}"] = se.where(se.notna() & (se > 0), cv0 / np.sqrt(n0))
        m[f"se_{k}_imputed"] = se.isna() | ~(se > 0)
    assert (m.y - m.lnRR).abs().max() < 1e-9, "linked SB/S means differ from the biomass PRIMARY lnRR"
    return m.reset_index(drop=True), {"pooled_cv": cv0, "median_n": n0}


def fit_conditional(d):
    """Frozen-coefficient versions of C1-C3 fitted on all TRAIN quadruples (for pre-registration)."""
    w = 1 / d.group_id.map(d.group_id.value_counts()).to_numpy()
    c1 = X1.lad(d[["D"]], d.y, w)
    c3 = X1.lad(d[["D", "eB"]], d.y, w)
    return {"C1": {"intercept": float(c1.intercept_), "b_D": float(c1.coef_[0])},
            "C2": {"r": float(np.median(d.RL.dropna())), "fallback_if_D_above_-0.05": float(np.median(d.y))},
            "C3": {"intercept": float(c3.intercept_), "b_D": float(c3.coef_[0]), "c_eB": float(c3.coef_[1])},
            "median_train": float(np.median(d.y))}


def main():
    d, se_info = build()
    d.to_csv(XB / "quadruples.csv", index=False)
    p = pd.read_csv(BIO / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    cov = {"primary_contrasts": int(len(p)), "primary_studies": int(p.study_id.nunique()),
           "linked_contrasts": int(len(d)), "linked_studies": int(d.study_id.nunique()),
           "arm_se_imputed_share": float(d.filter(like="_imputed").mean().mean()), **se_info,
           "linked_by_stress": d.groupby("stress_family").study_id.nunique().to_dict()}
    desc = {c: {"median": float(d[c].median()), "median_of_study_means": float(d.groupby("group_id")[c].mean().median())}
            for c in ["y", "D", "eB", "RL"]}
    obs = {x: X1.decompose(d, x) for x in ("D", "eB")}
    ci = {x: X1.boot(d, x) for x in ("D", "eB")}
    null = pd.DataFrame([X1.decompose(X1.null_world(d), "D") for _ in range(500)])
    null_q = {k: [float(null[k].quantile(.025)), float(null[k].median()), float(null[k].quantile(.975))] for k in null}
    s = d.groupby("group_id")[["y", "D", "eB"]].mean()
    r2 = lambda a, b: float(np.corrcoef(a, b)[0, 1] ** 2)
    nr2 = [r2(*[X1.null_world(d).groupby("group_id")[["D", "y"]].mean()[c] for c in ("D", "y")]) for _ in range(500)]
    between = {"R2_studymean_y_on_D": r2(s.D, s.y), "R2_null_median": float(np.median(nr2)),
               "R2_null_q975": float(np.quantile(nr2, .975)), "n_studies": int(len(s))}
    cvo = X1.cv(d)
    cvn = pd.concat([X1.cv(X1.null_world(d)) for _ in range(30)], keys=range(30)).groupby(level=1)["mean"].agg(["mean", "std"])
    tab = cvo.rename(columns={"mean": "group_mae", "std": "sd_seeds"}).join(
        cvn.rename(columns={"mean": "null_world_group_mae", "std": "null_world_sd"}))
    base, nbase = tab.loc["median", "group_mae"], tab.loc["median", "null_world_group_mae"]
    tab["gain_vs_median"] = 1 - tab.group_mae / base
    tab["gain_expected_from_coupling_alone"] = 1 - tab.null_world_group_mae / nbase
    tab["gain_net_of_coupling"] = tab.gain_vs_median - tab.gain_expected_from_coupling_alone
    tab.to_csv(XB / "predictive_cv.csv")
    rep = {"generated_at": now(), "status": "BIOMASS_V2_TRAIN", "coverage": cov, "descriptives": desc,
           "slopes_observed": obs, "slopes_ci95_study_bootstrap": ci, "slope_D_null_artifact_q025_q50_q975": null_q,
           "between_study_variance": between, "conditional_coefficients_all_train": fit_conditional(d)}
    write_json(XB / "stress_recovery_report.json", rep)
    X1.figure(d, null_q, tab)
    return rep, tab


if __name__ == "__main__":
    rep, tab = main()
    print(json.dumps({k: rep[k] for k in ("coverage", "slopes_observed", "slopes_ci95_study_bootstrap",
                                          "slope_D_null_artifact_q025_q50_q975", "between_study_variance",
                                          "conditional_coefficients_all_train")}, indent=1))
    print(tab.round(4).to_string())
