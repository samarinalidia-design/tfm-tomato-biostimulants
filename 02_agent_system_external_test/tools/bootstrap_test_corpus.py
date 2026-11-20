#!/usr/bin/env python3
"""One-time bootstrap of the EXTERNAL_TEST corpus (publications first online 2024-2026).

Run by the user (not by agents) BEFORE `tfm.py init/import-xlsx`. The original folder is only read.

Phase 1 (default):  propose a file -> study mapping and write
                    inputs/file_mapping_FOR_CONFIRMATION.xlsx + work/bootstrap/bootstrap_report.json
Phase 2 (--finalize): after every row of the mapping workbook is confirmed (approved=yes, or
                    study_id changed / IGNORE), build the read-only normalized corpus copy, the frozen
                    scope + source manifests, the TRAIN_DEV identity list, the baseline workbook and the
                    path/scope settings.

Matching is deterministic: DOI printed on the first pages of a PDF, then exact normalized title, then
publisher file-name rules (ScienceDirect PII, MDPI article id, Springer MOESM article number). Files with
no rule (e.g. Frontiers 'Data Sheet 1.docx') get a PROPOSED study from the download time next to a
matched PDF and must be confirmed by the user. Nothing is silently attached to a study.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tfmlib.mode import norm_doi, norm_title  # noqa: E402

DEFAULT_PAPERS = Path(r"C:\Users\lenovo\Desktop\master's\2024-2026 papers")
DEFAULT_REGISTRY_NAME = "tomato_biostimulants_stress_2024_2026_registry.xlsx"
DEFAULT_FREEZE = Path(r"C:\Users\lenovo\Desktop\master's\TFM_A399_Agent_System_v2_2_2026-10-19"
                      r"\TFM_AGENT_SYSTEM_v2_2\exports\DATA_FREEZE_20261113T112939135807Z")
DEFAULT_CORPUS = Path(r"C:\Users\lenovo\Desktop\master's\TFM_TEST_2024_2026_CORPUS")
DEFAULT_FREEZE_FILE = Path(r"C:\Users\lenovo\Desktop\SynerPlant_Local_ML_Starter\SynerPlant_Local_ML"
                           r"\outputs\MODEL_FREEZE.json")
MAPPING_XLSX = ROOT / "inputs" / "file_mapping_FOR_CONFIRMATION.xlsx"
REPORT = ROOT / "work" / "bootstrap" / "bootstrap_report.json"
DOI_RX = re.compile(r"10\.\d{4,9}/[^\s\"<>()\[\]]+", re.I)
MIME = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel", ".tif": "image/tiff", ".tiff": "image/tiff", ".csv": "text/csv"}
NEAR_SECONDS = 15 * 60


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------- inputs
def read_registry(path: Path):
    import pandas as pd
    df = pd.read_excel(path, sheet_name=0, dtype=str).fillna("")
    cols = {c: c.strip() for c in df.columns}
    df = df.rename(columns=cols)
    pick = {"no": "№", "year": "Год онлайн / издания", "stress_type": "Тип стресса", "stress_factor": "Стресс-фактор",
            "agent": "Биостимулятор / агент", "title": "Точное название статьи (EN)", "doi": "DOI",
            "relevance": "Соответствие", "note": "Пояснение / ограничения", "url": "Ссылка на источник"}
    missing = [v for v in pick.values() if v not in df.columns]
    if missing:
        raise SystemExit(f"registry columns missing: {missing}")
    recs = []
    for r in df.to_dict("records"):
        if not str(r[pick["no"]]).strip():
            continue
        no = int(float(r[pick["no"]]))
        rec = {k: str(r[v]).strip() for k, v in pick.items()}
        rec["no"] = no
        rec["study_id"] = f"T{no:03d}"
        rec["doi_norm"] = norm_doi(rec["doi"])
        rec["title_norm"] = norm_title(rec["title"])
        recs.append(rec)
    ids = [r["study_id"] for r in recs]
    if len(ids) != len(set(ids)):
        raise SystemExit("registry numbers are not unique")
    return recs


def pdf_text(p: Path, pages=2) -> str:
    import fitz
    try:
        with fitz.open(p) as d:
            return "\n".join(d[i].get_text() for i in range(min(pages, len(d))))
    except Exception:
        return ""


def pdf_title(p: Path) -> str:
    import fitz
    try:
        with fitz.open(p) as d:
            t = (d.metadata or {}).get("title") or ""
    except Exception:
        t = ""
    return t.strip() if len(t.strip()) > 15 else p.stem.replace("-", " ").replace("_", " ")


def docx_text(p: Path) -> str:
    try:
        from docx import Document
        d = Document(p)
        return "\n".join(x.text for x in d.paragraphs[:200])
    except Exception:
        return ""


# ------------------------------------------------------------------- matching
def match_pdf(text: str, recs):
    """(study_id, rule) from the article's own DOI/title on its first pages."""
    t_norm = norm_title(text)
    dois = {norm_doi(m.group(0)) for m in DOI_RX.finditer(text)}
    by_doi = [r for r in recs if r["doi_norm"] and any(d == r["doi_norm"] or d.startswith(r["doi_norm"]) for d in dois)]
    by_title = [r for r in recs if len(r["title_norm"]) >= 25 and r["title_norm"][:80] in t_norm]
    both = [r for r in by_doi if r in by_title]
    for cand, rule in [(both, "DOI_AND_TITLE"), (by_title, "TITLE"), (by_doi, "DOI")]:
        if len(cand) == 1:
            return cand[0]["study_id"], rule
    if by_doi or by_title:
        return None, "AMBIGUOUS:" + ",".join(sorted({r["study_id"] for r in by_doi + by_title}))
    return None, "NO_DOI_OR_TITLE"


def springer_study(name: str, recs):
    m = re.match(r"(\d{5})_(\d{4})_(\d+)_MOESM", name)
    if not m:
        return None
    code, yy, num = m.group(1), m.group(2)[2:], int(m.group(3))
    rx = re.compile(rf"s{code}-0?{yy}-0*{num}-", re.I)
    hits = [r for r in recs if rx.search(r["doi_norm"])]
    return hits[0]["study_id"] if len(hits) == 1 else None


def pii_of(name: str):
    m = re.search(r"1-s2\.0-(S[0-9X]+)-", name, re.I)
    return m.group(1).upper() if m else None


def mdpi_key(name: str):
    m = re.match(r"([a-z]+)-(\d+)-(\d+)", name.lower())
    return m.group(0) if m else None


def propose(papers: Path, recs):
    files = sorted(p for p in papers.iterdir() if p.is_file() and p.name != DEFAULT_REGISTRY_NAME
                   and not p.name.startswith("~$"))
    rows, pdf_owner = [], {}
    pii_owner, mdpi_owner = {}, {}
    # 1) every PDF: the article's own DOI/title
    for p in files:
        if p.suffix.lower() != ".pdf":
            continue
        text = pdf_text(p)
        sid, rule = match_pdf(text, recs)
        own = [norm_doi(m.group(0)) for m in DOI_RX.finditer(text[:3000])]
        rec = {"file": p.name, "kind": "PDF", "study_id": sid or "", "rule": rule,
               "role": "FULLTEXT" if sid else "", "mtime": p.stat().st_mtime,
               "detected_doi": own[0] if own else "", "detected_title": pdf_title(p)}
        if not sid and own:
            rec.update(study_id="NEW", rule="DOI_NOT_IN_REGISTRY:" + own[0], role="FULLTEXT", status="NOT_IN_REGISTRY")
        rows.append(rec)
        if sid:
            pdf_owner.setdefault(sid, []).append(p.name)
            if pii_of(p.name):
                pii_owner[pii_of(p.name)] = sid
            if mdpi_key(p.name):
                mdpi_owner[mdpi_key(p.name)] = sid
    # full texts outside the registry get stable new IDs (T101+, by file name) so supplements can follow them
    new = sorted((r for r in rows if r["study_id"] == "NEW"), key=lambda r: r["file"].lower())
    for k, r in enumerate(new, start=101):
        r["study_id"] = f"T{k:03d}"
        pdf_owner.setdefault(r["study_id"], []).append(r["file"])
        if pii_of(r["file"]):
            pii_owner[pii_of(r["file"])] = r["study_id"]
        if mdpi_key(r["file"]):
            mdpi_owner[mdpi_key(r["file"])] = r["study_id"]
    # 2) non-PDF files and zips: publisher rules, then download-time proposal
    matched_pdfs = sorted((r for r in rows if r["study_id"]), key=lambda r: r["mtime"])
    for p in files:
        if p.suffix.lower() == ".pdf":
            continue
        sid, rule = None, ""
        names = [p.name]
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                names += [i.filename for i in z.infolist() if not i.is_dir()]
        for n in names:
            if springer_study(n, recs):
                sid, rule = springer_study(n, recs), "SPRINGER_MOESM_ARTICLE_NUMBER"
                break
            if pii_of(n) and pii_of(n) in pii_owner:
                sid, rule = pii_owner[pii_of(n)], "SCIENCEDIRECT_PII"
                break
            if mdpi_key(n) and mdpi_key(n) in mdpi_owner:
                sid, rule = mdpi_owner[mdpi_key(n)], "MDPI_ARTICLE_ID"
                break
        if not sid and p.suffix.lower() == ".docx":
            s2, r2 = match_pdf(docx_text(p), recs)
            if s2:
                sid, rule = s2, "DOCX_" + r2
        status = "AUTO"
        if not sid:
            t = p.stat().st_mtime
            before = [r for r in matched_pdfs if 0 <= t - r["mtime"] <= NEAR_SECONDS]
            if before:
                sid, rule, status = before[-1]["study_id"], "PROPOSED_DOWNLOAD_TIME_AFTER:" + before[-1]["file"], "PROPOSED"
            else:
                rule, status = "NO_RULE", "UNMATCHED"
        rows.append({"file": p.name, "kind": "ZIP" if p.suffix.lower() == ".zip" else "SUPPLEMENT",
                     "study_id": sid or "", "rule": rule, "role": "SUPPLEMENT", "mtime": p.stat().st_mtime,
                     "status": status})
    for r in rows:
        r.setdefault("status", "AUTO" if r["study_id"] else "UNMATCHED")
        r.setdefault("detected_doi", "")
        r.setdefault("detected_title", "")
        if r["kind"] == "PDF" and r["study_id"] and len(pdf_owner.get(r["study_id"], [])) > 1:
            if not r["rule"].startswith("DOI_AND_TITLE"):
                r["role"] = "SUPPLEMENT"  # the article itself prints both its DOI and title
            r["status"], r["rule"] = "PROPOSED", r["rule"] + ";SEVERAL_PDFS_SAME_STUDY"
    return rows


# ------------------------------------------------------------- mapping workbook
COLS = ["file", "kind", "proposed_study_id", "proposed_role", "rule", "status", "registry_title",
        "detected_doi", "detected_title", "approved", "study_id", "role", "note"]


def write_mapping(rows, recs, old=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    title = {r["study_id"]: r["title"] for r in recs}
    old = old or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "mapping"
    ws.append(COLS)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
    yellow, green = PatternFill("solid", fgColor="FFF2CC"), PatternFill("solid", fgColor="E2EFDA")
    for r in sorted(rows, key=lambda x: (x["status"] == "AUTO", x["proposed_study_id"] if "proposed_study_id" in x else x["study_id"], x["file"])):
        sid = r["study_id"]
        prev = old.get(r["file"], {})
        # keep only real user input: an approval, or a study/role changed away from the earlier proposal
        touched = prev and (str(prev.get("approved", "")).strip() or
                            str(prev.get("study_id", "")) != str(prev.get("proposed_study_id", "")) or
                            str(prev.get("role", "")) != str(prev.get("proposed_role", "")) or
                            str(prev.get("note", "")).strip())
        if not touched or str(prev.get("proposed_study_id", "")) != str(sid):
            prev = {} if not touched or str(prev.get("study_id", "")) == str(prev.get("proposed_study_id", "")) else prev
        auto = r["status"] == "AUTO"
        ws.append([r["file"], r["kind"], sid, r["role"], r["rule"], r["status"], title.get(sid, ""),
                   r["detected_doi"], r["detected_title"],
                   prev.get("approved", "yes" if auto else ""), prev.get("study_id", sid), prev.get("role", r["role"]),
                   prev.get("note", "")])
        i = ws.max_row
        for j in range(1, len(COLS) + 1):
            ws.cell(i, j).fill = green if COLS[j - 1] in ("approved", "study_id", "role", "note") else (
                yellow if not auto else PatternFill())
    dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"J2:J{max(ws.max_row, 2)}")
    for col, w in zip("ABCDEFGHIJKLM", (48, 11, 12, 12, 46, 14, 50, 26, 50, 9, 10, 12, 40)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    reg = wb.create_sheet("registry")
    reg.append(["study_id", "no", "year", "relevance", "doi", "title", "fulltext_files"])
    owned = {}
    for r in rows:
        if r["kind"] == "PDF" and r["study_id"]:
            owned.setdefault(r["study_id"], []).append(r["file"])
    for r in recs:
        reg.append([r["study_id"], r["no"], r["year"], r["relevance"], r["doi"], r["title"],
                    "; ".join(owned.get(r["study_id"], [])) or "NO FULLTEXT FOUND"])
    for r in rows:
        if r.get("status") == "NOT_IN_REGISTRY":
            reg.append([r["study_id"], "", "", "NOT_IN_REGISTRY", r["detected_doi"], r["detected_title"], r["file"]])
    ins = wb.create_sheet("instructions")
    for line in [
        "Confirm the file -> study mapping of the 2024-2026 TEST corpus.",
        "Green columns are yours. approved = yes accepts the row; edit study_id (T###) or role (FULLTEXT/SUPPLEMENT) if wrong.",
        "Write study_id = IGNORE for a file that belongs to no registry study (it is then not part of the TEST corpus).",
        "NOT_IN_REGISTRY: a full text whose DOI is not in the registry (outside the prespecified search). It has a new ID T101+; approve it to add it as a TEST record (check detected_doi/detected_title), or write IGNORE.",
        "Yellow rows were matched by download time or are ambiguous/unmatched: check them in the file itself.",
        "Sheet 'registry' lists registry records without a full text: add the PDF to the papers folder or accept that the record is not part of the TEST corpus.",
        "Save, close Excel and run:  .venv\\Scripts\\python tools\\bootstrap_test_corpus.py --finalize",
    ]:
        ins.append([line])
    ins.column_dimensions["A"].width = 140
    MAPPING_XLSX.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(MAPPING_XLSX)
    except PermissionError:
        raise SystemExit(f"close {MAPPING_XLSX.name} in Excel and run again")


def read_mapping():
    import pandas as pd
    if not MAPPING_XLSX.exists():
        return {}
    df = pd.read_excel(MAPPING_XLSX, sheet_name="mapping", dtype=str).fillna("")
    return {r["file"]: r for r in df.to_dict("records")}


# --------------------------------------------------------------------- finalize
def safe(name: str, limit: int = 50) -> str:
    """Short ASCII file name (Windows paths stay well under 260 characters); the origin is kept in the manifest."""
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_.")[:limit] or "file"
    return stem + re.sub(r"[^a-z0-9.]", "", suffix)


def finalize(papers: Path, recs, corpus: Path, freeze_dir: Path, freeze_file: Path, today: str):
    import pandas as pd
    mapping = read_mapping()
    if not mapping:
        raise SystemExit("run phase 1 first (no mapping workbook)")
    pending = [f for f, r in mapping.items() if str(r["approved"]).strip().lower() not in ("yes", "да", "approved")]
    if pending:
        raise SystemExit(f"{len(pending)} mapping rows not approved yet, e.g. {pending[:5]}")
    # full texts outside the registry that the user approved become new TEST records
    known = {r["study_id"] for r in recs}
    for f, r in sorted(mapping.items()):
        sid = r["study_id"]
        if re.fullmatch(r"T1\d\d", sid) and sid not in known and r["role"].upper() == "FULLTEXT":
            recs.append({"no": int(sid[1:]), "study_id": sid, "year": "", "stress_type": "", "stress_factor": "",
                         "agent": "", "title": r.get("detected_title", ""), "doi": r.get("detected_doi", ""),
                         "relevance": "NOT_IN_REGISTRY (added by author decision)", "note": f"full text {f}",
                         "url": "", "doi_norm": norm_doi(r.get("detected_doi", "")),
                         "title_norm": norm_title(r.get("detected_title", ""))})
            known.add(sid)
    by_id = {r["study_id"]: r for r in recs}
    bad = [f for f, r in mapping.items() if r["study_id"] not in by_id and r["study_id"].upper() != "IGNORE"]
    if bad:
        raise SystemExit(f"unknown study_id in mapping rows: {bad[:5]}")
    if (ROOT / "db" / "tfm_test_2024_2026.sqlite").exists():
        raise SystemExit("the TEST database already exists: the bootstrap is one-time; use a new project copy to change the corpus")
    if corpus.exists() and any(corpus.iterdir()):
        raise SystemExit(f"corpus folder {corpus} is not empty; remove it only if no database was built from it")
    # TRAIN_DEV identity (never part of TEST)
    st = pd.read_csv(freeze_dir / "db_studies.csv", dtype=str).fillna("")
    ident = ROOT / "manifests" / "train_dev_identity.csv"
    ident.parent.mkdir(parents=True, exist_ok=True)
    st[["study_id", "doi", "title", "year"]].to_csv(ident, index=False, encoding="utf-8")
    tr_doi = {norm_doi(x) for x in st["doi"]} - {""}
    tr_title = {norm_title(x) for x in st["title"]} - {""}
    # studies with a confirmed full text
    fulltext = {}
    for f, r in mapping.items():
        if r["study_id"].upper() != "IGNORE" and r["role"].upper() == "FULLTEXT":
            fulltext.setdefault(r["study_id"], []).append(f)
    scope, excluded = [], []
    for r in recs:
        if r["study_id"] not in fulltext:
            excluded.append({**r, "reason": "NO_FULLTEXT_IN_FOLDER"})
        elif (r["doi_norm"] and r["doi_norm"] in tr_doi) or (r["title_norm"] and r["title_norm"] in tr_title):
            excluded.append({**r, "reason": "TRAIN_DEV_OVERLAP (already inspected; can never be TEST)"})
        else:
            scope.append(r)
    keep = {r["study_id"] for r in scope}
    ft, su = corpus / "01_fulltext", corpus / "02_supplements"
    ft.mkdir(parents=True)
    su.mkdir(parents=True)
    sources = []
    for f, r in sorted(mapping.items()):
        sid = r["study_id"]
        if sid not in keep:
            continue
        src = papers / f
        role = r["role"].upper()
        if src.suffix.lower() == ".zip":
            with zipfile.ZipFile(src) as z:
                for i in z.infolist():
                    if i.is_dir():
                        continue
                    data = z.read(i)
                    name = f"{sid}__SUPPLEMENT__{safe(Path(f).stem, 20)}__{safe(Path(i.filename).name, 40)}"
                    (su / sid).mkdir(exist_ok=True)
                    (su / sid / name).write_bytes(data)
                    sources.append({"study_id": sid, "role": "SUPPLEMENT", "file": name, "sha": sha256_bytes(data),
                                    "origin": f"{f}!{i.filename}", "origin_sha256": sha256(src)})
            continue
        dest_dir = ft if role == "FULLTEXT" else su / sid
        dest_dir.mkdir(exist_ok=True)
        name = f"{sid}__{role}__{safe(f)}"
        shutil.copy2(src, dest_dir / name)
        digest = sha256(dest_dir / name)
        if digest != sha256(src):
            raise SystemExit(f"copy of {f} differs from the original")
        sources.append({"study_id": sid, "role": role, "file": name, "sha": digest, "origin": f, "origin_sha256": digest})
    for p in corpus.rglob("*"):
        if p.is_file():
            p.chmod(0o444)  # read-only copy
    # manifests
    with (ROOT / "manifests" / "scope_TEST.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["study_id", "registry_no", "doi", "title", "registry_year", "registry_relevance",
                                           "registry_stress_type", "registry_stress_factor", "registry_agent", "registry_note",
                                           "dataset_role"])
        w.writeheader()
        for r in scope:
            w.writerow({"study_id": r["study_id"], "registry_no": r["no"], "doi": r["doi"], "title": r["title"],
                        "registry_year": r["year"], "registry_relevance": r["relevance"],
                        "registry_stress_type": r["stress_type"], "registry_stress_factor": r["stress_factor"],
                        "registry_agent": r["agent"], "registry_note": r["note"], "dataset_role": "EXTERNAL_TEST"})
    with (ROOT / "manifests" / "source_manifest_TEST.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["study_id", "role", "active_file_id", "active_file_name", "mime_type",
                                           "sha256", "origin", "origin_sha256"])
        w.writeheader()
        for s in sources:
            w.writerow({"study_id": s["study_id"], "role": s["role"], "active_file_id": "F_" + s["sha"][:20],
                        "active_file_name": s["file"], "mime_type": MIME.get(Path(s["file"]).suffix.lower(), ""),
                        "sha256": s["sha"], "origin": s["origin"], "origin_sha256": s["origin_sha256"]})
    with (ROOT / "manifests" / "excluded_registry_records.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["study_id", "registry_no", "doi", "title", "reason"])
        w.writeheader()
        for r in excluded:
            w.writerow({"study_id": r["study_id"], "registry_no": r["no"], "doi": r["doi"], "title": r["title"],
                        "reason": r["reason"]})
    # baseline workbook: identity only; no registry interpretation is passed to the extraction agents
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "studies"
    ws.append(["study_id", "doi", "title", "authors", "year", "journal", "publication_type", "class_final",
               "dataset_role", "first_publication_date", "temporal_eligibility"])
    for r in scope:
        y = re.search(r"\d{4}", r["year"])
        ws.append([r["study_id"], r["doi"], r["title"], "", int(y.group(0)) if y else None, "", "", "",
                   "EXTERNAL_TEST", "", "TEMPORAL_REVIEW_REQUIRED"])
    fs = wb.create_sheet("files")
    fs.append(["file_key", "study_id", "role", "active_file_id", "active_file_name", "mime_type"])
    for s in sources:
        fs.append(["F_" + s["sha"][:20], s["study_id"], s["role"], "F_" + s["sha"][:20], s["file"],
                   MIME.get(Path(s["file"]).suffix.lower(), "")])
    empty = {"experiments": ["experiment_id", "study_id", "cultivar", "growth_stage", "system", "substrate", "season", "country"],
             "experiment_context": ["experiment_id", "study_id"], "genotype_context": ["experiment_id", "study_id"],
             "arms": ["arm_id", "experiment_id", "arm_label", "arm_role"],
             "stress_factors": ["stress_factor_id", "study_id", "experiment_id", "arm_id"],
             "arm_components": ["component_id", "arm_id", "experiment_id"],
             "measurements": ["measurement_id", "experiment_id", "arm_id", "outcome_raw", "outcome_std", "outcome_family",
                              "organ", "timepoint", "mean", "sd", "se", "n", "unit_raw", "unit", "provenance_id",
                              "verification_status"],
             "outcome_dictionary": ["outcome_std", "target_role"],
             "endpoint_measurement_context": ["measurement_id", "endpoint_role"],
             "provenance_qa": ["provenance_id", "entity_type", "entity_id", "source_file_id"],
             "study_relations": ["study_id_a", "study_id_b", "relation_type"]}
    for name, header in empty.items():
        wb.create_sheet(name).append(header)
    base = ROOT / "work" / "baseline" / "TFM_TEST_BASELINE.xlsx"
    base.parent.mkdir(parents=True, exist_ok=True)
    wb.save(base)
    # settings
    ids = sorted(r["study_id"] for r in scope)
    scope_sha = hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
    pipe = ROOT / "config" / "pipeline.yaml"
    text = pipe.read_text(encoding="utf-8")
    for key, val in [("expected_count", str(len(ids))), ("scope_sha256", f"'{scope_sha}'"),
                     ("temporal_window_end", f"'{today}'"), ("model_freeze_path", json.dumps(str(freeze_file)))]:
        text, n = re.subn(rf"(?m)^(\s+{key}:).*$", lambda m, v=val: f"{m.group(1)} {v}", text)
        if n != 1:
            raise SystemExit(f"pipeline.yaml: key {key} not found exactly once")
    digest = sha256(base)
    text, n = re.subn(r"(?m)^audited_baseline_sha256:.*$", lambda m: f"audited_baseline_sha256: ['{digest}']", text)
    if n != 1:
        raise SystemExit("pipeline.yaml: audited_baseline_sha256 not found")
    pipe.write_text(text, encoding="utf-8")
    import yaml
    (ROOT / "config" / "paths.yaml").write_text(yaml.safe_dump({
        "corpus_root": str(corpus), "workbook": str(base), "fulltext_root": str(ft), "supplements_root": str(su),
        "docling_root": "", "figures_root": "", "legacy_figure_json_root": "", "docling_map_csv": "",
        "docling_study_globs": ["{study_id}", "**/{study_id}"],
        "context": {"max_chars": 120000,
                    "keep_sections_regex": "(material|method|experimental|design|treatment|statistic|result|yield|harvest|biomass|table|figure|supplement)",
                    "drop_sections_regex": "(introduction|discussion|reference|bibliograph)"}},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    local = ROOT / ".claude" / "settings.local.json"
    rule = "//" + str(corpus).lstrip("/").replace("\\", "/") + "/**"
    local.write_text(json.dumps({"permissions": {"additionalDirectories": [str(corpus)], "deny": [f"Edit({rule})"]}},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scope_studies": len(scope), "excluded_registry_records": len(excluded),
            "excluded_by_reason": {k: sum(1 for e in excluded if e["reason"].startswith(k))
                                   for k in ("NO_FULLTEXT", "TRAIN_DEV_OVERLAP")},
            "source_files": len(sources), "scope_sha256": scope_sha, "baseline_workbook": str(base), "corpus": str(corpus)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--papers", type=Path, default=DEFAULT_PAPERS)
    ap.add_argument("--registry", type=Path)
    ap.add_argument("--train-dev-freeze", type=Path, default=DEFAULT_FREEZE)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--model-freeze", type=Path, default=DEFAULT_FREEZE_FILE)
    ap.add_argument("--window-end", default=None, help="last first-online date of the TEST window (default: registry cut date)")
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args(argv)
    registry = a.registry or a.papers / DEFAULT_REGISTRY_NAME
    recs = read_registry(registry)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not a.finalize:
        rows = propose(a.papers, recs)
        write_mapping(rows, recs, read_mapping())
        with_ft = {r["study_id"] for r in rows if r["kind"] == "PDF" and r["study_id"]}
        rep = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "phase": "PROPOSE",
               "registry_records": len(recs), "files": len(rows),
               "by_status": {s: sum(r["status"] == s for r in rows) for s in ("AUTO", "PROPOSED", "UNMATCHED")},
               "registry_records_with_fulltext": len(with_ft),
               "registry_records_without_fulltext": sorted(r["study_id"] for r in recs if r["study_id"] not in with_ft),
               "files_needing_confirmation": [{k: r[k] for k in ("file", "study_id", "rule", "status")}
                                              for r in rows if r["status"] != "AUTO"],
               "mapping_workbook": str(MAPPING_XLSX)}
        REPORT.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v for k, v in rep.items() if k != "files_needing_confirmation"}, indent=1, ensure_ascii=False))
        return rep
    window_end = a.window_end or "2026-11-03"
    res = finalize(a.papers, recs, a.corpus, a.train_dev_freeze, a.model_freeze, window_end)
    res["phase"] = "FINALIZE"
    REPORT.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return res


if __name__ == "__main__":
    main()
