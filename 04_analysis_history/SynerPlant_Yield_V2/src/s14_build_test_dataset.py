"""Build the TEST analysis files with EXACTLY the frozen V2 rules (s03_build_dataset.py, x01_stress_recovery.py),
without modifying those hashed modules: they are imported and only their input/output locations are redirected.

  --validate-on-train      rebuild from a COPY of the V2 working DB and require byte-identical agreement with the
                           frozen PRIMARY_EXPANDED / quadruples (proves the redirection changes nothing)
  --test-sqlite <file>     TEST DATA_FREEZE SQLite (same schema as the TRAIN freeze); works on a private copy
Outputs (TEST mode): outputs/test_inputs/TEST_PRIMARY.csv, TEST_quadruples.csv, test_build_report.json
TEST-specific rule (pre-registered in the addendum): the TRAIN year rule (exclude > 2023) is replaced by the TEST
window (exclude < 2024). Study-specific TRAIN decisions (value corrections, relative-unit inclusions, study
exclusions) do not apply to TEST studies; generic rules (tiers, one contrast per arm pair, synthetic-PGR class,
box-centre / dry / non-marketable routing) do.
"""
from __future__ import annotations
import argparse, json, shutil, sqlite3, sys, types
from pathlib import Path
import numpy as np, pandas as pd
from v2_common import V2, OUT, DB, now, sha256, write_json

SCRATCH = V2 / "work_test_build"
TI = OUT / "test_inputs"


_OPEN = []


def _connect_factory(path: Path):
    def connect(readonly: bool = False):
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        _OPEN.append(con)
        return con
    return connect


def _cleanup():
    for c in _OPEN:
        try:
            c.close()
        except Exception:
            pass
    _OPEN.clear()
    import gc
    gc.collect()
    shutil.rmtree(SCRATCH, ignore_errors=False)


class _PdTestYear(types.ModuleType):
    """pandas proxy for s03: only pd.to_numeric(<year column>) is changed, so that s03's TRAIN rule
    'year > 2023 -> excluded' never fires; the TEST window is applied afterwards by this module."""

    def __init__(self):
        super().__init__("pandas_test_year_proxy")

    def __getattr__(self, k):
        return getattr(pd, k)

    @staticmethod
    def to_numeric(arg, *a, **kw):
        out = pd.to_numeric(arg, *a, **kw)
        if getattr(arg, "name", None) == "year":
            return out * 0      # TRAIN 'year > 2023' mask -> all False; real years stay in the data
        return out


def run(db_copy: Path, out_root: Path, test_mode: bool):
    import s03_build_dataset as B
    import x01_stress_recovery as Xr
    (out_root / "data").mkdir(parents=True, exist_ok=True)
    B.connect = _connect_factory(db_copy)
    B.DATA = out_root / "data"
    if test_mode:
        B.pd = _PdTestYear()
    rep = B.build()
    Xr.connect = _connect_factory(db_copy)
    Xr.OUT = out_root
    q, se_info = Xr.build()
    return rep, q, se_info


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate-on-train", action="store_true")
    g.add_argument("--test-sqlite")
    a = ap.parse_args()
    SCRATCH.mkdir(exist_ok=True)
    work = SCRATCH / "db_copy.sqlite"
    if a.validate_on_train:
        shutil.copy2(DB, work)
        out_root = SCRATCH / "train_validation"
        rep, q, _ = run(work, out_root, test_mode=False)
        new_p = pd.read_csv(out_root / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
        old_p = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
        old_q = pd.read_csv(OUT / "exploratory" / "stress_recovery" / "quadruples.csv", low_memory=False)
        res = {"validated_at": now(),
               "primary_identical_file_hash": sha256(out_root / "data" / "PRIMARY_EXPANDED.csv") == sha256(OUT / "data" / "PRIMARY_EXPANDED.csv"),
               "primary_same_ids": set(new_p.contrast_id) == set(old_p.contrast_id),
               "primary_max_abs_lnRR_diff": float((new_p.set_index("contrast_id").lnRR - old_p.set_index("contrast_id").lnRR).abs().max()),
               "quadruples_same_rows": len(q) == len(old_q) and set(q.contrast_id) == set(old_q.contrast_id),
               "quadruples_max_abs_D_diff": float((q.set_index("contrast_id").D - old_q.set_index("contrast_id").D).abs().max()),
               "rows": int(len(new_p)), "studies": int(new_p.study_id.nunique()), "quadruple_rows": int(len(q))}
        res["PASS"] = bool(res["primary_same_ids"] and res["primary_max_abs_lnRR_diff"] < 1e-12 and res["quadruples_same_rows"]
                           and res["quadruples_max_abs_D_diff"] < 1e-12)
        write_json(OUT / "test_inputs_validation.json", res)
        _cleanup()
        return res
    src = Path(a.test_sqlite)
    shutil.copy2(src, work)
    out_root = SCRATCH / "test_build"
    rep, q, se_info = run(work, out_root, test_mode=True)
    p = pd.read_csv(out_root / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    yr = pd.to_numeric(p.year, errors="coerce")
    outside = p[(yr < 2024) | yr.isna()]
    p = p[(yr >= 2024)]
    q = q[q.contrast_id.isin(set(p.contrast_id))]
    TI.mkdir(parents=True, exist_ok=True)
    p.to_csv(TI / "TEST_PRIMARY.csv", index=False)
    q.to_csv(TI / "TEST_quadruples.csv", index=False)
    shutil.copy2(out_root / "data" / "v2_yield_contrast_register.csv", TI / "TEST_contrast_register.csv")
    write_json(TI / "test_build_report.json", {
        "built_at": now(), "source_sqlite": str(src), "source_sha256": sha256(src), "rows": int(len(p)),
        "studies": int(p.study_id.nunique()), "quadruple_rows": int(len(q)), "quadruple_studies": int(q.study_id.nunique()),
        "excluded_outside_test_window": int(len(outside)), "status_counts": rep["status_counts"],
        "builder_sha256": sha256(Path(__file__))})
    _cleanup()
    return {"rows": len(p), "studies": int(p.study_id.nunique()), "quadruples": len(q)}


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
