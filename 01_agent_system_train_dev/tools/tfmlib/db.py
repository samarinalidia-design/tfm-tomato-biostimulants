from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import __version__

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema" / "wf_schema.sql"


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def new_run_id(prefix: str = "R") -> str:
    return f"{prefix}-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def sha256_file(path: Path, n: Optional[int] = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    d = h.hexdigest()
    return d[:n] if n else d


def sha256_text(text: str, n: Optional[int] = None) -> str:
    d = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return d[:n] if n else d


def q(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if readonly:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=60)
        con.execute("PRAGMA query_only = ON")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(path), timeout=60, isolation_level=None)
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 60000")
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextlib.contextmanager
def tx(con: sqlite3.Connection):
    """Write transaction that takes the write lock immediately (safe with parallel agents)."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def init_schema(con: sqlite3.Connection) -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # v1 had UNIQUE(record_key) across studies; it cannot safely be repaired after
    # collisions have overwritten data. Start v2 from the immutable Excel snapshot.
    if table_exists(con, "an_target_values"):
        old = con.execute("SELECT sql FROM sqlite_master WHERE name='an_target_values'").fetchone()[0]
        if "record_key        TEXT NOT NULL UNIQUE" in old or "receipt_id" not in old:
            raise RuntimeError("v1 database detected. Use a new v2 directory and re-import the baseline; do not copy v1 db/")
        if "dispersion_basis" not in old:
            raise RuntimeError("v2.0 database requires a controlled migration/reverification for the v2.1 error-bar policy; do not overwrite the existing database")
    con.executescript(sql)
    set_meta(con, "code_version", __version__)
    if get_meta(con, "created_at") is None:
        set_meta(con, "created_at", now())


def set_meta(con: sqlite3.Connection, key: str, value: Any) -> None:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    con.execute("INSERT INTO wf_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def get_meta(con: sqlite3.Connection, key: str) -> Optional[str]:
    row = con.execute("SELECT value FROM wf_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
                       (name,)).fetchone() is not None


def columns(con: sqlite3.Connection, table: str) -> List[str]:
    if not table_exists(con, table):
        return []
    return [r[1] for r in con.execute(f"PRAGMA table_info({q(table)})")]


def rows(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    return [dict(r) for r in con.execute(sql, params)]


def changelog(con: sqlite3.Connection, run_id: Optional[str], entity: str, entity_id: Any,
              action: str, detail: Any = None) -> None:
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False, default=str)
    con.execute("INSERT INTO wf_changelog(ts, run_id, entity, entity_id, action, detail) "
                "VALUES (?,?,?,?,?,?)", (now(), run_id, entity, str(entity_id), action, detail))


def add_issue(con: sqlite3.Connection, rule_id: str, severity: str, study_id: Optional[str],
              entity: str, entity_id: Any, message: str, run_id: Optional[str] = None) -> None:
    """Insert a validation issue unless an identical OPEN issue already exists."""
    exists = con.execute(
        "SELECT 1 FROM wf_validation WHERE rule_id=? AND COALESCE(study_id,'')=COALESCE(?, '') "
        "AND entity=? AND entity_id=? AND status='OPEN' AND message=?",
        (rule_id, study_id, entity, str(entity_id), message)).fetchone()
    if exists:
        return
    con.execute("INSERT INTO wf_validation(rule_id, severity, study_id, entity, entity_id, message, "
                "status, run_id, created_at) VALUES (?,?,?,?,?,?, 'OPEN', ?, ?)",
                (rule_id, severity, study_id, entity, str(entity_id), message, run_id, now()))


def add_review(con: sqlite3.Connection, study_id: Optional[str], kind: str, ref: str, question: str,
               options: Iterable[str] = (), evidence: str = "", priority: int = 2) -> None:
    con.execute("INSERT OR IGNORE INTO wf_review(study_id, kind, ref, question, options, evidence, "
                "priority, status, created_at) VALUES (?,?,?,?,?,?,?, 'OPEN', ?)",
                (study_id, kind, ref, question, json.dumps(list(options), ensure_ascii=False),
                 evidence, priority, now()))


# ------------------------------------------------------------------ columns
class ColumnResolver:
    """Resolve canonical field names to actual workbook headers (config/column_map.yaml)."""

    def __init__(self, con: sqlite3.Connection, column_map: Dict[str, Dict[str, List[str]]]):
        self.con = con
        self.map = column_map or {}
        self._cache: Dict[str, List[str]] = {}
        self.misses: List[str] = []
        self.fuzzy: List[str] = []

    def cols(self, table: str) -> List[str]:
        if table not in self._cache:
            self._cache[table] = columns(self.con, table)
        return self._cache[table]

    def get(self, table: str, field: str, required: bool = False) -> Optional[str]:
        cols = self.cols(table)
        if not cols:
            if required:
                raise KeyError(f"table '{table}' not found in database")
            return None
        lower = {c.lower(): c for c in cols}
        cands = (self.map.get(table) or {}).get(field) or [field]
        for c in cands:
            if c in cols:
                return c
            if c.lower() in lower:
                return lower[c.lower()]
        # unique prefix match on the first candidate (e.g. 'measu' -> measurement_id)
        stem = re.sub(r"_?(id|name|raw)$", "", cands[0].lower())
        pref = [c for c in cols if c.lower().startswith(stem)]
        if len(pref) == 1:
            self.fuzzy.append(f"{table}.{field} -> {pref[0]} (prefix match)")
            return pref[0]
        msg = f"{table}.{field}: none of {cands} found"
        if msg not in self.misses:
            self.misses.append(msg)
        if required:
            raise KeyError(msg + f"; available: {cols}")
        return None
