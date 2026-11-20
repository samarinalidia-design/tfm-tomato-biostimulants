"""ONE-TIME evaluation of the biomass TEST exactly as pre-registered (PREREG_TEST_BIOMASS.json).
    python b13_test_biomass.py --test-contrasts <TEST_PRIMARY.csv> --test-quadruples <TEST_quadruples.csv>
    python b13_test_biomass.py --dry-run-on-training      code check on TRAIN (no lock, no verdict)
The conditional-model test re-uses the frozen s13 functions (null worlds, bootstrap, criteria) unchanged.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd
import s13_test_evaluation as S13
from v2_common import V2, OUT, now, sha256, write_json

BIO = OUT / "biomass_v2"
REG = BIO / "preregistration" / "PREREG_TEST_BIOMASS.json"
TST = BIO / "test_evaluation"
LOCK = TST / "TEST_EVALUATED.lock"


def primary(reg, t):
    h = reg["primary_hypothesis"]
    m, q1, q2 = h["frozen_point_lnRR"], h["intervals_90"]["single_contrast_q"], h["intervals_90"]["simultaneous_q"]
    a = (t.lnRR - m).abs()
    cs = a.groupby(t.study_id).apply(lambda x: (x <= q1).mean())
    cm = a.groupby(t.study_id).apply(lambda x: bool((x <= q2).all()))
    K = int(cs.size)
    o = {"n_contrasts": int(len(t)), "n_studies": K, "group_mae": S13.gmae(t.lnRR, m, t.study_id),
         "mae": float(a.mean()), "rmse": float(np.sqrt(((t.lnRR - m) ** 2).mean())), "bias": float((m - t.lnRR).mean()),
         "coverage_single": float(cs.mean()), "coverage_simultaneous": float(cm.mean()),
         "coverage_simultaneous_ci95": S13.binom_ci(int(cm.sum()), K)}
    o["pass_coverage_single"] = bool(o["coverage_single"] >= 0.85)
    o["pass_coverage_simultaneous"] = bool(o["coverage_simultaneous"] >= 0.85)
    o["pass_accuracy_transport"] = bool(o["group_mae"] <= h["accuracy_threshold"])
    return o


def conditional(reg, q):
    c = reg["conditional_models"]
    adapter = {"conditional_models": {"coefficients_frozen_on_42_TRAIN_studies": c["coefficients_frozen_on_TRAIN_quadruples"],
                                      "conformal_90": c["conformal_90"], "minimum_TEST_studies": c["minimum_TEST_studies"]}}
    res = S13.conditional(adapter, q)
    if "C3" in res:
        res["C3_secondary_pass"] = bool(res["C3"]["gain_vs_median"] >= 0.10 and
                                        res["C3"]["gain_vs_median"] > res["C3"]["null_gain_q95"])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-contrasts")
    ap.add_argument("--test-quadruples")
    ap.add_argument("--dry-run-on-training", action="store_true")
    a = ap.parse_args()
    reg = json.loads(REG.read_text(encoding="utf-8"))
    bad = [k for k, h in reg["hashes_sha256"].items() if not (V2 / k).exists() or sha256(V2 / k) != h]
    if bad:
        sys.exit(f"REFUSED: pre-registered files changed: {bad}")
    TST.mkdir(parents=True, exist_ok=True)
    if a.dry_run_on_training:
        t = pd.read_csv(BIO / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
        q = pd.read_csv(BIO / "stress_recovery" / "quadruples.csv", low_memory=False)
        label, name = "DRY_RUN_ON_TRAINING_DATA (code check only)", "DRY_RUN_report.json"
    else:
        if LOCK.exists():
            sys.exit(f"REFUSED: the biomass TEST was already evaluated ({LOCK.read_text()}).")
        t = pd.read_csv(a.test_contrasts, low_memory=False)
        q = pd.read_csv(a.test_quadruples, low_memory=False)
        train = set(pd.read_csv(BIO / "data" / "PRIMARY_EXPANDED.csv", usecols=["study_id"]).study_id.astype(str))
        if set(t.study_id.astype(str)) & train:
            sys.exit("REFUSED: TEST studies overlap TRAIN")
        if (pd.to_numeric(t.year, errors="coerce") <= 2023).any():
            sys.exit("REFUSED: TEST contains studies published <= 2023")
        LOCK.write_text(f"{now()} sha256(test_contrasts)={sha256(Path(a.test_contrasts))}")
        label, name = "BIOMASS_TEST_2024_2026_ONE_TIME", "TEST_REPORT.json"
    rep = {"label": label, "evaluated_at": now(), "registration": reg["registered_at_utc"],
           "primary": primary(reg, t), "conditional": conditional(reg, q)}
    write_json(TST / name, rep)
    return rep


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
