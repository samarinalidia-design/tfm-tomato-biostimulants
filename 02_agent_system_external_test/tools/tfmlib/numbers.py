"""Numeric parsing for table cells and the deterministic "number appears in source" check.

Handles decimal commas ("8,70 a"), thousands separators, unicode minus, ± / +/- /
parentheses dispersion and trailing significance letters — the cases that broke
`numeric_cell_count` in the V4.3 source layer.
"""
from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Optional, Set

_MINUS = {"−": "-", "–": "-", "—": "-", "﹣": "-", "－": "-"}
_SPACES = {" ": " ", " ": " ", " ": " ", " ": " "}
TOKEN_RE = re.compile(r"(?<![\w])-?\d+(?:[.,]\d+)*(?![\d])")
PM_RE = re.compile(r"(±|\+/-|\+-|\+\s*/\s*-|±)")


def clean(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    for k, v in _MINUS.items():
        s = s.replace(k, v)
    for k, v in _SPACES.items():
        s = s.replace(k, v)
    return s


def interpretations(token: str) -> Set[float]:
    """All plausible float readings of a numeric token (decimal comma vs thousands separators)."""
    t = clean(token).strip().replace(" ", "")
    if not t:
        return set()
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    out: Set[float] = set()
    if re.fullmatch(r"\d+", t):
        out.add(float(t))
    elif re.fullmatch(r"\d+[.,]\d+", t):
        out.add(float(t.replace(",", ".")))                       # 2,45 / 2.45
        if re.fullmatch(r"\d{1,3}[.,]\d{3}", t):                   # 1,234 could be thousands
            out.add(float(t.replace(",", "").replace(".", "")))
    else:
        # several separators: the last one is the decimal separator, others are thousands
        m = re.fullmatch(r"(\d{1,3}(?:([.,])\d{3})+)(?:([.,])(\d+))?", t)
        if m:
            int_part = re.sub(r"[.,]", "", m.group(1))
            if m.group(4) is not None and m.group(3) != m.group(2):
                out.add(float(f"{int_part}.{m.group(4)}"))
            elif m.group(4) is None:
                out.add(float(int_part))
        else:
            # fall back: last separator = decimal
            idx = max(t.rfind("."), t.rfind(","))
            if idx > 0:
                try:
                    out.add(float(re.sub(r"[.,]", "", t[:idx]) + "." + t[idx + 1:]))
                except ValueError:
                    pass
    return {(-v if neg else v) for v in out}


def parse_number(token: str) -> Optional[float]:
    vals = interpretations(token)
    if not vals:
        return None
    # prefer the decimal-comma/decimal-point reading (smallest magnitude ambiguity)
    t = clean(token).strip()
    if re.fullmatch(r"-?\d+[.,]\d+", t.replace(" ", "")):
        return float(t.replace(" ", "").replace(",", "."))
    return sorted(vals, key=abs)[0]


def tokens(text: str) -> List[str]:
    return TOKEN_RE.findall(clean(text))


def parse_cell(verbatim: str) -> Dict[str, object]:
    """Split a printed cell like '2,45 ± 0,12 b' into mean, dispersion and letters."""
    s = clean(verbatim).strip()
    res: Dict[str, object] = {"mean": None, "disp": None, "letters": None, "pm": False, "paren": False}
    if not s:
        return res
    pm = PM_RE.search(s)
    if pm:
        left, right = s[:pm.start()], s[pm.end():]
        lt, rt = tokens(left), tokens(right)
        res["mean"] = parse_number(lt[-1]) if lt else None
        res["disp"] = parse_number(rt[0]) if rt else None
        res["pm"] = True
        tail = right
    else:
        m = re.search(r"(-?\d+(?:[.,]\d+)*)\s*\(\s*(-?\d+(?:[.,]\d+)*)\s*\)", s)
        if m:
            res["mean"], res["disp"], res["paren"] = parse_number(m.group(1)), parse_number(m.group(2)), True
            tail = s[m.end():]
        else:
            tk = tokens(s)
            res["mean"] = parse_number(tk[0]) if tk else None
            tail = s[s.find(tk[0]) + len(tk[0]):] if tk else ""
    # significance letters = whatever follows the last number, if it is only letters a-h / A-H
    tk = list(TOKEN_RE.finditer(clean(tail)))
    rest = clean(tail)[tk[-1].end():] if tk else clean(tail)
    rest = rest.strip()
    if rest and re.fullmatch(r"[a-hA-H\s*†‡,]+", rest) and re.search(r"[a-hA-H]", rest):
        res["letters"] = re.sub(r"[\s*†‡,]+", " ", rest).strip()
    return res


def close(a: float, b: float, rel: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)


def value_in_tokens(value: float, toks: Iterable[str]) -> bool:
    for t in toks:
        for v in interpretations(t):
            if close(v, value):
                return True
    return False


def mean_in_verbatim(mean: float, verbatim: str) -> bool:
    if verbatim is None:
        return False
    return value_in_tokens(mean, tokens(verbatim))


def value_in_texts(value: float, texts: Iterable[str]) -> bool:
    for txt in texts:
        if txt and value_in_tokens(value, tokens(txt)):
            return True
    return False


def decimals(token: str) -> int:
    t = clean(token)
    m = re.search(r"[.,](\d+)$", t)
    return len(m.group(1)) if m else 0
