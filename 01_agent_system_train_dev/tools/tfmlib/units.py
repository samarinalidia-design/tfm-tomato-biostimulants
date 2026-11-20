"""Unit normalisation for target endpoints.

lnRR is scale-free, so conversion is only needed to (a) check that S and SB arms
are on the same scale and (b) report harmonised values. Unknown units are kept
raw and flagged (never guessed).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

FEDDAN_M2 = 4200.83

_SUP = str.maketrans({"⁻": "-", "¹": "1", "²": "2", "³": "3", "−": "-", "·": " ", "×": "x"})


def _norm(u: str) -> str:
    # 'g (axis title ...)': a reader's trailing remark is not part of the printed unit.
    u = re.sub(r"\s*[\(\[].*$", "", (u or "").strip()) or (u or "")
    s = re.sub(r"\bMg\b", "tonne", u.strip()).lower().translate(_SUP)
    s = s.replace("per ", "/").replace(" per", "/")
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+", " ", s)
    # 'g plant-1' -> 'g/plant', 'kg m-2' -> 'kg/m2', 't ha-1' -> 't/ha'
    s = re.sub(r"\b([a-z]+)\s*-\s*1\b", r"/\1", s)
    s = re.sub(r"\b([a-z]+)\s*-\s*2\b", r"/\g<1>2", s)
    s = re.sub(r"\b([a-z]+)\s*-\s*3\b", r"/\g<1>3", s)
    s = s.replace(" /", "/").replace("/ ", "/").replace(" ", "")
    s = re.sub(r"/+", "/", s)  # 'kg/m-2' -> 'kg/m2'
    s = re.sub(r"plantas?\b", "plant", s).replace("plants", "plant").replace("pl.", "plant")
    s = re.sub(r"/pl(?=$|/)", "/plant", s).replace("plantant", "plant")
    s = re.sub(r"\.(?=/)", "", s)  # 't.ha-1' -> 't/ha', 'kg.m-2' -> 'kg/m2'
    s = s.replace("tonnes", "t").replace("tonne", "t").replace("tons", "t").replace("ton", "t")
    s = s.replace("m^2", "m2").replace("m^3", "m3").replace("fed.", "fed").replace("feddan", "fed")
    s = s.replace("pot-1", "/pot").replace("pots", "pot")
    s = re.sub(r"(?<![a-z])(gms?|gr|grams?)(?=$|/)", "g", s)
    s = re.sub(r"(?<=g)(dw|dm|dryweight|drywt|drymatter)(?=$|/)", "", s)
    return s


# (pattern, unit_norm, factor, denominator)
_YIELD = [
    (r"^g(fruit)?/plant$", "kg/plant", 1e-3, "PER_PLANT"),
    (r"^kg(fruit)?/plant$", "kg/plant", 1.0, "PER_PLANT"),
    (r"^kg/10plant$", "kg/plant", 0.1, "PER_PLANT"),
    (r"^t/ha$", "t/ha", 1.0, "PER_AREA"),
    (r"^kg/ha$", "t/ha", 1e-3, "PER_AREA"),
    (r"^q/ha$", "t/ha", 0.1, "PER_AREA"),
    (r"^kg/m2$", "t/ha", 10.0, "PER_AREA"),
    (r"^g/m2$", "t/ha", 0.01, "PER_AREA"),
    (r"^kg/fed$", "t/ha", 10000.0 / FEDDAN_M2 / 1000.0, "PER_AREA"),
    (r"^t/fed$", "t/ha", 10000.0 / FEDDAN_M2, "PER_AREA"),
    (r"^g/pot$", "kg/pot", 1e-3, "PER_POT"),
    (r"^kg/pot$", "kg/pot", 1.0, "PER_POT"),
    (r"^kg/plot$", "kg/plot", 1.0, "PER_PLOT"),
    (r"^g/plot$", "kg/plot", 1e-3, "PER_PLOT"),
]
_BIOMASS = [
    (r"^mg/plant$", "g/plant", 1e-3, "PER_PLANT"),
    (r"^g/plant$", "g/plant", 1.0, "PER_PLANT"),
    (r"^kg/plant$", "g/plant", 1e3, "PER_PLANT"),
    (r"^mg/pot$", "g/pot", 1e-3, "PER_POT"),
    (r"^g/pot$", "g/pot", 1.0, "PER_POT"),
    (r"^g/m2$", "g/m2", 1.0, "PER_AREA"),
    (r"^t/ha$", "g/m2", 100.0, "PER_AREA"),
    (r"^kg/ha$", "g/m2", 0.1, "PER_AREA"),
    (r"^mg$", "g", 1e-3, None),
    (r"^g$", "g", 1.0, None),
    (r"^kg$", "g", 1e3, None),
]
_FRUIT_NUMBER = [
    (r"^(no\.?|n|number|fruits?|count|pieces?|numberoffruits?)?/plant$", "count/plant", 1.0, "PER_PLANT"),
    (r"^(fruits?|no\.?)?/m2$", "count/m2", 1.0, "PER_AREA"),
]
_MEAN_FRUIT_MASS = [
    (r"^g(/fruit)?$", "g/fruit", 1.0, None),
    (r"^kg(/fruit)?$", "g/fruit", 1e3, None),
]
_WP = [
    (r"^kg/m3$", "kg/m3", 1.0, "PER_WATER"),
    (r"^g/l$", "kg/m3", 1.0, "PER_WATER"),
    (r"^g/kg$", "g/kg", 1.0, "PER_WATER"),
]
TABLES = {
    "FRUIT_YIELD": _YIELD,
    "DRY_BIOMASS": _BIOMASS,
    "FRUIT_NUMBER": _FRUIT_NUMBER,
    "MEAN_FRUIT_MASS": _MEAN_FRUIT_MASS,
    "WATER_PRODUCTIVITY": _WP,
}


# Bare mass is a yield unit only with a confirmed denominator; bare g never implies per plant.
_BARE_YIELD = {"PER_PLANT": "kg/plant", "PER_POT": "kg/pot", "PER_PLOT": "kg/plot"}


def normalize(unit_raw: str, endpoint: str, denominator: Optional[str] = None) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Return (unit_norm, factor, implied_denominator) or (None, None, None) if unknown."""
    s = _norm(unit_raw)
    for pat, norm, fac, den in TABLES.get(endpoint, []):
        if re.match(pat, s):
            return norm, fac, den
    if endpoint == "FRUIT_YIELD" and s in ("g", "kg") and denominator in _BARE_YIELD:
        return _BARE_YIELD[denominator], (1e-3 if s == "g" else 1.0), denominator
    # Printed abbreviations resolved only by the denominator read from the source: 'kg/pt' per plant, 'ton /h' per area.
    if endpoint == "FRUIT_YIELD" and denominator == "PER_PLANT" and s in ("g/pt", "kg/pt"):
        return "kg/plant", (1e-3 if s == "g/pt" else 1.0), "PER_PLANT"
    if endpoint == "FRUIT_YIELD" and denominator == "PER_AREA" and s == "t/h":
        return "t/ha", 1.0, "PER_AREA"
    # The unit printed inside a longer label: 'Total Yield (Kg/m-2)', 'Fruit weight/plant (g)'.
    inner = re.search(r"\(([^()]+)\)", unit_raw or "")
    if inner and inner.group(1).strip() != (unit_raw or "").strip():
        return normalize(inner.group(1), endpoint, denominator)
    return None, None, None
