"""Secondary TEST meta-analyses pre-registered in Addendum 1. Runs ONLY after the one-time s13 evaluation
(TEST_EVALUATED.lock), or as a code check with --dry-run-on-training (TRAIN used as both inputs; no meaning)."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
from v2_common import V2, OUT, now, sha256, write_json

RSCRIPT = Path(r"C:\Program Files\R\R-4.5.0\bin\Rscript.exe")
TST = OUT / "test_evaluation"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run-on-training", action="store_true")
    a = ap.parse_args()
    train = OUT / "data" / "PRIMARY_EXPANDED.csv"
    if a.dry_run_on_training:
        test, out = train, TST / "DRY_RUN_test_meta.json"
    else:
        if not (TST / "TEST_EVALUATED.lock").exists():
            sys.exit("REFUSED: run s13_test_evaluation.py (one-time TEST evaluation) first")
        test, out = OUT / "test_inputs" / "TEST_PRIMARY.csv", TST / "TEST_meta.json"
    TST.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(RSCRIPT), str(V2 / "src" / "meta_test.R"), str(train), str(test), str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"R failed:\n{r.stderr[-3000:]}")
    res = json.loads(out.read_text(encoding="utf-8"))
    res["label"] = "DRY_RUN_ON_TRAINING_DATA" if a.dry_run_on_training else "TEST_SECONDARY_META"
    res["run_at"] = now()
    write_json(out, res)
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str)[:2500])
