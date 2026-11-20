"""Uncertainty types C and D: three-level random-effects meta-analysis (contrast within study) by REML.

y_ij = mu + u_i + w_ij + e_ij ;  u_i ~ N(0, tau_b^2) between studies, w_ij ~ N(0, tau_w^2) within studies,
e_ij ~ N(0, v_ij) known sampling variance. Sampling covariance between contrasts sharing a control is not known
(shared-control covariance needs the control SD and n, which are in vi only partially), so the within-study level
absorbs it and the CI is additionally reported with a cluster-robust (CR1, study) standard error.
This is an exploratory Python implementation; the confirmatory analysis remains R metafor::rma.mv + clubSandwich.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy import optimize, stats
from v2_common import OUT, now, write_json

DATA = OUT / "data"
META = OUT / "meta"
META.mkdir(parents=True, exist_ok=True)


def fit3(y, v, g, X=None):
    y, v, g = np.asarray(y, float), np.asarray(v, float), np.asarray(g)
    X = np.ones((len(y), 1)) if X is None else np.asarray(X, float)
    blocks = [np.where(g == k)[0] for k in pd.unique(g)]

    def parts(lt):
        tb, tw = np.exp(lt)
        XtVX = np.zeros((X.shape[1], X.shape[1]))
        XtVy = np.zeros(X.shape[1])
        logdet = 0.0
        Vinv = []
        for b in blocks:
            V = np.diag(v[b] + tw) + tb
            Vi = np.linalg.inv(V)
            Vinv.append(Vi)
            logdet += np.linalg.slogdet(V)[1]
            XtVX += X[b].T @ Vi @ X[b]
            XtVy += X[b].T @ Vi @ y[b]
        beta = np.linalg.solve(XtVX, XtVy)
        return beta, XtVX, Vinv, logdet

    def nll(lt):
        beta, XtVX, Vinv, logdet = parts(lt)
        q = sum(float((y[b] - X[b] @ beta) @ Vi @ (y[b] - X[b] @ beta)) for b, Vi in zip(blocks, Vinv))
        return 0.5 * (logdet + np.linalg.slogdet(XtVX)[1] + q)

    best = min((optimize.minimize(nll, x0, method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-8, "maxiter": 2000})
                for x0 in ([np.log(0.05), np.log(0.05)], [np.log(0.3), np.log(0.01)], [np.log(0.01), np.log(0.3)])),
               key=lambda r: r.fun)
    tb, tw = np.exp(best.x)
    beta, XtVX, Vinv, _ = parts(best.x)
    cov = np.linalg.inv(XtVX)
    # CR1 cluster-robust covariance
    meat = np.zeros_like(cov)
    for b, Vi in zip(blocks, Vinv):
        s = X[b].T @ Vi @ (y[b] - X[b] @ beta)
        meat += np.outer(s, s)
    K = len(blocks)
    cr = cov @ meat @ cov * K / (K - X.shape[1])
    return {"beta": beta, "se": np.sqrt(np.diag(cov)), "se_cr1": np.sqrt(np.diag(cr)), "tau2_between": float(tb),
            "tau2_within": float(tw), "k_studies": K, "n": len(y), "converged": bool(best.success)}


def summary(name, d):
    d = d[d.vi.notna() & (d.vi > 0)]
    if d.study_id.nunique() < 5:
        return {"set": name, "n": int(len(d)), "k_studies": int(d.study_id.nunique()), "status": "TOO_FEW_STUDIES"}
    f = fit3(d.lnRR, d.vi, d.study_id)
    K = f["k_studies"]
    t = stats.t.ppf(0.975, K - 1)
    mu, se, secr = float(f["beta"][0]), float(f["se"][0]), float(f["se_cr1"][0])
    tv = np.mean(d.vi)
    tot = f["tau2_between"] + f["tau2_within"]
    return {"set": name, "n": int(len(d)), "k_studies": K, "mu_lnRR": mu, "pct_effect": 100 * (np.exp(mu) - 1),
            "C_ci95_model": [mu - t * se, mu + t * se], "C_ci95_cluster_robust": [mu - t * secr, mu + t * secr],
            "tau2_between": f["tau2_between"], "tau2_within": f["tau2_within"],
            "I2_total_approx": tot / (tot + tv), "share_between_of_tau2": f["tau2_between"] / tot if tot > 0 else None,
            "D_pi95_new_study_mean": [mu - t * np.sqrt(se ** 2 + f["tau2_between"]), mu + t * np.sqrt(se ** 2 + f["tau2_between"])],
            "D_pi95_new_contrast_true_effect": [mu - t * np.sqrt(se ** 2 + tot), mu + t * np.sqrt(se ** 2 + tot)],
            "converged": f["converged"], "df_t": K - 1}


def main():
    sets = {"PRIMARY_EXPANDED": "PRIMARY_EXPANDED", "STRICT_SENSITIVITY": "STRICT_SENSITIVITY",
            "REPORTED_VARIANCE_ONLY": "SENSITIVITY_REPORTED_VARIANCE", "QUALITY_CORE": "QUALITY_CORE",
            "V1_EQUIVALENT": "V1_EQUIVALENT"}
    out = []
    for lab, f in sets.items():
        d = pd.read_csv(DATA / f"{f}.csv", low_memory=False)
        out.append(summary(lab, d))
    d = pd.read_csv(DATA / "PRIMARY_EXPANDED.csv", low_memory=False)
    sub = []
    for col in ["stress_family", "biostimulant_class", "yield_tier", "cultivation_system"]:
        for lv, g in d.groupby(col):
            s = summary(f"{col}={lv}", g)
            s["moderator"], s["level"] = col, lv
            sub.append(s)
    # unweighted study-level summary (all studies incl. those without variance): mean of study means
    sm = d.groupby("study_id").lnRR.mean()
    unw = {"k_studies": int(len(sm)), "mean_of_study_means": float(sm.mean()), "median_of_study_means": float(sm.median()),
           "sd_of_study_means": float(sm.std(ddof=1)),
           "studies_with_variance": int(d[d.vi.notna()].study_id.nunique())}
    write_json(META / "meta_summary.json", {"generated_at": now(), "overall": out, "unweighted_study_level": unw,
                                            "note": "exploratory 3-level REML (Python); confirmatory: R metafor rma.mv + clubSandwich CR2"})
    pd.DataFrame(sub).to_csv(META / "meta_subgroups.csv", index=False)
    return out, unw


if __name__ == "__main__":
    import json
    o, u = main()
    print(json.dumps(o, indent=1, default=float)); print(u)
