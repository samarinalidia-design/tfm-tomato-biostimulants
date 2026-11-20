"""Import the working workbook (header-driven), the yield registry and legacy figure JSONs."""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import (ColumnResolver, changelog, columns, now, q, rows, set_meta, sha256_file,
                 table_exists, tx)

PROTECTED_PREFIXES = ("wf_", "an_", "v_", "mart_", "sqlite_")


def _table_name(sheet: str) -> str:
    t = re.sub(r"[^0-9a-zA-Z_]+", "_", sheet.strip()).strip("_").lower() or "sheet"
    if t[0].isdigit():
        t = "s_" + t
    if t.startswith(PROTECTED_PREFIXES):
        t = "core_" + t
    if sheet.strip().startswith("_"):
        t = "_" + t
    return t


def _cell(v: Any) -> Any:
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    return v


def import_workbook(con, path: Path) -> Dict[str, int]:
    """Replace core tables with the workbook content. wf_/an_ tables are untouched."""
    from openpyxl import load_workbook
    path = Path(path).expanduser()
    from .db import get_meta
    old_hash = get_meta(con, "workbook_sha256")
    if old_hash:
        if old_hash == sha256_file(path):
            return json.loads(get_meta(con, "workbook_sheet_counts") or "{}")
        raise ValueError("baseline already imported: a different workbook requires a new isolated project/database")
    wb = load_workbook(path, read_only=True, data_only=True)
    counts: Dict[str, int] = {}
    with tx(con):
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            header = None
            hdr_row = 0
            for i, r in enumerate(it, start=1):
                if r and any(c not in (None, "") for c in r):
                    header, hdr_row = list(r), i
                    break
            if header is None:
                continue
            cols: List[str] = []
            for j, h in enumerate(header):
                name = str(h).strip() if h not in (None, "") else f"col_{j + 1}"
                base, k = name, 2
                while name in cols:
                    name = f"{base}__{k}"
                    k += 1
                cols.append(name)
            tname = _table_name(ws.title)
            con.execute(f"DROP TABLE IF EXISTS {q(tname)}")
            con.execute(f"CREATE TABLE {q(tname)} (_row INTEGER, " +
                        ", ".join(f"{q(c)}" for c in cols) + ")")
            ph = ", ".join("?" for _ in range(len(cols) + 1))
            batch, n = [], 0
            for i, r in enumerate(it, start=hdr_row + 1):
                if r is None or all(c in (None, "") for c in r):
                    continue
                vals = [_cell(c) for c in list(r)[:len(cols)]]
                vals += [None] * (len(cols) - len(vals))
                batch.append([i] + vals)
                n += 1
                if len(batch) >= 5000:
                    con.executemany(f"INSERT INTO {q(tname)} VALUES ({ph})", batch)
                    batch = []
            if batch:
                con.executemany(f"INSERT INTO {q(tname)} VALUES ({ph})", batch)
            counts[tname] = n
        set_meta(con, "workbook_path", str(path))
        set_meta(con, "workbook_sha256", sha256_file(path))
        set_meta(con, "workbook_imported_at", now())
        set_meta(con, "workbook_sheet_counts", counts)
        changelog(con, None, "workbook", path.name, "IMPORT", counts)
    wb.close()
    return counts


# ------------------------------------------------------------------ studies
_TITLE_YIELD = re.compile(r"\b(yield|fruit|harvest|productiv|marketable)", re.I)
_OUT_YIELD = re.compile(r"(yield|fruit[_ ]?(weight|mass)[_ ]?per[_ ]?plant|marketable|harvest)", re.I)
_OUT_DRY = re.compile(r"(dry[_ ]?(weight|mass|matter|biomass)|\bdw\b|biomass[_ ]?dry)", re.I)
_REG_P0 = {"PAIR_MEANS_CANDIDATE", "AUTHOR_EFFECT_ONLY", "YIELD_DATA_NO_PAIR", "TITLE_SIGNAL_ONLY"}


def seed_studies(con, cfg) -> Dict[str, int]:
    """Create wf_study_status rows for class-A studies and compute target-first priorities."""
    from .config import execution_contract_hash
    from .db import get_meta
    contract_hash=execution_contract_hash(cfg)
    if get_meta(con,"execution_contract_hash") is None:set_meta(con,"execution_contract_hash",contract_hash)
    elif get_meta(con,"execution_contract_hash")!=contract_hash:raise ValueError("execution contract changed; do not silently reuse verified results")
    cr = ColumnResolver(con, cfg.column_map)
    sid = cr.get("studies", "study_id", required=True)
    cls = cr.get("studies", "class_final")
    ttl = cr.get("studies", "title")
    st = rows(con, f"SELECT {q(sid)} AS study_id, " +
              (f"{q(cls)} AS class_final, " if cls else "NULL AS class_final, ") +
              (f"{q(ttl)} AS title " if ttl else "NULL AS title ") + "FROM studies")
    if cfg.get("scope.enforce_frozen_ids", True):
        scope_path = cfg.root / cfg.get("scope.manifest", "manifests/scope_A_399.csv")
        import csv
        with scope_path.open(encoding="utf-8-sig", newline="") as f:
            frozen = {r["study_id"] for r in csv.DictReader(f)}
        actual = {str(s["study_id"]) for s in st}
        if actual != frozen:
            raise ValueError(f"scope mismatch: missing={sorted(frozen-actual)} extra={sorted(actual-frozen)}")
    # outcome signals from existing measurements
    signal: Dict[str, set] = {}
    m_exp = cr.get("measurements", "experiment_id")
    e_id, e_sid = cr.get("experiments", "experiment_id"), cr.get("experiments", "study_id")
    m_out = cr.get("measurements", "outcome_std") or cr.get("measurements", "outcome_raw")
    if m_exp and e_id and e_sid and m_out:
        od_out, od_role = cr.get("outcome_dictionary", "outcome_std"), cr.get("outcome_dictionary", "target_role")
        role_map: Dict[str, str] = {}
        if od_out and od_role:
            for r in rows(con, f"SELECT {q(od_out)} AS o, {q(od_role)} AS r FROM outcome_dictionary"):
                if r["o"]:
                    role_map[str(r["o"]).strip().lower()] = str(r["r"] or "")
        for r in rows(con, f"SELECT e.{q(e_sid)} AS study_id, m.{q(m_out)} AS outcome "
                           f"FROM measurements m JOIN experiments e ON m.{q(m_exp)} = e.{q(e_id)}"):
            o = str(r["outcome"] or "")
            role = role_map.get(o.strip().lower(), "")
            s = signal.setdefault(str(r["study_id"]), set())
            if role.startswith("PRIMARY") or _OUT_YIELD.search(o):
                s.add("YIELD")
            if role.startswith("SECONDARY") or _OUT_DRY.search(o):
                s.add("DRY")
    reg = {r["study_id"]: r for r in rows(con, "SELECT * FROM wf_registry")} if table_exists(con, "wf_registry") else {}
    created = 0
    with tx(con):
        for s in st:
            study = str(s["study_id"]).strip()
            if not study or study.lower() == "none":
                continue
            if s["class_final"] not in (None, "", "A"):
                continue
            prio, why = 3, "no target signal yet (NOT_DETECTED != absent)"
            sig = signal.get(study, set())
            r = reg.get(study)
            if r and (r.get("evidence_tier") in _REG_P0 or r.get("eligibility_status") in _REG_P0):
                prio, why = 0, f"registry: {r.get('eligibility_status') or r.get('evidence_tier')}"
            elif "YIELD" in sig:
                prio, why = 0, "yield-like outcome already in measurements"
            elif s["title"] and _TITLE_YIELD.search(str(s["title"])):
                prio, why = 0, "title yield/fruit/harvest signal"
            elif "DRY" in sig:
                prio, why = 1, "dry-biomass outcome already in measurements"
            elif sig:
                prio, why = 2, "other outcomes present"
            cur = con.execute("INSERT OR IGNORE INTO wf_study_status(study_id, state, priority, priority_reason, "
                              "updated_at) VALUES (?, 'NEW', ?, ?, ?)", (study, prio, why, now()))
            created += cur.rowcount
            if cur.rowcount == 0:
                con.execute("UPDATE wf_study_status SET priority=?, priority_reason=?, updated_at=? "
                            "WHERE study_id=? AND state='NEW'", (prio, why, now(), study))
    pr = rows(con, "SELECT priority, COUNT(*) n FROM wf_study_status GROUP BY priority ORDER BY priority")
    return {"created": created, **{f"priority_{r['priority']}": r["n"] for r in pr}}


def import_registry(con, path: Path) -> int:
    """Yield feasibility registry (sheet REGISTRY_A_399 or CSV with the same headers)."""
    path = Path(path).expanduser()
    import pandas as pd
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        xl = pd.ExcelFile(path)
        sheet = "REGISTRY_A_399" if "REGISTRY_A_399" in xl.sheet_names else xl.sheet_names[0]
        df = xl.parse(sheet, dtype=str)
    else:
        df = pd.read_csv(path, dtype=str)
    norm = {c: re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_") for c in df.columns}
    df = df.rename(columns=norm)
    n = 0
    with tx(con):
        for rec in df.fillna("").to_dict("records"):
            sid = str(rec.get("study_id", "")).strip()
            if not sid:
                continue
            con.execute("INSERT INTO wf_registry(study_id, evidence_tier, eligibility_status, priority, payload) "
                        "VALUES (?,?,?,?,?) ON CONFLICT(study_id) DO UPDATE SET evidence_tier=excluded.evidence_tier, "
                        "eligibility_status=excluded.eligibility_status, priority=excluded.priority, "
                        "payload=excluded.payload",
                        (sid, rec.get("evidence_tier"), rec.get("eligibility_status"), rec.get("priority"),
                         json.dumps(rec, ensure_ascii=False)))
            n += 1
    return n


# ------------------------------------------------------- legacy figure JSON
def _role(outcome: str, declared: Optional[str]) -> str:
    d = (declared or "").lower()
    o = (outcome or "").lower()
    if "primary" in d or ("yield" in o and "relative" not in o):
        return "PRIMARY_YIELD"
    if "secondary" in d or _OUT_DRY.search(o):
        return "SECONDARY_DRY_BIOMASS"
    if d:
        return "AUXILIARY"
    return "AUXILIARY" if o else "UNKNOWN"


def import_legacy_figures(con, root: Path) -> Dict[str, Any]:
    """Load figure_numeric_data.json files (schemas v1.4/v1.5) as UNVERIFIED hints."""
    root = Path(root).expanduser()
    files = sorted(root.rglob("figure_numeric_data.json"))
    summary: Dict[str, Any] = {"files": len(files), "records": 0, "by_role": {}, "schema_versions": {},
                               "with_calibration": 0, "with_px": 0, "with_error_value": 0,
                               "recompute_mismatch": 0, "parse_errors": []}
    with tx(con):
        con.execute("DELETE FROM wf_legacy_figure WHERE json_path LIKE ?", (str(root) + "%",))
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception as exc:  # broken JSON is itself a finding
                summary["parse_errors"].append(f"{f}: {exc}")
                continue
            ver = str(data.get("schema_version", "unknown"))
            summary["schema_versions"][ver] = summary["schema_versions"].get(ver, 0) + 1
            study = str(data.get("study_id", ""))
            src_default = data.get("source_file_id") or (data.get("source_pdf") or {}).get("drive_file_id")
            labels = {}
            for fig in (data.get("figures") or data.get("figure_index") or []):
                labels[fig.get("source_figure_filename")] = fig.get("original_figure_label")
            for m in data.get("measurements") or []:
                cal = m.get("axis_calibration") or m.get("figure_axis_calibration")
                pxd = m.get("plot_coordinate_px") or {}
                value = m.get("value")
                recomputed = None
                if isinstance(cal, dict) and "pixel_zero" in cal and "pixel_other" in cal and pxd.get("y") is not None:
                    try:
                        p0, v0 = float(cal["pixel_zero"]), float(cal.get("zero_value", 0))
                        p1, v1 = float(cal["pixel_other"]), float(cal["other_value"])
                        recomputed = v0 + (float(pxd["y"]) - p0) * (v1 - v0) / (p1 - p0)
                        if value is not None and abs(recomputed - float(value)) > 1e-6 * max(1.0, abs(float(value))) + 1e-6:
                            summary["recompute_mismatch"] += 1
                    except (TypeError, ValueError, ZeroDivisionError):
                        recomputed = None
                role = _role(m.get("outcome_type", ""), m.get("outcome_role"))
                summary["by_role"][role] = summary["by_role"].get(role, 0) + 1
                summary["records"] += 1
                summary["with_calibration"] += int(bool(cal))
                summary["with_px"] += int(bool(pxd))
                summary["with_error_value"] += int(m.get("sd") is not None or m.get("se") is not None)
                fig_file = m.get("source_figure_filename")
                con.execute(
                    "INSERT INTO wf_legacy_figure(json_path, schema_version, study_id, source_file_id, figure_file, "
                    "figure_label, panel, group_label, outcome, outcome_role, value, unit, error_bar_type, sd, se, n, "
                    "timepoint, has_calibration, has_px, recomputed_value, method, verification, imported_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(f), ver, study, m.get("source_file_id") or src_default, fig_file,
                     m.get("original_figure_label") or labels.get(fig_file),
                     m.get("panel_label") or m.get("panel_id"), m.get("experimental_group"),
                     m.get("outcome_type"), role, value, m.get("unit"), m.get("error_bar_type"),
                     m.get("sd"), m.get("se"), m.get("n"), m.get("timepoint"), int(bool(cal)), int(bool(pxd)),
                     recomputed, m.get("measurement_method"),
                     m.get("verification_status"), now()))
    return summary
