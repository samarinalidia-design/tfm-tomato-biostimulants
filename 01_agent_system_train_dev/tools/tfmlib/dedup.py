"""Candidate duplicate / companion publications (preprints, conference versions, same-lab series)."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Dict, List, Set, Tuple

from .db import ColumnResolver, q, rows, tx
from .tasks import create_task

PREPRINT_DOI = ("10.21203/", "10.1101/", "10.20944/", "10.22541/", "10.31219/", "10.2139/ssrn")
WEAK_TYPES = ("preprint", "posted-content", "conference-paper", "proceedings-article")
STOP = set(("a an the of on in to and for by with under from as at its their tomato tomatoes plant plants solanum "
            "lycopersicum lycopersicon esculentum mill l stress stresses effect effects improves improve improving "
            "improved enhance enhances enhanced enhancing via using use role roles growth yield yields quality fruit "
            "fruits salt salinity saline nacl drought water deficit heat cold chilling temperature high low tolerance "
            "tolerant resistance response responses application applied foliar seedling seedlings physiological "
            "biochemical antioxidant antioxidants mitigates mitigate mitigation mitigating alleviates alleviate "
            "alleviation alleviating induced inducing conditions condition greenhouse field soil cultivars cultivar "
            "biostimulant biostimulants extract extracts treatment treatments abiotic biotic based new novel study "
            "evaluation assessment performance performances mechanisms mechanism").split())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _surnames(authors: str) -> Set[str]:
    out = set()
    for a in re.split(r";|\band\b", authors or ""):
        a = a.strip()
        if not a:
            continue
        sur = a.split(",")[0] if "," in a else a.split()[-1]
        sur = _norm(sur).strip()
        if len(sur) > 1:
            out.add(sur)
    return out


def _title_tokens(t: str) -> Set[str]:
    return {w for w in _norm(t).split() if w not in STOP and len(w) > 2}


def _jac(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def candidates(con, cfg, author_jac: float = 0.34, title_jac: float = 0.6, year_gap: int = 4) -> List[Dict]:
    """Candidate pairs. Strong evidence = shared authors; a title match alone is not enough
    (titles in this corpus share many domain words), except for preprint/conference versions."""
    cr = ColumnResolver(con, cfg.column_map)
    f = {k: cr.get("studies", k) for k in ("study_id", "doi", "title", "authors", "year", "publication_type")}
    sel = ", ".join(f"{q(v)} AS {k}" if v else f"NULL AS {k}" for k, v in f.items())
    st = rows(con, f"SELECT {sel} FROM studies")
    meta = []
    for s in st:
        try:
            y = int(float(s["year"])) if s["year"] not in (None, "") else None
        except (TypeError, ValueError):
            y = None
        meta.append({**s, "study_id": str(s["study_id"]), "y": y, "au": _surnames(str(s["authors"] or "")),
                     "ti": _title_tokens(str(s["title"] or "")),
                     "weak": str(s["doi"] or "").lower().startswith(PREPRINT_DOI) or
                             str(s["publication_type"] or "").lower() in WEAK_TYPES})
    pairs = []
    for i in range(len(meta)):
        for j in range(i + 1, len(meta)):
            a, b = meta[i], meta[j]
            if a["y"] and b["y"] and abs(a["y"] - b["y"]) > year_gap:
                continue
            ja, jt = _jac(a["au"], b["au"]), _jac(a["ti"], b["ti"])
            strong = ja >= author_jac
            title_twin = jt >= title_jac and ja > 0
            version = (a["weak"] or b["weak"]) and (ja >= 0.2 or jt >= 0.5)
            if strong or title_twin or version:
                why = [f"authors J={ja:.2f}", f"title J={jt:.2f}"] + (["preprint/conference version"] if version else [])
                pairs.append({"a": a["study_id"], "b": b["study_id"], "why": "; ".join(why),
                              "score": ja + jt + (1 if version else 0)})
    return pairs


def clusters(pairs: List[Dict]) -> List[List[str]]:
    parent: Dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        ra, rb = find(p["a"]), find(p["b"])
        if ra != rb:
            parent[ra] = rb
    groups: Dict[str, List[str]] = {}
    for x in parent:
        groups.setdefault(find(x), []).append(x)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def seed_dedup_tasks(con, cfg, max_cluster: int = 6) -> Dict[str, int]:
    """One DEDUP task per small connected cluster; clusters larger than max_cluster (long same-lab
    series) are split into their individual candidate pairs so each comparison stays focused."""
    pairs = candidates(con, cfg)
    cl = clusters(pairs)
    n_tasks, split = 0, 0
    with tx(con):
        for g in cl:
            if len(g) <= max_cluster:
                create_task(con, cfg, g[0], "DEDUP", "cluster::" + json.dumps(g), priority=1)
                n_tasks += 1
            else:
                split += 1
                members = set(g)
                for p in pairs:
                    if p["a"] in members and p["b"] in members:
                        pr = sorted([p["a"], p["b"]])
                        create_task(con, cfg, pr[0], "DEDUP", "cluster::" + json.dumps(pr), priority=1)
                        n_tasks += 1
    return {"candidate_pairs": len(pairs), "clusters": len(cl), "large_clusters_split": split, "dedup_tasks": n_tasks}
