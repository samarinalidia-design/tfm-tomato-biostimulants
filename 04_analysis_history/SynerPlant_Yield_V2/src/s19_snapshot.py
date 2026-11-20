"""Working-version snapshot without copying files: records SHA-256 of every result, code, dashboard, audit and report
file, plus the TEST freeze and lock references.
  python s19_snapshot.py            write exports/WORKING_VERSION_V2.0_TEST_EVALUATED.json (refuses if it exists)
  python s19_snapshot.py --verify   list every file changed / missing since the snapshot
  python s19_snapshot.py --v3 [--verify]   the same for exports/WORKING_VERSION_V3.0_BIOMASS_META.json (also hashes the V3 DB)
  python s19_snapshot.py --v31 [--verify]  exports/WORKING_VERSION_V3.1_REVIEW_CORRECTIONS.json (+ V3 DB, Excel exports, source PDFs)
"""
from __future__ import annotations
import json, sys
from v2_common import V2, OUT, DB, now, sha256, write_json

V31 = "--v31" in sys.argv
V3 = "--v3" in sys.argv or V31
SNAP = V2 / "exports" / ("WORKING_VERSION_V3.1_REVIEW_CORRECTIONS.json" if V31 else
                         "WORKING_VERSION_V3.0_BIOMASS_META.json" if V3 else "WORKING_VERSION_V2.0_TEST_EVALUATED.json")
ROOTS = ["outputs", "src", "dashboard", "audit"]
SINGLE = ["FINAL_REPORT_EN.md", "README_V2.md", "RUN_ALL_WINDOWS.bat", "OPEN_DASHBOARD_WINDOWS.bat", "requirements_v2.txt"]
SKIP = ("__pycache__", ".pyc", "~$")


def files():
    out = [V2 / f for f in SINGLE if (V2 / f).exists()]
    for r in ROOTS:
        out += [p for p in (V2 / r).rglob("*") if p.is_file() and not any(s in str(p) for s in SKIP)]
    out.append(DB)
    if V3:
        out.append(V2 / "db" / "TFM_V3_WORKING.sqlite")
    if V31:
        for x in ("EXCEL_TRAIN_TEST_V3.0", "EXCEL_TRAIN_TEST_V3.1"):
            out += [p for p in (V2 / "exports" / x).glob("*.xlsx")]
        out += sorted(V2.glob("*.pdf"))
    return sorted(out)


def main():
    if "--verify" in sys.argv:
        s = json.loads(SNAP.read_text(encoding="utf-8"))
        bad = [k for k, h in s["hashes_sha256"].items() if not (V2 / k).exists() or sha256(V2 / k) != h]
        print(f"Snapshot {s['created_at_utc']}: {len(s['hashes_sha256'])} files, "
              f"{'ALL UNCHANGED' if not bad else str(len(bad)) + ' changed/missing'}")
        for b in bad[:50]:
            print("  ", b)
        return 0
    if SNAP.exists():
        sys.exit("Snapshot exists; it is immutable.")
    test_freeze = V2.parent.parent / "TFM_TEST_2024_2026_Agent_System" / "exports" / "DATA_FREEZE_20261118T105532769144Z"
    info = {
        "version": "V2.0_TEST_EVALUATED",
        "created_at_utc": now(),
        "description": "SynerPlant Yield V2 after the one-time pre-registered TEST evaluation (yield). Further work "
                       "(biomass V2, yield V3) is done in db/TFM_V3_WORKING.sqlite; this version stays reproducible.",
        "test_freeze": str(test_freeze),
        "test_freeze_manifest_sha256": sha256(test_freeze / "MANIFEST.json"),
        "test_lock": "outputs/test_evaluation/TEST_EVALUATED.lock",
        "hashes_sha256": {p.relative_to(V2).as_posix(): sha256(p) for p in files()},
    }
    if V3:
        info.update({"version": "V3.0_BIOMASS_META", "description": "Yield V2 (TEST evaluated) + biomass V2 with its "
                     "one-time pre-registered TEST + yield V3 influence/proxy checks + meta-analysis diagnostics "
                     "(forest, moderators, publication bias) + Fig. 1-11 + report sections 12-15.",
                     "biomass_test_lock": "outputs/biomass_v2/test_evaluation/TEST_EVALUATED.lock",
                     "previous_version": "exports/WORKING_VERSION_V2.0_TEST_EVALUATED.json"})
    if V31:
        info.update({"version": "V3.1_REVIEW_CORRECTIONS", "description": "V3.0 + corrections after the external review "
                     "of the TRAIN Excel export (v31_build.py, audit/v31_register.json): non-stressed and non-biostimulant "
                     "contrasts removed, solvent/fertilizer control re-basing, separate drought/salinity measures, "
                     "negation-aware timing, recovered duration and dose units; PDF checks of four extreme values; "
                     "V3.1 model comparison on TRAIN (yield and biomass); Excel exports V3.0/V3.1; report section 16. "
                     "Both TESTs unchanged (one-time evaluations already done).",
                     "previous_version": "exports/WORKING_VERSION_V3.0_BIOMASS_META.json"})
    write_json(SNAP, info)
    print("Snapshot written:", SNAP.name)


if __name__ == "__main__":
    sys.exit(main())
