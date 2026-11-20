"""TFM Table 7 — mandatory gates before the ML notebook, plus accuracy dashboards."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .db import ColumnResolver, get_meta, q, rows, table_exists

DONE_STATES = ("CLOSED", "NO_TARGET_CONFIRMED", "EXCLUDED_SCOPE")


def _one(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return r[0] if r else 0


def compute(con, cfg) -> List[Dict[str, Any]]:
    g: List[Dict[str, Any]] = []

    def add(name, criterion, value, status, action):
        g.append({"gate": name, "criterion": criterion, "value": value, "status": status, "if_fail": action})

    integ = _one(con, "SELECT COUNT(*) FROM wf_validation WHERE status='OPEN' AND severity='BLOCKING' AND rule_id IN ('G001','G002')")
    add("1 Relational integrity", "unique PKs; valid FKs study->experiment->arm->measurement",
        f"{integ} open blocking issues", "PASS" if integ == 0 else "FAIL", "stop build; fix links (see qa_issues)")

    tot = _one(con, "SELECT COUNT(*) FROM wf_study_status")
    done = _one(con, "SELECT COUNT(*) FROM wf_study_status WHERE state IN (%s)" % ",".join("?" for _ in DONE_STATES), DONE_STATES)
    states = {r["state"]: r["n"] for r in rows(con, "SELECT state, COUNT(*) n FROM wf_study_status GROUP BY state")}
    add("2 Extraction coverage", "all non-X studies closed/confirmed incl. supplements",
        f"{done}/{tot} closed ({(100 * done / tot if tot else 0):.1f} %); {states}",
        "PASS" if tot and done == tot else "FAIL", "keep PENDING; do not declare the base final")

    ntv = _one(con, "SELECT COUNT(*) FROM an_target_values")
    prov = _one(con, "SELECT COUNT(*) FROM an_target_values WHERE source_file_id IS NOT NULL AND locator IS NOT NULL "
                     "AND verification IS NOT NULL")
    add("3 Target provenance", "100 % of targets with source_file_id + locator + verification",
        f"{prov}/{ntv}", "PASS" if ntv and prov == ntv else "FAIL", "exclude from verified mart")

    sbs = _one(con, "SELECT COUNT(*) FROM an_contrasts WHERE contrast_type='SB_vs_S'")
    no_n = _one(con, "SELECT COUNT(*) FROM an_contrasts WHERE contrast_type='SB_vs_S' AND (n_t IS NULL OR n_c IS NULL)")
    var_ok = _one(con, "SELECT COUNT(*) FROM an_contrasts WHERE contrast_type='SB_vs_S' AND var_available=1")
    add("4 n and uncertainty", "defensible n; SD/SE/CI distinguished",
        f"{sbs} SB-vs-S contrasts; {var_ok} with variance; {no_n} without n",
        "PASS" if sbs and no_n == 0 else ("WARN" if sbs else "FAIL"), "flag; exclude from weighted analyses")

    nonpos = _one(con, "SELECT COUNT(*) FROM an_contrasts WHERE contrast_type='SB_vs_S' AND effect IS NULL")
    add("5 Contrasts", "positive means for lnRR; comparable arms; dependency recorded",
        f"{nonpos} non-computable; shared controls flagged", "PASS" if sbs and nonpos == 0 else ("WARN" if sbs else "FAIL"),
        "do not compute / mark exploratory")

    blk = _one(con, "SELECT COUNT(*) FROM wf_validation WHERE status='OPEN' AND severity='BLOCKING'")
    outl = _one(con, "SELECT COUNT(*) FROM wf_validation WHERE status='OPEN' AND rule_id='C001'")
    add("6 Biological QA", "no impossible/duplicate blocking values; outliers reviewed",
        f"{blk} open blocking; {outl} outliers awaiting review", "PASS" if blk == 0 and outl == 0 else ("WARN" if blk == 0 else "FAIL"),
        "resolve or document flag")

    leak = get_meta(con, "last_export_leakage_check")
    add("7 Leakage", "IDs/provenance/post-treatment biomarkers outside primary features",
        leak or "export not run", "PASS" if leak == "PASS" else "FAIL", "FAIL until removed")

    exp = get_meta(con, "last_export_manifest")
    add("8 Reproducibility", "CSV/Parquet + dictionary + QA + SHA-256 from the same run",
        exp or "export not run", "PASS" if exp else "FAIL", "do not freeze dataset")

    test_rows = 0
    if table_exists(con, "studies"):
        cr = ColumnResolver(con, cfg.column_map)
        dr = cr.get("studies", "dataset_role")
        if dr:
            test_rows = _one(con, f"SELECT COUNT(*) FROM studies WHERE UPPER(COALESCE({q(dr)},'')) LIKE '%TEST%'")
    add("9 External TEST", "0 TEST records inspected before MODEL_FREEZE", f"{test_rows} TEST rows",
        "PASS" if test_rows == 0 else "FAIL", "invalidates confirmatory test")
    return g


def accuracy(con, cfg) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    rec = rows(con, "SELECT family, outcome, COUNT(*) n FROM wf_reconciliation GROUP BY family, outcome")
    out["reconciliation"] = rec
    tot = sum(r["n"] for r in rec)
    agree = sum(r["n"] for r in rec if r["outcome"] == "AGREE")
    out["double_extraction_agreement"] = round(agree / tot, 4) if tot else None
    out["verification_mix"] = rows(con, "SELECT verification, source_kind, COUNT(*) n FROM an_target_values "
                                        "GROUP BY verification, source_kind")
    a = rows(con, "SELECT verdict, COUNT(*) n FROM wf_audit GROUP BY verdict")
    na = sum(r["n"] for r in a)
    out["audit"] = {"items": na, "correct_rate": round(sum(r["n"] for r in a if r["verdict"] == "CORRECT") / na, 4) if na else None}
    t = rows(con, "SELECT p1.study_id, p1.fruit_yield y1, p2.fruit_yield y2, p1.dry_biomass b1, p2.dry_biomass b2 "
                  "FROM wf_triage p1 JOIN wf_triage p2 ON p1.study_id=p2.study_id AND p1.pass='P1' AND p2.pass='P2'")
    out["second_triage"] = {"n": len(t), "disagreements": sum(1 for r in t if r["y1"] != r["y2"] or r["b1"] != r["b2"])}
    # twin validation: figure values vs table values for the same record
    tw = rows(con, "SELECT COALESCE(f.mean_norm,f.mean) fm, COALESCE(t.mean_norm,t.mean) tm FROM wf_values f JOIN an_target_values t ON f.record_key=t.record_key "
                   "AND f.study_id=t.study_id WHERE f.source_kind='FIGURE' AND t.source_kind<>'FIGURE' AND t.mean<>0 AND COALESCE(f.unit_norm,f.unit_raw)=COALESCE(t.unit_norm,t.unit_raw)")
    errs = sorted(abs(r["fm"] - r["tm"]) / abs(r["tm"]) for r in tw)
    if errs:
        out["figure_twin_rel_error"] = {"n": len(errs), "median": round(errs[len(errs) // 2], 4),
                                        "p95": round(errs[min(len(errs) - 1, int(0.95 * len(errs)))], 4), "max":round(max(errs),4), "above_5pct":sum(e>0.05+1e-12 for e in errs)}
    gold = get_meta(con, "last_gold_score")
    if gold:
        out["gold_standard"] = json.loads(gold)
    return out
