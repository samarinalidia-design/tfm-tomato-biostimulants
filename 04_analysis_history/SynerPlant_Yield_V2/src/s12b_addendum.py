"""Addendum 1 to the TEST pre-registration (written BEFORE any TEST data are opened; immutable once written).

Adds: (1) the TEST dataset builder (s14) and its byte-identical validation on TRAIN; (2) the TEST year-window rule;
(3) the confirmatory R meta-analysis of TRAIN (results frozen); (4) secondary TEST meta-analyses (s17 + meta_test.R);
(5) the chronology of the TEST extraction relative to the V1 and V2 freezes.
  python s12b_addendum.py            write (refuses if it exists)
  python s12b_addendum.py --verify   check every hash of the registration AND the addendum
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from v2_common import V2, OUT, V1_ML, now, sha256, write_json

PR = OUT / "preregistration"
ADD = PR / "ADDENDUM_1_TEST.json"
TEST_PROJECT = V2.parent.parent / "TFM_TEST_2024_2026_Agent_System"
FILES = ["src/s14_build_test_dataset.py", "src/s16_meta_R.py", "src/meta_confirmatory.R", "src/meta_test.R",
         "src/s17_test_meta.py", "src/s12b_addendum.py", "outputs/meta/R_confirmatory.json",
         "outputs/test_inputs_validation.json", "outputs/preregistration/PREREG_TEST_V2.json"]


def verify():
    reg = json.loads((PR / "PREREG_TEST_V2.json").read_text())
    add = json.loads(ADD.read_text())
    bad = [k for k, h in {**reg["hashes_sha256"], **add["hashes_sha256"]}.items()
           if not (V2 / k).exists() or sha256(V2 / k) != h]
    lock = (OUT / "test_evaluation" / "TEST_EVALUATED.lock").exists()
    n = len(reg["hashes_sha256"]) + len(add["hashes_sha256"])
    print(f"Registration {reg['registered_at_utc']} + Addendum 1 {add['registered_at_utc']}: {n} hashed files "
          f"{'INTACT' if not bad else 'BROKEN: ' + str(bad)}; TEST evaluated: {lock}")
    return 1 if bad else 0


def main():
    if ADD.exists():
        print("Addendum 1 already exists; it is immutable. Nothing written.")
        return
    val = json.loads((OUT / "test_inputs_validation.json").read_text())
    if not val.get("PASS"):
        sys.exit("REFUSED: TEST builder validation did not pass")
    R = json.loads((OUT / "meta" / "R_confirmatory.json").read_text(encoding="utf-8"))
    v1_freeze = V1_ML / "outputs" / "MODEL_FREEZE.json"
    chk = TEST_PROJECT / "work" / "CHECKPOINT.json"
    add = {
        "title": "Addendum 1 to PREREG_TEST_V2 (before the TEST is opened)",
        "registered_at_utc": now(),
        "test_status_at_registration": "NOT OPENED: no TEST outcome, table or study file has been read by V2 code",
        "1_test_dataset_builder": {
            "script": "src/s14_build_test_dataset.py --test-sqlite <TEST DATA_FREEZE sqlite>",
            "principle": "imports the frozen s03_build_dataset.py and x01_stress_recovery.py unchanged; only the input "
                         "database and output folder are redirected",
            "validation_on_train": val,
            "outputs": ["outputs/test_inputs/TEST_PRIMARY.csv", "outputs/test_inputs/TEST_quadruples.csv"]},
        "2_test_specific_rules": {
            "year_window": "the TRAIN rule 'year > 2023 excluded' is replaced by 'year < 2024 excluded' (TEST window)",
            "study_specific_train_decisions": "value corrections, relative-unit inclusions and study exclusions of the "
                                              "TRAIN register name TRAIN studies only and do not apply to TEST",
            "unit_unresolved_test_contrasts": "excluded from TEST_PRIMARY (no study-level review is allowed after "
                                              "opening TEST); counted and reported",
            "generic_rules_applied": "yield tiers, one contrast per SB/S arm pair (terminal cumulative total), "
                                     "synthetic-PGR exclusion, box-centre / dry / non-marketable routing"},
        "3_confirmatory_TRAIN_meta_analysis_R": {
            "method": "metafor::rma.mv REML, random ~1|study/contrast; clubSandwich CR2 by study (Satterthwaite df)",
            "results_frozen": {k: {x: v[x] for x in ("k_studies", "mu_lnRR", "pct_effect", "ci95_CR2", "p_CR2",
                                                      "tau2_between", "tau2_within", "pi95_new_study_mean")}
                               for k, v in R.items() if isinstance(v, dict) and "mu_lnRR" in v},
            "agreement_with_python_REML": "|mu_R - mu_Python| < 2e-8 in all five sets"},
        "4_secondary_TEST_meta_analyses": {
            "script": "src/s17_test_meta.py (runs only after the one-time s13 evaluation)",
            "analyses": ["TEST pooled lnRR (same model, CR2)", "TRAIN vs TEST difference (dataset moderator, CR2)",
                         "TRAIN+TEST pooled lnRR (updated synthesis)"],
            "interpretation": "consistency if the 95% CR2 CI of the TEST-minus-TRAIN difference includes 0; the TEST "
                              "pooled mean is also compared with the TRAIN 95% prediction interval for a new study's mean "
                              "(-0.43 to 1.52). Secondary only: never changes the primary verdicts of PREREG_TEST_V2"},
        "5_chronology_and_blinding": {
            "test_extraction_frozen_against": "V1 MODEL_FREEZE (pipeline.yaml model_freeze_path of the TEST project)",
            "v1_model_freeze_sha256": sha256(v1_freeze) if v1_freeze.exists() else None,
            "test_project_last_checkpoint_utc": json.loads(chk.read_text()).get("at") if chk.exists() else None,
            "statement": "The TEST extraction started under the V1 freeze. V2 (data audit, models, intervals, conditional "
                         "models) was developed afterwards without access to any TEST data: only the TEST project's "
                         "task-state counts were looked at. The TEST therefore remains independent of V2. The TEST "
                         "project configuration is not changed."},
        "hashes_sha256": {f: sha256(V2 / f) for f in FILES},
    }
    write_json(ADD, add)
    md = [f"# Addendum 1 to the TEST pre-registration — {add['registered_at_utc']}", "",
          "TEST status: **not opened**.", "",
          "1. **TEST builder** `s14_build_test_dataset.py`: imports the frozen s03/x01 unchanged. On a TRAIN copy it "
          f"reproduces PRIMARY_EXPANDED byte-identically ({val['rows']} contrasts / {val['studies']} studies) and all "
          f"{val['quadruple_rows']} quadruples.",
          "2. **TEST rules**: year window < 2024 excluded; TRAIN study-specific decisions do not apply; unit-unresolved "
          "TEST contrasts are excluded and reported.",
          "3. **Confirmatory TRAIN meta-analysis (R metafor + CR2)**: V2 primary +{:.0f} % (CR2 95 % CI {:.3f}–{:.3f}, "
          "31 studies); agreement with Python < 2·10⁻⁸.".format(R["PRIMARY_EXPANDED"]["pct_effect"],
                                                                  *R["PRIMARY_EXPANDED"]["ci95_CR2"]),
          "4. **Secondary TEST meta-analyses** (`s17_test_meta.py`, after s13 only): TEST pooled effect; TEST − TRAIN "
          "difference; TRAIN + TEST synthesis. They never change the primary verdicts.",
          "5. **Chronology**: the TEST extraction started under the V1 freeze; V2 never saw TEST data.", "",
          "## SHA-256", *[f"- `{k}` {v}" for k, v in add["hashes_sha256"].items()]]
    (PR / "ADDENDUM_1_TEST.md").write_text("\n".join(md), encoding="utf-8")
    print("Addendum 1 written", add["registered_at_utc"])


if __name__ == "__main__":
    if "--verify" in sys.argv:
        sys.exit(verify())
    main()
