"""Shared paths and helpers for SynerPlant Yield V2 (read-only access to V1 sources)."""
from __future__ import annotations
import hashlib, json, sqlite3, datetime as dt
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
ROOT = V2.parent
V1_SYSTEM = ROOT / "TFM_AGENT_SYSTEM_v2_2"
V1_FREEZE = V1_SYSTEM / "exports" / "DATA_FREEZE_20261113T112939135807Z"
_V1_ML_CANDIDATES = [ROOT.parent / "SynerPlant_Local_ML_Starter" / "SynerPlant_Local_ML",          # moved 2026-11-18
                     Path(r"C:\Users\lenovo\Desktop\SynerPlant_Local_ML_Starter\SynerPlant_Local_ML")]
V1_ML = next((p for p in _V1_ML_CANDIDATES if p.exists()), _V1_ML_CANDIDATES[0])
CORPUS = Path("G:/Мой диск/TFM_CORPUS_NORMALIZED")
DB = V2 / "db" / "TFM_V2_WORKING.sqlite"
AUDIT = V2 / "audit"
OUT = V2 / "outputs"
for p in (AUDIT, OUT):
    p.mkdir(exist_ok=True)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def connect(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def resolve_source(file_name: str) -> Path | None:
    for sub in ("01_fulltext", "02_supplements"):
        p = CORPUS / sub / file_name
        if p.exists():
            return p
    hits = list(CORPUS.glob(f"0*/**/{file_name}"))
    return hits[0] if hits else None


def pdf_text(path: Path) -> list[str]:
    import fitz
    with fitz.open(path) as doc:
        return [pg.get_text() for pg in doc]


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
