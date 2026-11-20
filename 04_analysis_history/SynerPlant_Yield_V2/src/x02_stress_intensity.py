"""EXPLORATORY (post-freeze, pre-TEST): a-priori stress intensity -> expected damage -> biostimulant effect.

Check 1: values coded from the verified arm stress descriptions (audit/stress_intensity_curated.csv).
Check 2: the same number is found in the original PDF text (automatic; page recorded) -> AUTO_VERIFIED_V2.
Conversions are done here, never by hand:
  NaCl mM -> EC 0.1 dS/m per mM;  NaCl % w/v -> x 17.11 dS/m;  NaCl g/L -> x 1.711;  TDS ppm -> /640 (USDA Hb 60)
  saline irrigation water applied to soil: ECe = 1.5 x ECw (FAO-29, leaching fraction 15-20 %); measured ECe,
  soil EC, nutrient solutions and measured solution EC are used as printed (sensitivity: no 1.5 factor).
External damage models (NOT fitted to these data):
  salinity  Maas-Hoffman tomato: Yr = 1 - 0.099 * max(ECe - 2.5, 0)
  drought   FAO-33 (ET-based supply only): Yr = 1 - 1.05 * (1 - supply/reference)
  expected damage D_exp = ln(max(Yr, 0.05)); combined stresses multiply relative yields.
Soil-water (% FC) regimes have no external model: kept as an intensity (relative soil water) only.
"""
from __future__ import annotations
import json, re
import numpy as np, pandas as pd
from scipy import stats
from sklearn.linear_model import QuantileRegressor
from v2_common import connect, OUT, AUDIT, resolve_source, pdf_text, now, write_json
from s04_train import outer_splits, SEEDS

X = OUT / "exploratory" / "stress_intensity"
X.mkdir(parents=True, exist_ok=True)
EC_FACTOR = {"EC_DSM": 1.0, "NACL_MM": 0.1, "NACL_PCT_WV": 17.11, "NACL_GL": 1.711, "TDS_PPM": 1 / 640}


def pdf_check(cur: pd.DataFrame) -> pd.DataFrame:
    con = connect(readonly=True)
    files = pd.read_sql("SELECT study_id, file_name, role FROM files", con)
    cache = {}
    out = []
    for r in cur.itertuples():
        if r.study_id not in cache:
            pages = []
            for f in files[files.study_id == r.study_id].itertuples():
                p = resolve_source(f.file_name)
                if p and p.suffix.lower() == ".pdf":
                    try:
                        pages += [(f.role, i + 1, re.sub(r"\s+", " ", t.replace("−", "-"))) for i, t in enumerate(pdf_text(p))]
                    except Exception:
                        pass
            cache[r.study_id] = pages
        hit = None
        for tok in str(r.pdf_tokens).split("|"):
            tok = tok.strip()
            if not tok:
                continue
            if re.search(r"\d", tok):
                num = re.escape(re.match(r"[\d.]+", tok).group(0)) if re.match(r"[\d.]+", tok) else None
                rest = tok[len(re.match(r"[\d.]+", tok).group(0)):].strip() if num else tok
                pat = (rf"(?<![\d.]){num}(?![\d])\s*{re.escape(rest)}" if num else re.escape(tok))
            else:
                pat = re.escape(tok)
            for role, pg, t in cache[r.study_id]:
                if re.search(pat, t, re.I):
                    hit = f"{role} p{pg}"
                    break
            if hit:
                break
        out.append(hit)
    cur = cur.copy()
    cur["pdf_locator"] = out
    cur["verification"] = np.where(cur.pdf_locator.notna(), "AUTO_VERIFIED_V2", "CODED_FROM_VERIFIED_ARM_ONLY")
    return cur


def convert(cur: pd.DataFrame) -> pd.DataFrame:
    c = cur.copy()
    c["value"] = pd.to_numeric(c.value, errors="coerce")
    c["reference_value"] = pd.to_numeric(c.reference_value, errors="coerce")
    sal = c.component == "SALINITY"
    ecx = c.value * c.metric.map(EC_FACTOR)
    c["ec_exposure_dSm"] = np.where(sal, ecx, np.nan)
    f15 = np.where(c.basis == "IRRIGATION_WATER_SOIL", 1.5, 1.0)
    c["ece_equiv_dSm"] = c.ec_exposure_dSm * f15
    yr_sal = 1 - 0.099 * np.clip(c.ece_equiv_dSm - 2.5, 0, None)
    yr_sal_nof = 1 - 0.099 * np.clip(c.ec_exposure_dSm - 2.5, 0, None)
    dr = c.component == "DROUGHT"
    rel = np.clip(c.value / c.reference_value, 0, 1)
    c["water_supply_rel_ET"] = np.where(dr & (c.basis == "ET_SUPPLY"), rel, np.nan)
    c["soil_water_rel_FC"] = np.where(dr & (c.basis == "SOIL_WATER"), rel, np.nan)
    yr_dr = 1 - 1.05 * (1 - c.water_supply_rel_ET)
    c["Yr_exp"] = np.where(sal, yr_sal, np.where(dr, yr_dr, np.nan))
    c["Yr_exp_no_ece_factor"] = np.where(sal, yr_sal_nof, np.where(dr, yr_dr, np.nan))
    return c


def per_stress_code(c: pd.DataFrame) -> pd.DataFrame:
    """One row per (study, stress code); combined stresses multiply relative yields."""
    def agg(g):
        o = {"ece_equiv_dSm": g.ece_equiv_dSm.max(), "ec_exposure_dSm": g.ec_exposure_dSm.max(),
             "water_supply_rel_ET": g.water_supply_rel_ET.min(), "soil_water_rel_FC": g.soil_water_rel_FC.min(),
             "verification": "AUTO_VERIFIED_V2" if (g.verification == "AUTO_VERIFIED_V2").all() else "PARTIAL"}
        for k in ("Yr_exp", "Yr_exp_no_ece_factor"):
            v = g[k].dropna()
            o[k] = float(np.prod(v)) if len(v) and len(v) == g.component.isin(["SALINITY", "DROUGHT"]).sum() else np.nan
        return pd.Series(o)
    s = c.groupby(["study_id", "stress_code"]).apply(agg, include_groups=False).reset_index()
    s["D_exp"] = np.log(np.clip(s.Yr_exp.astype(float), 0.05, 1))
    s["D_exp_no_ece_factor"] = np.log(np.clip(s.Yr_exp_no_ece_factor.astype(float), 0.05, 1))
    return s


def gmae(y, p, g):
    return float(pd.Series(np.abs(np.asarray(y) - np.asarray(p))).groupby(np.asarray(g)).mean().mean())


def lad(Xtr, y, w):
    return QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs").fit(Xtr, y, sample_weight=w * len(w) / w.sum())


def design(d, kind):
    if kind == "external_damage":
        x = pd.DataFrame({"D_exp": d.D_exp.fillna(0), "D_exp_missing": d.D_exp.isna().astype(float)})
    elif kind == "intensity":
        sal = (d.stress_family == "SALINITY") | d.ece_equiv_dSm.notna()
        x = pd.DataFrame({
            "ece_over_threshold": np.clip(d.ece_equiv_dSm.fillna(0) - 2.5, 0, None),
            "et_deficit": (1 - d.water_supply_rel_ET).fillna(0),
            "soil_water_deficit": (1 - d.soil_water_rel_FC).fillna(0),
            "intensity_missing": (d.ece_equiv_dSm.isna() & d.water_supply_rel_ET.isna() & d.soil_water_rel_FC.isna()).astype(float)})
    return x


def cv(d):
    rows = []
    preds = []
    for seed in SEEDS:
        for f, te_g in enumerate(outer_splits(d.group_id, seed)):
            m = d.group_id.isin(te_g).to_numpy()
            tr, te = d[~m], d[m]
            w = 1 / tr.group_id.map(tr.group_id.value_counts()).to_numpy()
            P = {"median": np.full(len(te), np.median(tr.lnRR))}
            for k in ("external_damage", "intensity"):
                P[k] = lad(design(tr, k), tr.lnRR, w).predict(design(te, k))
            for k, v in P.items():
                rows.append({"seed": seed, "fold": f, "model": k, "group_mae": gmae(te.lnRR, v, te.group_id)})
                preds.append(pd.DataFrame({"contrast_id": te.contrast_id, "group_id": te.group_id, "y": te.lnRR,
                                           "pred": v, "model": k, "seed": seed}))
    r = pd.DataFrame(rows)
    P = pd.concat(preds)
    tab = r.groupby(["model", "seed"]).group_mae.mean().groupby("model").agg(["mean", "std"])
    # paired study-level bootstrap vs median
    e = P.assign(ae=(P.y - P.pred).abs()).groupby(["model", "group_id"]).ae.mean().unstack(0)
    rng = np.random.default_rng(1)
    for k in tab.index:
        diff = (e[k] - e["median"]).to_numpy()
        bs = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(4000)]
        tab.loc[k, "diff_vs_median"] = diff.mean()
        tab.loc[k, "ci_lo"], tab.loc[k, "ci_hi"] = np.percentile(bs, [2.5, 97.5])
    tab["gain_vs_median"] = 1 - tab["mean"] / tab.loc["median", "mean"]
    return tab


def within_concordance(q):
    """Within-study ranking check: does the more severe nominal level show more damage / a larger effect?"""
    import itertools
    q = q.copy()
    q["sev"] = np.where(q.ece_equiv_dSm.notna(), q.ece_equiv_dSm,
                        np.where(q.water_supply_rel_ET.notna(), 1 - q.water_supply_rel_ET,
                                 np.where(q.soil_water_rel_FC.notna(), 1 - q.soil_water_rel_FC, np.nan)))
    g = q.dropna(subset=["sev"]).groupby(["study_id", "stress_code"]).agg(sev=("sev", "first"), D=("D", "mean"),
                                                                          y=("y", "mean")).reset_index()
    nD = nY = tot = st = 0
    for _, h in g.groupby("study_id"):
        if h.sev.nunique() < 2:
            continue
        st += 1
        for a, b in itertools.combinations(h.itertuples(), 2):
            if a.sev == b.sev:
                continue
            hi, lo = (a, b) if a.sev > b.sev else (b, a)
            nD += hi.D < lo.D
            nY += hi.y > lo.y
            tot += 1
    return {"studies_with_2plus_levels": st, "pairs": tot,
            "share_more_severe_level_has_larger_damage": nD / tot if tot else None,
            "share_more_severe_level_has_larger_biostimulant_effect": nY / tot if tot else None}


def main():
    cur = pd.read_csv(AUDIT / "stress_intensity_curated.csv", dtype=str)
    cur = convert(pdf_check(cur))
    cur.to_csv(X / "stress_intensity_coded_verified.csv", index=False)
    sc = per_stress_code(cur)
    sc.to_csv(X / "stress_intensity_by_stress_code.csv", index=False)
    p = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    p = p.drop(columns=[c for c in ("ece_equiv_dSm", "D_exp") if c in p]).merge(sc, on=["study_id", "stress_code"], how="left")
    p["group_id"] = p.study_id.astype(str)
    p.to_csv(X / "PRIMARY_EXPANDED_with_intensity.csv", index=False)
    # coverage (sal/drought studies)
    fam = p.stress_family.isin(["SALINITY", "DROUGHT"])
    has_new = p.ece_equiv_dSm.notna() | p.water_supply_rel_ET.notna() | p.soil_water_rel_FC.notna()
    has_old = p.salinity_dSm_equiv.notna() | p.drought_supply_pct.notna()
    cov = {}
    for f in ["SALINITY", "DROUGHT"]:
        q = p[p.stress_family == f]
        cov[f] = {"studies": int(q.study_id.nunique()),
                  "studies_with_intensity_V2_frozen": int(q[has_old[q.index]].study_id.nunique()),
                  "studies_with_intensity_now": int(q[has_new[q.index]].study_id.nunique()),
                  "studies_with_external_damage_model": int(q[q.D_exp.notna()].study_id.nunique())}
    cov["all_primary_studies_with_D_exp"] = int(p[p.D_exp.notna()].study_id.nunique())
    cov["coded_rows"] = int(len(cur))
    cov["verification_counts"] = cur.verification.value_counts().to_dict()
    cov["not_comparable_rows"] = int((cur.basis == "NOT_COMPARABLE").sum())
    missing = p[fam & ~has_new].drop_duplicates(["study_id", "stress_code"])[["study_id", "stress_code"]]
    missing.to_csv(X / "salinity_drought_arms_without_intensity.csv", index=False)

    # validation against the OBSERVED damage in factorial studies (x01 quadruples)
    q = pd.read_csv(OUT / "exploratory" / "stress_recovery" / "quadruples.csv", low_memory=False)
    q = q.merge(p[["contrast_id", "D_exp", "D_exp_no_ece_factor", "ece_equiv_dSm", "water_supply_rel_ET",
                   "soil_water_rel_FC", "stress_code"]], on="contrast_id", how="left")
    val = {}
    for lab, col, sub in [("D_exp_vs_observed_D", "D_exp", q.D_exp.notna()),
                          ("D_exp_no_1.5_factor_vs_observed_D", "D_exp_no_ece_factor", q.D_exp_no_ece_factor.notna()),
                          ("ECe_vs_observed_D (salinity)", "ece_equiv_dSm", q.ece_equiv_dSm.notna()),
                          ("ET_supply_vs_observed_D (drought)", "water_supply_rel_ET", q.water_supply_rel_ET.notna()),
                          ("soil_water_FC_vs_observed_D (drought)", "soil_water_rel_FC", q.soil_water_rel_FC.notna())]:
        g = q[sub].groupby("group_id")[[col, "D", "y"]].mean()
        if len(g) >= 4:
            rho, pv = stats.spearmanr(g[col], g.D)
            rho_y, pv_y = stats.spearmanr(g[col], g.y)
            val[lab] = {"studies": int(len(g)), "spearman_with_observed_D": float(rho), "p": float(pv),
                        "spearman_with_effect_lnRR": float(rho_y), "p_effect": float(pv_y)}
            if col.startswith("D_exp"):
                val[lab]["median_abs_error_D_exp_minus_D"] = float((g[col] - g.D).abs().median())
    # predictive CV (a-priori features only; no coupling: nothing is computed from the arms)
    res = {}
    res["PRIMARY_all_69"] = cv(p)
    sub = p[p.D_exp.notna() | p.ece_equiv_dSm.notna() | p.water_supply_rel_ET.notna() | p.soil_water_rel_FC.notna()].copy()
    res["subset_with_intensity"] = cv(sub)
    for k, t in res.items():
        t.to_csv(X / f"predictive_cv_{k}.csv")
    rep = {"generated_at": now(), "status": "EXPLORATORY_POST_FREEZE_PRE_TEST", "coverage": cov, "validation": val,
           "within_study_concordance": within_concordance(q),
           "cv": {k: t.round(4).reset_index().to_dict("records") for k, t in res.items()},
           "subset_size": {"rows": int(len(sub)), "studies": int(sub.study_id.nunique())}}
    write_json(X / "stress_intensity_report.json", rep)
    return rep


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=1, default=str))
