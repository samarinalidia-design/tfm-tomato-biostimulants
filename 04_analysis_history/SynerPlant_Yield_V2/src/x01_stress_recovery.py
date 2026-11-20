"""EXPLORATORY (post-freeze, pre-TEST): does stress damage explain between-study heterogeneity of the
biostimulant yield effect?  Read-only w.r.t. the frozen V2 release.

Factorial experiments give four arms C (control), S (stress), B (biostimulant), SB (stress + biostimulant):
  target      y   = ln(SB/S)          (the V2 estimand)
  damage      D   = ln(S/C)  (<0 = yield loss caused by the stress)
  unstressed  e_B = ln(B/C)           (effect of the biostimulant without stress; shares NO arm with y)
  recovery    RL  = ln(SB/S) / -D = 1 - ln(SB/C)/ln(S/C)   (share of the log-loss recovered; |D| >= 0.05 only)
  recovery%   RF  = (SB-S)/(C-S)      (share of the absolute loss recovered; C-S >= 5% of C only)

COUPLING TRAP: y and D share ln S.  Sampling error in S lowers D and raises y at the same time, creating a negative
slope of y on D even when the true effect does not depend on damage.  The size of this artefact is estimated with a
null simulation that uses each arm's own sampling error (reported SD/n, or the pooled CV where missing).
"""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from sklearn.linear_model import QuantileRegressor
from v2_common import connect, OUT, now, write_json
from s04_train import outer_splits, SEEDS

X = OUT / "exploratory" / "stress_recovery"
X.mkdir(parents=True, exist_ok=True)
RNG = np.random.default_rng(20261118)


# ------------------------------------------------------------------ 1. quadruples
def build():
    con = connect(readonly=True)
    sxb = pd.read_sql("SELECT contrast_id AS sxb_id, study_id, experiment_key, tv_ids FROM an_contrasts "
                      "WHERE endpoint='FRUIT_YIELD' AND contrast_type='SxB'", con)
    tv = pd.read_sql("SELECT tv_id, role, mean, sd, n, arm_key FROM an_target_values WHERE endpoint='FRUIT_YIELD'",
                     con).set_index("tv_id")
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
    # link to the V2 PRIMARY contrast with the same SB and S target values (fallback: same arm pair)
    p = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    p["tv_SB"] = p.tv_ids.map(lambda s: json.loads(s)[0])
    p["tv_S"] = p.tv_ids.map(lambda s: json.loads(s)[1])
    keep = ["contrast_id", "study_id", "lnRR", "stress_family", "biostimulant_class", "yield_tier", "tv_SB", "tv_S",
            "arm_key_t", "arm_key_c"]
    m1 = q.merge(p[keep], on=["study_id", "tv_SB", "tv_S"], how="inner")
    rest = q[~q.sxb_id.isin(m1.sxb_id)]
    m2 = rest.merge(p[keep].drop(columns=["tv_SB", "tv_S"]), left_on=["study_id", "arm_SB", "arm_S"],
                    right_on=["study_id", "arm_key_t", "arm_key_c"], how="inner")
    m = pd.concat([m1.assign(link="SAME_VALUES"), m2.assign(link="SAME_ARM_PAIR")], ignore_index=True)
    m = m.drop_duplicates("contrast_id")          # one C/B set per PRIMARY contrast (first = exact values)
    m["y"] = np.log(m.m_SB / m.m_S)
    m["D"] = np.log(m.m_S / m.m_C)
    m["eB"] = np.log(m.m_B / m.m_C)
    m["ln_SB_C"] = np.log(m.m_SB / m.m_C)
    m["interaction"] = m.y - m.eB
    m["RL"] = np.where(m.D <= -0.05, m.y / -m.D, np.nan)
    m["RF"] = np.where((m.m_C - m.m_S) >= 0.05 * m.m_C, (m.m_SB - m.m_S) / (m.m_C - m.m_S), np.nan)
    m["group_id"] = m.study_id.astype(str)
    # per-arm sampling SE on the log scale; missing -> pooled CV / sqrt(median n)
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
    assert abs((m.y - m.lnRR).abs().max()) < 1e-9, "linked SB/S means differ from the PRIMARY lnRR"
    return m, {"pooled_cv": cv0, "median_n": n0}


# ------------------------------------------------------------------ 2. slope with study bootstrap
def wslope(x, y, g):
    """group-balanced OLS slope (each study total weight 1)."""
    w = 1 / pd.Series(g).map(pd.Series(g).value_counts()).to_numpy()
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    return float(np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2))


def decompose(d, xcol, ycol="y"):
    s = d.groupby("group_id")[[xcol, ycol]].mean()
    within = d[[xcol, ycol]] - d.groupby("group_id")[[xcol, ycol]].transform("mean")
    has_var = d.groupby("group_id")[xcol].transform("std").fillna(0) > 1e-9
    return {"pooled": wslope(d[xcol].to_numpy(), d[ycol].to_numpy(), d.group_id.to_numpy()),
            "between_studies": float(np.polyfit(s[xcol], s[ycol], 1)[0]),
            "within_studies": float(np.polyfit(within[xcol][has_var], within[ycol][has_var], 1)[0])
            if has_var.sum() > 10 else np.nan}


def boot(d, xcol, B=2000):
    gs = d.group_id.unique()
    idx = {g: np.where(d.group_id.to_numpy() == g)[0] for g in gs}
    out = []
    for _ in range(B):
        pick = RNG.choice(gs, len(gs), replace=True)
        rows = np.concatenate([idx[g] for g in pick])
        dd = d.iloc[rows].copy()
        dd["group_id"] = np.repeat(np.arange(len(pick)), [len(idx[g]) for g in pick]).astype(str)
        out.append(decompose(dd, xcol))
    b = pd.DataFrame(out)
    return {k: [float(b[k].quantile(.025)), float(b[k].quantile(.975))] for k in b}


def null_world(d):
    """World in which the true effect does NOT depend on damage or on the unstressed effect.
    True study effects of y and of eB are the observed study means PERMUTED across studies (independently), so
    their real between-study distribution is kept but every link to D (and between y and eB) is broken.
    True lnC, lnS are the observed values; true lnSB = lnS + mu_y*, true lnB = lnC + mu_b*.
    Every arm then gets fresh sampling error with its own log-SE, so the only remaining y-D association is the
    shared-S coupling. (Observed arms already contain noise -> artefact slightly over-stated, conservative.)"""
    sm = d.groupby("group_id")[["y", "eB"]].mean()
    perm_y = pd.Series(RNG.permutation(sm.y.to_numpy()), index=sm.index)
    perm_b = pd.Series(RNG.permutation(sm.eB.to_numpy()), index=sm.index)
    mu_y = d.group_id.map(perm_y)
    mu_b = d.group_id.map(perm_b)
    lC, lS = np.log(d.m_C), np.log(d.m_S)
    true = {"C": lC, "S": lS, "SB": lS + mu_y, "B": lC + mu_b}
    obs = {k: v + RNG.normal(0, d[f"se_{k}"]) for k, v in true.items()}
    nd = d.copy()
    nd["y"], nd["D"], nd["eB"] = obs["SB"] - obs["S"], obs["S"] - obs["C"], obs["B"] - obs["C"]
    return nd


# ------------------------------------------------------------------ 3. grouped CV predictors
def lad(x, y, w):
    m = QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs")
    return m.fit(x, y, sample_weight=w * len(w) / w.sum())


def cv(d, sims=0):
    def gmae(y, p, g):
        return float(pd.Series(np.abs(y - p)).groupby(g).mean().mean())

    res = []
    for seed in SEEDS:
        for f, te_g in enumerate(outer_splits(d.group_id, seed)):
            m = d.group_id.isin(te_g).to_numpy()
            tr, te = d[~m], d[m]
            w = 1 / tr.group_id.map(tr.group_id.value_counts()).to_numpy()
            pred = {"median": np.full(len(te), np.median(tr.y))}
            pred["damage_linear"] = lad(tr[["D"]], tr.y, w).predict(te[["D"]])
            r = tr.RL.dropna()
            rmed = float(np.median(r)) if len(r) else 0.0
            pred["recovery_share"] = np.where(te.D <= -0.05, rmed * -te.D, np.median(tr.y))
            pred["unstressed_effect"] = lad(tr[["eB"]], tr.y, w).predict(te[["eB"]])
            pred["damage+unstressed"] = lad(tr[["D", "eB"]], tr.y, w).predict(te[["D", "eB"]])
            for k, v in pred.items():
                res.append({"seed": seed, "fold": f, "model": k, "group_mae": gmae(te.y.to_numpy(), v, te.group_id.to_numpy())})
    r = pd.DataFrame(res)
    return r.groupby(["model", "seed"]).group_mae.mean().groupby("model").agg(["mean", "std"])


def main():
    d, se_info = build()
    d.to_csv(X / "quadruples.csv", index=False)
    p = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    cov = {"primary_contrasts": int(len(p)), "primary_studies": int(p.study_id.nunique()),
           "linked_contrasts": int(len(d)), "linked_studies": int(d.study_id.nunique()),
           "link_type": d.link.value_counts().to_dict(), "arm_se_imputed_share": float(d.filter(like="_imputed").mean().mean()),
           **se_info,
           "linked_by_stress": d.groupby("stress_family").study_id.nunique().to_dict()}
    desc = {}
    for c in ["y", "D", "eB", "ln_SB_C", "interaction", "RL", "RF"]:
        s = d[c].dropna()
        sm = d.groupby("group_id")[c].mean().dropna()
        desc[c] = {"n": int(len(s)), "median": float(s.median()), "q25": float(s.quantile(.25)), "q75": float(s.quantile(.75)),
                   "median_of_study_means": float(sm.median()), "share_positive": float((s > 0).mean())}
    # slopes: observed, CI, null artefact
    obs = {x: decompose(d, x) for x in ("D", "eB")}
    ci = {x: boot(d, x) for x in ("D", "eB")}
    null = pd.DataFrame([decompose(null_world(d), "D") for _ in range(500)])
    null_q = {k: [float(null[k].quantile(.025)), float(null[k].median()), float(null[k].quantile(.975))] for k in null}
    # share of between-study variance of y explained by study-mean damage (observed vs null)
    s = d.groupby("group_id")[["y", "D", "eB"]].mean()
    r2 = lambda a, b: float(np.corrcoef(a, b)[0, 1] ** 2)
    nulls_r2 = []
    for _ in range(500):
        sn = null_world(d).groupby("group_id")[["y", "D"]].mean()
        nulls_r2.append(r2(sn.D, sn.y))
    between = {"R2_studymean_y_on_D": r2(s.D, s.y), "R2_null_median": float(np.median(nulls_r2)),
               "R2_null_q975": float(np.quantile(nulls_r2, .975)), "R2_studymean_y_on_eB": r2(s.eB, s.y),
               "var_between_y": float(s.y.var()), "n_studies": int(len(s))}
    # predictive CV (observed) and the coupling optimism (same CV on null worlds)
    cvo = cv(d)
    cvn = pd.concat([cv(null_world(d)) for _ in range(30)], keys=range(30))
    cvn = cvn.groupby(level=1)["mean"].agg(["mean", "std"])
    tab = cvo.rename(columns={"mean": "group_mae", "std": "sd_seeds"}).join(
        cvn.rename(columns={"mean": "null_world_group_mae", "std": "null_world_sd"}))
    base, nbase = tab.loc["median", "group_mae"], tab.loc["median", "null_world_group_mae"]
    tab["gain_vs_median"] = 1 - tab.group_mae / base
    tab["gain_expected_from_coupling_alone"] = 1 - tab.null_world_group_mae / nbase
    tab["gain_net_of_coupling"] = tab.gain_vs_median - tab.gain_expected_from_coupling_alone
    tab.to_csv(X / "predictive_cv.csv")
    by_stress = d.groupby("stress_family").agg(studies=("group_id", "nunique"), contrasts=("y", "size"),
                                               median_y=("y", "median"), median_D=("D", "median"),
                                               median_RL=("RL", "median"), median_eB=("eB", "median")).round(3)
    by_stress.to_csv(X / "by_stress_family.csv")
    rep = {"generated_at": now(), "status": "EXPLORATORY_POST_FREEZE_PRE_TEST", "coverage": cov, "descriptives": desc,
           "slopes_observed": obs, "slopes_ci95_study_bootstrap": ci, "slope_D_null_artifact_q025_q50_q975": null_q,
           "between_study_variance": between}
    write_json(X / "stress_recovery_report.json", rep)
    figure(d, null_q, tab)
    return rep, tab, by_stress


def figure(d, null_q, tab):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s = d.groupby("group_id")[["y", "D", "eB"]].mean()
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.8))
    ax[0].scatter(d.D, d.y, s=7, c="#8d99ae", alpha=.6, lw=0)
    ax[0].scatter(s.D, s.y, s=22, c="#2a6f97", edgecolor="w", lw=.4)
    xs = np.linspace(d.D.min(), d.D.max(), 10)
    b = decompose(d, "D")["between_studies"]
    ax[0].plot(xs, s.y.mean() + b * (xs - s.D.mean()), c="#2a6f97", lw=1, label=f"between-study slope {b:.2f}")
    ax[0].plot(xs, s.y.mean() + null_q["between_studies"][1] * (xs - s.D.mean()), c="#c0392b", ls="--", lw=1,
               label=f"coupling artefact {null_q['between_studies'][1]:.2f}")
    ax[0].set_xlabel("stress damage D = ln(S/C)")
    ax[0].set_ylabel("ln(SB/S)")
    ax[0].legend(fontsize=7)
    ax[1].scatter(d.eB, d.y, s=7, c="#8d99ae", alpha=.6, lw=0)
    ax[1].scatter(s.eB, s.y, s=22, c="#2e8b57", edgecolor="w", lw=.4)
    ax[1].axline((0, 0), slope=1, c="k", lw=.6, ls=":")
    ax[1].set_xlabel("unstressed effect ln(B/C)")
    ax[1].set_ylabel("ln(SB/S)")
    t = tab.sort_values("group_mae")
    ax[2].barh(t.index, t.group_mae, xerr=t.sd_seeds, color="#2a6f97")
    ax[2].barh(t.index, t.null_world_group_mae, color="none", edgecolor="#c0392b", ls="--")
    ax[2].set_xlabel("group-MAE, grouped 5x5 CV (red dashed = null world)", fontsize=8)
    fig.text(0.01, 0.01, "Exploratory. Grey = contrasts, coloured = study means. Error bars (right) = Type A: SD over 5 CV "
             "seeds. Red dashed = same CV in simulated worlds where the effect does NOT depend on damage "
             "(coupling artefact only).", fontsize=7)
    fig.tight_layout(rect=(0, .06, 1, 1))
    for e in ("png", "svg", "pdf"):
        fig.savefig(X / f"X1_stress_recovery.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


if __name__ == "__main__":
    rep, tab, bs = main()
    print(json.dumps({k: rep[k] for k in ("coverage", "descriptives", "slopes_observed", "slopes_ci95_study_bootstrap",
                                          "slope_D_null_artifact_q025_q50_q975", "between_study_variance")}, indent=1))
    pd.set_option("display.width", 220)
    print(tab.round(4).to_string())
    print(bs.to_string())
