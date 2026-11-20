"""Build the biomass TEST inputs with EXACTLY the biomass V2 rules (b03_build_biomass.build, bx01.build).
  --validate-on-train   rebuild from a COPY of the V3 working DB into a scratch folder and require identical
                        PRIMARY_EXPANDED and quadruples (proves that redirection changes nothing)
  --test-sqlite <file>  TEST DATA_FREEZE SQLite; works on a private copy; TEST year window (exclude < 2024);
                        decisions naming TRAIN study_ids are NOT applied (study_rules=False)
Outputs (TEST): outputs/biomass_v2/test_inputs/TEST_PRIMARY.csv, TEST_quadruples.csv, test_build_report.json
"""
from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path
import pandas as pd
import b03_build_biomass as B
import bx01_biomass_stress as BX
from v2_common import V2, OUT, now, sha256, write_json

BIO = OUT / "biomass_v2"
SCRATCH = V2 / "work_test_build_biomass"
TI = BIO / "test_inputs"


def run(db_copy: Path, out_root: Path, test_mode: bool):
    data = out_root / "data"
    rep = B.build(db_path=db_copy, out_dir=data, year_rule="test" if test_mode else "train", write_db=False,
                  study_rules=not test_mode)
    q, se = BX.build(db_path=db_copy, primary_csv=data / "PRIMARY_EXPANDED.csv")
    return rep, q, se


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate-on-train", action="store_true")
    g.add_argument("--test-sqlite")
    a = ap.parse_args()
    SCRATCH.mkdir(exist_ok=True)
    work = SCRATCH / "db_copy.sqlite"
    try:
        if a.validate_on_train:
            shutil.copy2(B.DB3, work)
            out = SCRATCH / "train_validation"
            rep, q, _ = run(work, out, test_mode=False)
            n_p = pd.read_csv(out / "data" / "PRIMARY_EXPANDED.csv", low_memory=False).set_index("contrast_id")
            o_p = pd.read_csv(BIO / "data" / "PRIMARY_EXPANDED.csv", low_memory=False).set_index("contrast_id")
            o_q = pd.read_csv(BIO / "stress_recovery" / "quadruples.csv", low_memory=False).set_index("contrast_id")
            qq = q.set_index("contrast_id")
            res = {"validated_at": now(),
                   "primary_identical_file_hash": sha256(out / "data" / "PRIMARY_EXPANDED.csv") == sha256(BIO / "data" / "PRIMARY_EXPANDED.csv"),
                   "primary_same_ids": set(n_p.index) == set(o_p.index),
                   "primary_max_abs_lnRR_diff": float((n_p.lnRR - o_p.lnRR).abs().max()),
                   "quadruples_same_rows": set(qq.index) == set(o_q.index),
                   "quadruples_max_abs_D_diff": float((qq.D - o_q.D).abs().max()),
                   "rows": int(len(n_p)), "studies": int(n_p.study_id.nunique()), "quadruple_rows": int(len(qq))}
            res["PASS"] = bool(res["primary_same_ids"] and res["primary_max_abs_lnRR_diff"] < 1e-12
                               and res["quadruples_same_rows"] and res["quadruples_max_abs_D_diff"] < 1e-12)
            write_json(BIO / "test_inputs_validation.json", res)
            return res
        src = Path(a.test_sqlite)
        shutil.copy2(src, work)
        out = SCRATCH / "test_build"
        rep, q, se = run(work, out, test_mode=True)
        p = pd.read_csv(out / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
        yr = pd.to_numeric(p.year, errors="coerce")
        p = p[yr >= 2024]
        q = q[q.contrast_id.isin(set(p.contrast_id))]
        TI.mkdir(parents=True, exist_ok=True)
        p.to_csv(TI / "TEST_PRIMARY.csv", index=False)
        q.to_csv(TI / "TEST_quadruples.csv", index=False)
        shutil.copy2(out / "data" / "biomass_contrast_register.csv", TI / "TEST_contrast_register.csv")
        r = {"built_at": now(), "source_sqlite": str(src), "source_sha256": sha256(src), "rows": int(len(p)),
             "studies": int(p.study_id.nunique()), "quadruple_rows": int(len(q)),
             "quadruple_studies": int(q.study_id.nunique()), "status_counts": rep["status_counts"],
             "builder_sha256": sha256(Path(__file__)), "b03_sha256": sha256(V2 / "src" / "b03_build_biomass.py")}
        write_json(TI / "test_build_report.json", r)
        return {k: r[k] for k in ("rows", "studies", "quadruple_rows", "quadruple_studies")}
    finally:
        import gc
        gc.collect()
        shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
