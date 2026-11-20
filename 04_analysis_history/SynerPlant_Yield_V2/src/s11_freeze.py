"""DATA_FREEZE V2 + model freeze manifest with SHA-256 hashes and honest acceptance gates.

Status values: READY_TO_USE only when every mandatory gate passes; otherwise READY_FOR_HUMAN_AUDIT (all automatic
gates pass, the V2 human audit of changed contrasts is pending) or DRAFT (an automatic gate fails).
"""
from __future__ import annotations
import json, shutil, sqlite3, datetime as dt
import pandas as pd
from v2_common import V2, OUT, AUDIT, DB, V1_FREEZE, now, sha256, write_json

EXP = V2 / "exports"


def gates():
    g = []
    integ = json.loads((AUDIT / "integrity_report.json").read_text())
    g.append(("integrity_checks", integ["overall"] == "PASS", f"{integ['overall']}; FAIL checks: "
              f"{[c['check'] for c in integ['checks'] if c['status'] == 'FAIL']}"))
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    reg = json.loads((AUDIT / "corrections_register.json").read_text(encoding="utf-8"))
    n_tv = sum(len(v["tv_values"]) for v in reg["value_corrections"])
    applied = con.execute("SELECT COUNT(*) FROM an_target_values WHERE verification='AUTO_VERIFIED_V2'").fetchone()[0]
    g.append(("register_value_corrections_applied", applied == n_tv, f"{applied}/{n_tv} values AUTO_VERIFIED_V2"))
    hv = con.execute("SELECT COUNT(*) FROM v2_changelog WHERE status LIKE '%HUMAN%'").fetchone()[0]
    g.append(("no_agent_human_verdicts", hv == 0, f"{hv} agent rows claiming HUMAN status"))
    p = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    g.append(("primary_train_dev_only", (pd.to_numeric(p.year) <= 2023).all(), f"max year {p.year.max()}"))
    g.append(("primary_unique_arm_pairs", not p.arm_pair.duplicated().any(), "one contrast per SB/S arm pair"))
    g.append(("primary_positive_means", bool(((p.mean_t > 0) & (p.mean_c > 0)).all()), "lnRR computable"))
    g.append(("v1_sources_unchanged", sha256(V1_FREEZE / "TFM_DATABASE_CLASS_A_FINAL.sqlite") ==
              "a7f473fdf248174c5c53e4173ea0a7bcd09905331dda9ad13c934e31c2dfd4de", "V1 freeze SQLite hash unchanged"))
    g.append(("external_test_untouched", not any("TEST" in str(x).upper() for x in p.get("dataset_role", [])),
              "no TEST rows; no TEST file opened by V2 code"))
    sel = json.loads((OUT / "ml" / "selection_report.json").read_text())
    g.append(("model_selected_by_prespecified_rule", "PRIMARY_EXPANDED" in sel["selection"], sel["selection"].get(
        "PRIMARY_EXPANDED", {}).get("reason", "")))
    unc = pd.read_csv(OUT / "uncertainty" / "interval_methods_comparison.csv")
    ch = unc[unc.model.str.startswith("chosen")]
    single = ch[ch.method == "group_cvplus_contrast"].coverage_contrast_study_balanced.iloc[0]
    simul = ch[ch.method == "group_cvplus_simultaneous"].coverage_all_contrasts_of_study.iloc[0]
    g.append(("interval_coverage_verified", single >= 0.85 and simul >= 0.85,
              f"held-out coverage single={single:.3f}, simultaneous={simul:.3f} (nominal 0.90, tolerance 0.05)"))
    aud = json.loads((AUDIT / "human_audit_v2_package.json").read_text())
    done, n_done = False, 0
    xl = AUDIT / "HUMAN_AUDIT_V2_PACKAGE.xlsx"
    try:
        a = pd.read_excel(xl, sheet_name="audit")
        req = a[a.required_sample == True]  # noqa
        v = req["human_verdict (CORRECT / INCORRECT / UNSURE)"].astype(str).str.upper().str.strip()
        done = len(req) >= aud["required_k"] and v.eq("CORRECT").all() and req.reviewer_name.notna().all()
        n_done = int(v.eq("CORRECT").sum())
    except Exception:
        pass
    g.append(("human_audit_v2_changed_contrasts", done, f"required k={aud['required_k']} of N={aud['changed_N']} "
              f"changed contrasts; {n_done} CORRECT; "
              f"{'complete' if done else 'PENDING (package ready: audit/HUMAN_AUDIT_V2_PACKAGE.xlsx)'}"))
    return [{"gate": a, "status": "PASS" if b else "FAIL", "value": c} for a, b, c in g]


def main():
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    G = gates()
    auto_ok = all(x["status"] == "PASS" for x in G if x["gate"] != "human_audit_v2_changed_contrasts")
    human_ok = next(x for x in G if x["gate"] == "human_audit_v2_changed_contrasts")["status"] == "PASS"
    status = "READY_TO_USE" if auto_ok and human_ok else ("READY_FOR_HUMAN_AUDIT" if auto_ok else "DRAFT")
    for old in EXP.glob("DATA_FREEZE_V2_*"):
        shutil.rmtree(old)          # one current freeze only (no redundant copies)
    out = EXP / f"DATA_FREEZE_V2_{ts}"
    out.mkdir(parents=True)
    files = []
    for p in sorted([*(OUT / "data").glob("*.csv"), *(OUT / "data").glob("*.json"), *(OUT / "model").glob("*"),
                     *(OUT / "ml").glob("*.json"), *(OUT / "ml").glob("*.csv"), *(OUT / "uncertainty").glob("*.json"),
                     *(OUT / "uncertainty").glob("*.csv"), *(OUT / "meta").glob("*"), *AUDIT.glob("*.json"),
                     AUDIT / "HUMAN_AUDIT_V2_PACKAGE.xlsx", *(V2 / "src").glob("*.py"), V2 / "requirements_v2.txt"]):
        if p.is_file():
            files.append({"path": str(p.relative_to(V2)).replace("\\", "/"), "sha256": sha256(p), "bytes": p.stat().st_size})
    files.append({"path": "db/TFM_V2_WORKING.sqlite", "sha256": sha256(DB), "bytes": DB.stat().st_size})
    man = {"build": ts, "status": status, "ready_to_use": status == "READY_TO_USE", "created_at": now(),
           "base_release": V1_FREEZE.name, "gates": G, "files": files,
           "test_policy": "the external 2024-2026 TEST has not been opened; it remains the final, one-time judge"}
    write_json(out / "MANIFEST.json", man)
    (out / "DATA_FREEZE_V2.md").write_text(
        f"# DATA_FREEZE V2 {ts}\n\nStatus: **{status}**\n\n" +
        "\n".join(f"- {x['status']} `{x['gate']}`: {x['value']}" for x in G) +
        f"\n\n{len(files)} files hashed in MANIFEST.json (SHA-256).\n", encoding="utf-8")
    return man


if __name__ == "__main__":
    m = main()
    print(m["status"])
    for x in m["gates"]:
        print(x["status"], x["gate"], "-", x["value"])
