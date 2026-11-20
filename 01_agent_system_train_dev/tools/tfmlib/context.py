"""Targeted context packets (Methods/Results + tables + captions, ~20-40k tokens)
instead of whole papers — the cause of the failed V4.0 API run."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import ColumnResolver, q, rows, table_exists
from .tasks import reviewable_patches

TARGET_OUT = re.compile(r"(yield|fruit|harvest|marketable|dry[_ ]?(weight|mass|matter|biomass)|\bdw\b|biomass)", re.I)

SCHEMA_FOR = {
    "TRIAGE": "triage", "TRIAGE_2ND": "triage", "SCOPE": "scope", "DESIGN": "design",
    "EXTRACT_A": "values", "EXTRACT_B": "values", "FIGURE_A": "figure", "FIGURE_B": "figure",
    "ADJUDICATE": "adjudication", "MODERATORS": "moderators", "ROB": "rob", "DEDUP": "relations",
    "AUDIT": "audit", "PATCH_REVIEW":"patches", "QA_REVIEW":"qa_review", "TEMPORAL":"temporal", "MODERATORS_VERIFY":"moderators","MODERATORS_ADJ":"moderators", "DRY_BASIS":"dry_basis",
}


# ------------------------------------------------------------- DB extracts
def study_dump(con, cfg, study_id: str, light: bool = False) -> Dict[str, Any]:
    cr = ColumnResolver(con, cfg.column_map)
    out: Dict[str, Any] = {"study_id": study_id}
    sid = cr.get("studies", "study_id")
    if sid:
        r = rows(con, f"SELECT * FROM studies WHERE CAST({q(sid)} AS TEXT)=?", (study_id,))
        out["study"] = {k: v for k, v in (r[0] if r else {}).items() if k != "_row"}
    f_sid = cr.get("files", "study_id")
    if f_sid:
        out["files"] = [{k: v for k, v in x.items() if k != "_row"}
                        for x in rows(con, f"SELECT * FROM files WHERE CAST({q(f_sid)} AS TEXT)=?", (study_id,))]
    e_id, e_sid = cr.get("experiments", "experiment_id"), cr.get("experiments", "study_id")
    exps: List[Dict[str, Any]] = []
    if e_id and e_sid:
        exps = rows(con, f"SELECT * FROM experiments WHERE CAST({q(e_sid)} AS TEXT)=?", (study_id,))
    out["experiments"] = [{k: v for k, v in x.items() if k != "_row"} for x in exps]
    exp_ids = [str(x[e_id]) for x in exps] if e_id else []
    out["arms"], out["stress_factors"], out["arm_components"], out["target_measurements"] = [], [], [], []
    a_exp, a_id = cr.get("arms", "experiment_id"), cr.get("arms", "arm_id")
    if exp_ids and a_exp:
        ph = ",".join("?" for _ in exp_ids)
        arms = rows(con, f"SELECT * FROM arms WHERE CAST({q(a_exp)} AS TEXT) IN ({ph})", exp_ids)
        out["arms"] = [{k: v for k, v in x.items() if k not in ("_row",) and v not in (None, "")} for x in arms]
        arm_ids = [str(x[a_id]) for x in arms] if a_id else []
        if arm_ids and not light:
            ph2 = ",".join("?" for _ in arm_ids)
            for t, key in (("stress_factors", "stress_factors"), ("arm_components", "arm_components")):
                c = cr.get(t, "arm_id")
                if c:
                    out[key] = [{k: v for k, v in x.items() if k != "_row" and v not in (None, "")}
                                for x in rows(con, f"SELECT * FROM {q(t)} WHERE CAST({q(c)} AS TEXT) IN ({ph2})", arm_ids)]
        m_exp = cr.get("measurements", "experiment_id")
        m_out = cr.get("measurements", "outcome_std") or cr.get("measurements", "outcome_raw")
        if m_exp and m_out:
            ms = rows(con, f"SELECT * FROM measurements WHERE CAST({q(m_exp)} AS TEXT) IN ({ph})", exp_ids)
            out["target_measurements"] = [{k: v for k, v in x.items() if k != "_row" and v not in (None, "")}
                                          for x in ms if TARGET_OUT.search(str(x.get(m_out) or ""))][:400]
    if table_exists(con, "wf_registry"):
        r = rows(con, "SELECT evidence_tier, eligibility_status, priority FROM wf_registry WHERE study_id=?", (study_id,))
        out["yield_registry"] = r[0] if r else None
    out["status"] = (rows(con, "SELECT * FROM wf_study_status WHERE study_id=?", (study_id,)) or [None])[0]
    out["triage"] = rows(con, "SELECT pass, fruit_yield, dry_biomass, yield_components, scope_flag, scope_reason, "
                              "n_experiments, design_summary FROM wf_triage WHERE study_id=?", (study_id,))
    out["slots"] = rows(con, "SELECT * FROM wf_target_slots WHERE study_id=? ORDER BY slot_id", (study_id,))
    out["design"] = design_map(con, study_id)
    return out


def design_map(con, study_id: str) -> Dict[str, Any]:
    arms = rows(con, "SELECT arm_key, experiment_key, arm_id, label_in_source, stress_code, stress_desc, bio_code, "
                     "bio_desc, n_bio_components, component_codes, background_key, genotype, season, site, role "
                     "FROM wf_design_arms WHERE study_id=? ORDER BY arm_key", (study_id,))
    for arm in arms:
        arm["component_codes"] = json.loads(arm["component_codes"] or "[]")
    return {
        "experiments": rows(con, "SELECT experiment_key, experiment_id, description, system, allocation, factorial_verified "
                                 "FROM wf_design_experiments WHERE study_id=? ORDER BY experiment_key", (study_id,)),
        "arms": arms,
        "timepoints": rows(con, "SELECT timepoint_key, experiment_key, label, days, kind, is_terminal "
                                "FROM wf_design_timepoints WHERE study_id=? ORDER BY timepoint_key", (study_id,)),
    }


# ---------------------------------------------------------- source files
def find_study_dir(cfg, study_id: str) -> Optional[Path]:
    root = cfg.p("docling_root")
    mp = cfg.paths.get("docling_map_csv")
    if mp:
        p = Path(str(mp)).expanduser()
        if p.exists():
            with open(p, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if str(r.get("study_id", "")).strip() == study_id and r.get("folder"):
                        d = Path(r["folder"]).expanduser()
                        return d if d.is_absolute() or not root else root / d
    if not root or not root.exists():
        return None
    for pat in cfg.paths.get("docling_study_globs") or ["{study_id}", "**/{study_id}"]:
        token = re.compile(r"(?<![A-Za-z0-9])" + re.escape(study_id) + r"(?![A-Za-z0-9])")
        hits = sorted(h for h in root.glob(pat.format(study_id=study_id)) if h.is_dir() and token.search(h.name))
        if len(hits) > 1:
            raise ValueError(f"ambiguous Docling folder for {study_id}: add an exact entry to docling_map_csv")
        if hits:
            return hits[0]
    return None


def _glob_many(base: Path, patterns: List[str]) -> List[Path]:
    seen, out = set(), []
    for pat in patterns:
        for h in sorted(base.glob(pat)):
            if h.is_file() and h not in seen:
                seen.add(h)
                out.append(h)
    return out


def collect_sources(cfg, study_dir: Optional[Path]) -> Dict[str, List[str]]:
    pats = cfg.paths.get("patterns") or {}
    res: Dict[str, List[str]] = {k: [] for k in ("document_text", "table_csv", "table_png", "figure_png",
                                                 "handoff", "inventory", "evidence_index")}
    if not study_dir or not study_dir.exists():
        return res
    defaults = {"document_text": ["**/parsed_v4_3/document.md", "**/parsed_v4_3/document.txt", "document.md", "document.txt", "document_text.md", "**/document_text.md"], "table_csv": ["**/tables/*.csv"],
                "table_png": ["**/tables/*.png"], "figure_png": ["**/figures/**/*.png", "**/FIG_*/*.png"],
                "handoff": ["**/STUDY_HANDOFF.v4_3.json", "**/STUDY_HANDOFF.json"], "inventory": ["**/source_inventory.json"],
                "evidence_index": ["**/evidence_index.jsonl"]}
    for k in res:
        found = _glob_many(study_dir, pats.get(k) or defaults[k])
        if k == "document_text":   # only the first markdown file that looks like the document
            found = [f for f in found if "table" not in f.name.lower()][:3]
        res[k] = [str(f) for f in found]
    return res


def split_sections(md: str) -> List[Dict[str, str]]:
    parts: List[Dict[str, str]] = []
    cur = {"heading": "(front)", "text": ""}
    for line in md.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+\S", line):
            parts.append(cur)
            cur = {"heading": line.strip("# ").strip(), "text": line + "\n"}
        else:
            cur["text"] += line + "\n"
    parts.append(cur)
    return [p for p in parts if p["text"].strip()]


def targeted_text(md: str, keep_re: str, drop_re: str, max_chars: int) -> str:
    secs = split_sections(md)
    if len(secs) <= 2:  # no usable headings: cut at the reference list
        m = re.search(r"\n\s*(references|literature cited|bibliography)\s*\n", md, re.I)
        txt = md[:m.start()] if m else md
        return txt[:max_chars]
    keep = re.compile(keep_re, re.I)
    drop = re.compile(drop_re, re.I)
    out, used = [], 0
    for s in secs:
        h = s["heading"]
        if drop.search(h) and not keep.search(h):
            continue
        if keep.search(h) or keep.search(s["text"][:400]) or h == "(front)":
            chunk = s["text"] if h != "(front)" else s["text"][:2500]
            if used + len(chunk) > max_chars:
                chunk = chunk[: max(0, max_chars - used)]
            out.append(chunk)
            used += len(chunk)
            if used >= max_chars:
                break
    return "\n".join(out)


def _read(path: str, limit: int = 400000) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def source_texts(cfg, study_id: str) -> List[str]:
    """All parsed text available for the deterministic number-in-source check."""
    d = find_study_dir(cfg, study_id)
    src = collect_sources(cfg, d)
    texts = [_read(p) for p in src["document_text"]]
    texts += [_read(p, 200000) for p in src["table_csv"]]
    return [t for t in texts if t]


# ---------------------------------------------------------------- packets
def build_packet(con, cfg, task: Dict[str, Any]) -> Path:
    tid, ttype, study = task["task_id"], task["task_type"], task["study_id"]
    pdir = cfg.work_dir / "packets" / tid
    pdir.mkdir(parents=True, exist_ok=True)
    light = ttype in ("AUDIT", "DEDUP")
    dump = study_dump(con, cfg, study, light=light)
    sdir = find_study_dir(cfg, study)
    src = collect_sources(cfg, sdir)
    ctx_cfg = cfg.paths.get("context") or {}
    max_chars = int(ctx_cfg.get("max_chars", 120000))
    keep_re = ctx_cfg.get("keep_sections_regex", r"(method|result|table|figure|yield|biomass)")
    drop_re = ctx_cfg.get("drop_sections_regex", r"(introduction|discussion|reference)")

    ctx_lines: List[str] = [f"# Context packet {tid} — study {study} — {ttype}\n"]
    st = dump.get("study") or {}
    ctx_lines.append(f"**Title:** {st.get('title', '')}  \n**DOI:** {st.get('doi', '')}  \n**Year:** {st.get('year', '')}\n")
    include_tables_inline = ttype in ("TRIAGE", "SCOPE", "DESIGN", "EXTRACT_A", "MODERATORS", "ROB")
    if ttype == "TRIAGE_2ND":
        ctx_lines.append("> Independent target discovery: inspect every original full text and supplementary. "
                         "The earlier biomass-focused extraction is not a complete source inventory. "
                         "Do not read Docling outputs or the first triage.\n")
    elif src["document_text"]:
        md = _read(src["document_text"][0])
        if ttype in ("EXTRACT_B", "FIGURE_B", "TRIAGE_2ND"):
            md = "\n".join(s["text"] for s in split_sections(md) if re.search(r"method|material|statistic", s["heading"], re.I))
        budget = max_chars if ttype != "EXTRACT_B" else max_chars // 2
        ctx_lines.append("## Methods / Results (targeted)\n")
        ctx_lines.append(targeted_text(md, keep_re, drop_re, budget))
    else:
        ctx_lines.append("> Parsed document text NOT found. Locate the study folder (see paths in packet.json) "
                         "or read the original PDF pages directly.\n")
    if include_tables_inline and src["table_csv"]:
        ctx_lines.append("\n## Parsed tables (Docling CSV — verify against the table image when in doubt)\n")
        for p in src["table_csv"][:40]:
            ctx_lines.append(f"\n### {Path(p).name}\n```csv\n{_read(p, 20000)}\n```\n")
    context_text = "\n".join(ctx_lines)
    (pdir / "context.md").write_text(context_text, encoding="utf-8")

    schema_name = SCHEMA_FOR.get(ttype, "values")
    packet: Dict[str, Any] = {
        "task": {k: task[k] for k in ("task_id", "study_id", "task_type", "agent", "scope_ref", "attempts")},
        "output_path": str((cfg.work_dir / "outbox" / f"{tid}.json").relative_to(cfg.root)),
        "output_schema": f"schema/json/{schema_name}.schema.json",
        "submit_cmd": f"python3 tools/tfm.py submit {tid} work/outbox/{tid}.json",
        "context_md": str((pdir / "context.md").relative_to(cfg.root)),
        "context_chars": len(context_text),
        "sources": {"study_dir": str(sdir) if sdir else None, **src,
                    "fulltext_root": str(cfg.p("fulltext_root") or ""),
                    "supplements_root": str(cfg.p("supplements_root") or ""),
                    "figures_root": str(cfg.p("figures_root") or "")},
        "study": dump,
        "target_discovery": cfg.get("target_discovery", {}),
    }
    if ttype in ("EXTRACT_A", "EXTRACT_B", "FIGURE_A", "FIGURE_B", "ADJUDICATE", "MODERATORS", "ROB", "AUDIT"):
        packet["design"] = design_map(con, study)
    if ttype in ("EXTRACT_B", "FIGURE_B", "TRIAGE_2ND"):
        for k in ("target_measurements", "triage", "yield_registry"):
            packet["study"].pop(k, None)
        packet["study"]["study"].pop("notes", None)
    packet["source_warning"] = "DOCLING_UNVERIFIED. Original PDF/supplement is authoritative. Receipts are required for source verification."
    if ttype in ("EXTRACT_A", "EXTRACT_B"):
        packet["slots"] = rows(con, "SELECT * FROM wf_target_slots WHERE study_id=? AND route IN ('EXTRACT') "
                                    "ORDER BY slot_id", (study,))
        packet["endpoint_rules"] = cfg.pipeline.get("endpoints")
        packet["source_priority"] = cfg.get("source_priority")
        if ttype == "EXTRACT_B":
            packet["modality_rule"] = ("PASS B: read numbers from the table IMAGES (table_png) or rendered PDF pages, "
                                       "not from Docling CSV. Do not open work/outbox files of other passes.")
    if ttype in ("FIGURE_A", "FIGURE_B"):
        packet["slots"] = rows(con, "SELECT * FROM wf_target_slots WHERE slot_id=?", (task["scope_ref"],))
        packet["figure_rules"] = cfg.get("figures")
        packet["pass"] = "FA" if ttype == "FIGURE_A" else "FB"
        packet["figure_candidates"] = figure_candidates(cfg, sdir, packet["slots"][0] if packet["slots"] else {})
    if ttype == "ADJUDICATE":
        packet["conflicts"] = conflicts_for(con, study)
    if ttype == "TRIAGE_2ND":
        packet["independence_rule"] = "Do NOT read wf_triage pass P1, earlier target decisions, old inventories or Docling outputs. Independently discover primary fruit yield in ALL original sources, even when biomass is present."
        packet["study"] = {k: v for k, v in packet["study"].items() if k in ("study_id", "study", "files")}
        packet["study"]["study"] = {k: v for k, v in packet["study"].get("study", {}).items() if k in ("study_id", "doi", "title", "authors", "year", "publication_type")}
        for key in ("document_text", "table_csv", "table_png", "figure_png", "study_dir", "handoff", "inventory", "evidence_index", "figures_root"):
            packet["sources"].pop(key, None)
    if ttype == "DRY_BASIS":
        packet["dry_basis_records"] = rows(con, "SELECT record_key,arm_key,source_file_id,page,locator,unit_raw FROM an_target_values WHERE study_id=? AND endpoint='DRY_BIOMASS' AND record_key NOT IN (SELECT tv_record_key FROM wf_dry_basis WHERE study_id=?)", (study, study))
        packet["dry_basis_instruction"] = "Read the original Methods, caption and table header. Mark DRY_CONFIRMED only when the source states oven/dry weight or dry matter for these records."
    if ttype == "MODERATORS_VERIFY":
        packet["moderator_verification"]="Independently read all relevant pre-experimental/context fields in original sources. Do not inspect wf_moderators or the first moderator pass."
    if ttype == "MODERATORS_ADJ":
        packet["moderator_passes"]=rows(con,"SELECT pass,payload FROM wf_moderator_passes WHERE study_id=?",(study,))
    if ttype == "DESIGN" and str(task.get("scope_ref") or "").startswith("human-fix-"):
        packet["human_recheck_notes"]=rows(con,"SELECT a.contrast_id,a.verdict,a.notes FROM wf_contrast_audit a JOIN an_contrasts c USING(contrast_id) WHERE c.study_id=? AND a.verdict<>'CORRECT'",(study,))
    if ttype == "DESIGN":
        packet["design_gap_reports"] = rows(con, "SELECT * FROM wf_review WHERE study_id=? "
                                                 "AND kind='DESIGN_GAP' AND status='OPEN' ORDER BY review_id", (study,))
    if ttype == "PATCH_REVIEW":
        packet["patches"] = reviewable_patches(con, study)
    if ttype == "QA_REVIEW":
        packet["qa_issues"] = rows(con,"SELECT * FROM wf_validation WHERE status='OPEN' AND CAST(issue_id AS TEXT)=?",(str(task.get("scope_ref") or "").removeprefix("issue-"),))
    if ttype == "DEDUP":
        packet["cluster"] = json.loads(task["scope_ref"].split("::", 1)[1]) if "::" in task["scope_ref"] else []
        packet["cluster_studies"] = [study_dump(con, cfg, s, light=True).get("study") for s in packet["cluster"]]
    if ttype == "AUDIT":
        items = rows(con, "SELECT * FROM an_target_values WHERE study_id=? ORDER BY tv_id", (study,))
        if task["scope_ref"].startswith("audit:"):
            ids = {int(x) for x in task["scope_ref"].split(":", 1)[1].split(",") if x.strip()}
            items = [i for i in items if i["tv_id"] in ids]
        packet["audit_items"] = items
        packet["independence_rule"] = ("Audit blind: re-read each value at its locator in the ORIGINAL source; do not "
                                       "open wf_values, outbox files or other agents' reasoning.")
    (pdir / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return pdir / "packet.json"


def figure_candidates(cfg, study_dir: Optional[Path], slot: Dict[str, Any]) -> List[str]:
    """Likely image files for a figure slot: FIG_### folders / figure_###.png in the study folder and in
    figures_root/<source_file_id>/ (layout used by the figure export)."""
    fid = str(slot.get("figure_item_id") or "")
    m = re.search(r"(?:FIG_?|figure_)(\d+)", fid, re.I)
    if not m:
        return []
    num = int(m.group(1))
    pats = [f"**/FIG_{num:03d}/*.png", f"**/figure_{num:03d}.png", f"**/FIG_{num}/*.png", f"**/figure_{num}.png"]
    bases = [b for b in (study_dir,) if b and b.exists()]
    fr = cfg.p("figures_root")
    if fr and slot.get("source_file_id") and (fr / str(slot["source_file_id"])).exists():
        bases.append(fr / str(slot["source_file_id"]))
    out: List[str] = []
    for b in bases:
        for f in _glob_many(b, pats):
            if str(f) not in out:
                out.append(str(f))
    return out[:20]


def conflicts_for(con, study_id: str) -> List[Dict[str, Any]]:
    recs = rows(con, "SELECT * FROM wf_reconciliation WHERE study_id=? AND status='OPEN' ORDER BY rec_id", (study_id,))
    out = []
    for r in recs:
        item = dict(r)
        for side in ("a", "b"):
            vid = r[f"value_id_{side}"]
            item[f"value_{side}"] = (rows(con, "SELECT * FROM wf_values WHERE value_id=?", (vid,)) or [None])[0] if vid else None
        out.append(item)
    return out
