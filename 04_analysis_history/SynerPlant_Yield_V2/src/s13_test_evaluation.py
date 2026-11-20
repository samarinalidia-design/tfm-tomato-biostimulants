"""ONE-TIME evaluation of the independent 2024-2026 TEST, exactly as pre-registered (PREREG_TEST_V2.json).

Usage (once, after the TEST dataset has been built with the frozen V2 rules):
    python s13_test_evaluation.py --test-contrasts <TEST_PRIMARY.csv> [--test-quadruples <TEST_quadruples.csv>]
Inputs
  TEST_PRIMARY.csv     columns: contrast_id, study_id, lnRR, year              (V2 PRIMARY_EXPANDED format)
  TEST_quadruples.csv  columns: contrast_id, study_id, m_C, m_S, m_B, m_SB, se_C, se_S, se_B, se_SB (optional)
Guards: refuses to run if any pre-registered hash changed, if TEST studies overlap TRAIN, if a year <= 2023, or if
the one-shot lock exists. '--dry-run-on-training' only checks the code path on training data: no lock, no verdict.
"""
from __future__ import annotations
import argparse, json, math, sys
import numpy as np, pandas as pd
from scipy import stats
from v2_common import V2, OUT, now, sha256, write_json
from s12_preregister import predict, REG
from s06_uncertainty import ALPHA

TST = OUT / "test_evaluation"
LOCK = TST / "TEST_EVALUATED.lock"
RNG = np.random.default_rng(20261118)


def gmae(y, p, g):
    return float(pd.Series(np.abs(np.asarray(y) - np.asarray(p))).groupby(np.asarray(g)).mean().mean())


def binom_ci(k, n):
    lo = stats.beta.ppf(0.025, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
    return [float(lo), float(hi)]


def check_hashes(reg):
    bad = []
    for rel, h in reg["hashes_sha256"].items():
        p = V2 / rel
        if not p.exists() or sha256(p) != h:
            bad.append(rel)
    return bad


def primary(reg, t):
    m = reg["primary_hypothesis"]["frozen_median_lnRR"]
    q1 = reg["primary_hypothesis"]["intervals_90"]["single_contrast_q"]
    q2 = reg["primary_hypothesis"]["intervals_90"]["simultaneous_q"]
    a = (t.lnRR - m).abs()
    cs = a.groupby(t.study_id).apply(lambda x: (x <= q1).mean())
    cm = a.groupby(t.study_id).apply(lambda x: bool((x <= q2).all()))
    K = int(cs.size)
    out = {"n_contrasts": int(len(t)), "n_studies": K, "group_mae": gmae(t.lnRR, m, t.study_id),
           "mae": float(a.mean()), "rmse": float(np.sqrt(((t.lnRR - m) ** 2).mean())), "bias": float((m - t.lnRR).mean()),
           "coverage_single": float(cs.mean()), "coverage_simultaneous": float(cm.mean()),
           "coverage_simultaneous_ci95": binom_ci(int(cm.sum()), K)}
    out["pass_coverage_single"] = out["coverage_single"] >= 0.85
    out["pass_coverage_simultaneous"] = out["coverage_simultaneous"] >= 0.85
    out["pass_accuracy_transport"] = out["group_mae"] <= 0.361 + 2 * 0.113
    return out


def slope_between(d):
    s = d.groupby("study_id")[["D", "y"]].mean()
    return float(np.polyfit(s.D, s.y, 1)[0]) if len(s) >= 3 else np.nan


def null_world(d):
    sm = d.groupby("study_id")[["y", "eB"]].mean()
    py = pd.Series(RNG.permutation(sm.y.to_numpy()), index=sm.index)
    pb = pd.Series(RNG.permutation(sm.eB.to_numpy()), index=sm.index)
    lC, lS = np.log(d.m_C), np.log(d.m_S)
    true = {"C": lC, "S": lS, "SB": lS + d.study_id.map(py), "B": lC + d.study_id.map(pb)}
    o = {k: v + RNG.normal(0, d[f"se_{k}"]) for k, v in true.items()}
    n = d.copy()
    n["y"], n["D"], n["eB"] = o["SB"] - o["S"], o["S"] - o["C"], o["B"] - o["C"]
    return n


def conditional(reg, q):
    coef = reg["conditional_models"]["coefficients_frozen_on_42_TRAIN_studies"]
    conf = reg["conditional_models"]["conformal_90"]
    d = q.copy()
    d["y"], d["D"], d["eB"] = np.log(d.m_SB / d.m_S), np.log(d.m_S / d.m_C), np.log(d.m_B / d.m_C)
    K = d.study_id.nunique()
    if K < reg["conditional_models"]["minimum_TEST_studies"]:
        return {"status": "INSUFFICIENT_TEST_STUDIES", "n_studies": int(K)}

    def gains(x):
        base = gmae(x.y, predict(coef, x, "median"), x.study_id)
        return {m: 1 - gmae(x.y, predict(coef, x, m), x.study_id) / base for m in ("C1", "C2", "C3")}, base

    g_obs, base = gains(d)
    nulls = [gains(null_world(d))[0] for _ in range(500)]
    sl = slope_between(d)
    sl_null = [slope_between(null_world(d)) for _ in range(500)]
    sids = d.study_id.unique()
    sl_boot = []
    for _ in range(2000):
        pick = RNG.choice(sids, len(sids))
        bd = pd.concat([d[d.study_id == s].assign(study_id=f"{s}#{i}") for i, s in enumerate(pick)])
        sl_boot.append(slope_between(bd))
    res = {"n_contrasts": int(len(d)), "n_studies": int(K), "median_group_mae": base}
    for m in ("C1", "C2", "C3"):
        p = predict(coef, d, m)
        a = (d.y - p).abs()
        nq = np.quantile([n[m] for n in nulls], 0.95)
        res[m] = {"group_mae": gmae(d.y, p, d.study_id), "gain_vs_median": g_obs[m], "null_gain_q95": float(nq),
                  "coverage_single": float(a.groupby(d.study_id).apply(lambda x: (x <= conf[m]["single_contrast_q"]).mean()).mean())}
    lo, hi = np.percentile(sl_boot, [2.5, 97.5])
    nlo, nhi = np.percentile(sl_null, [2.5, 97.5])
    res["between_slope"] = {"observed": sl, "ci95": [float(lo), float(hi)], "null_band95": [float(nlo), float(nhi)]}
    c1 = res["C1"]
    k1 = bool(c1["gain_vs_median"] >= 0.10)
    k2 = bool(c1["gain_vs_median"] > c1["null_gain_q95"])
    k3 = bool(hi < 0 and hi < nlo)
    res["criteria"] = {"1_gain": k1, "2_beyond_coupling": k2, "3_slope": k3,
                       "4_coverage": bool(c1["coverage_single"] >= 0.85)}
    res["verdict"] = "CONFIRMED" if (k1 and k2 and k3) else ("PARTIAL" if k3 else "NOT_CONFIRMED")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-contrasts")
    ap.add_argument("--test-quadruples")
    ap.add_argument("--dry-run-on-training", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()
    reg = json.loads(REG.read_text())
    TST.mkdir(parents=True, exist_ok=True)
    bad = check_hashes(reg)
    if a.verify_only:
        st = "INTACT" if not bad else f"BROKEN: {bad}"
        print(f"Pre-registration {reg['registered_at_utc']}: {len(reg['hashes_sha256'])} hashed files {st}; "
              f"TEST evaluated: {LOCK.exists()}")
        sys.exit(1 if bad else 0)
    if bad:
        sys.exit(f"REFUSED: pre-registered files changed: {bad}")
    if a.dry_run_on_training:
        t = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
        q = pd.read_csv(OUT / "exploratory" / "stress_recovery" / "quadruples.csv", low_memory=False)
        label = "DRY_RUN_ON_TRAINING_DATA (code check only - numbers are NOT a TEST result)"
    else:
        if LOCK.exists():
            sys.exit(f"REFUSED: the TEST was already evaluated ({LOCK.read_text()}).")
        if not a.test_contrasts:
            sys.exit("REFUSED: --test-contrasts is required")
        t = pd.read_csv(a.test_contrasts, low_memory=False)
        q = pd.read_csv(a.test_quadruples, low_memory=False) if a.test_quadruples else None
        train = set(pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", usecols=["study_id"]).study_id)
        overlap = set(t.study_id) & train
        if overlap:
            sys.exit(f"REFUSED: TEST studies overlap TRAIN_DEV: {sorted(overlap)[:10]}")
        if (pd.to_numeric(t.year, errors="coerce") <= 2023).any():
            sys.exit("REFUSED: TEST contains studies published <= 2023")
        label = "TEST_2024_2026_ONE_TIME"
        LOCK.write_text(f"{now()} sha256(test_contrasts)={sha256(__import__('pathlib').Path(a.test_contrasts))}")
    rep = {"label": label, "evaluated_at": now(), "registration": reg["registered_at_utc"],
           "primary": primary(reg, t), "conditional": conditional(reg, q) if q is not None else {"status": "NO_QUADRUPLES"}}
    name = "DRY_RUN_report.json" if a.dry_run_on_training else "TEST_REPORT.json"
    write_json(TST / name, rep)
    return rep


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
