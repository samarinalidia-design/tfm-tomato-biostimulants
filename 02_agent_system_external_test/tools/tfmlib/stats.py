"""Small statistics helpers (no SciPy dependency)."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence

# two-sided 95 % t quantiles t(0.975, df)
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
         10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
         18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
         26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t975(df: float) -> float:
    if df is None or df < 1:
        return float("nan")
    d = int(round(df))
    if d in _T975:
        return _T975[d]
    keys = sorted(_T975)
    if d > keys[-1]:
        return 1.960 + (1.980 - 1.960) * 120.0 / d   # smooth approach to z
    lo = max(k for k in keys if k < d)
    hi = min(k for k in keys if k > d)
    # interpolate in 1/df (standard practice for t tables)
    w = (1 / d - 1 / hi) / (1 / lo - 1 / hi)
    return _T975[hi] + w * (_T975[lo] - _T975[hi])


def sd_from(dispersion_type: Optional[str], value: Optional[float], n: Optional[float], ci: Optional[dict] = None) -> Optional[float]:
    """TFM Table 5: SD direct; SE*sqrt(n); CI95 half-width -> SE via t(0.975,n-1) -> SD."""
    if value is None or dispersion_type in (None, "NONE", "UNCLEAR"):
        return None
    if dispersion_type == "SD":
        return float(value)
    if n is None or n <= 0:
        return None
    if dispersion_type == "SE":
        return float(value) * math.sqrt(n)
    if dispersion_type == "CI95":
        if not ci or ci.get("target")!="ARM_MEAN" or not ci.get("symmetric") or ci.get("sidedness")!="TWO_SIDED":return None
        if not 0 < ci.get("level",0) < 1 or n < 2:return None
        from scipy.stats import t, norm
        alpha=1-ci["level"]
        if ci.get("distribution")=="t" and ci.get("df") is not None and ci.get("df")>0:q=t.ppf(1-alpha/2,ci["df"])
        elif ci.get("distribution")=="normal":q=norm.ppf(1-alpha/2)
        else:return None
        return float(value)/q*math.sqrt(n)
    return None


def lnrr(m_t: float, m_c: float) -> Optional[float]:
    if m_t is None or m_c is None or m_t <= 0 or m_c <= 0:
        return None
    return math.log(m_t / m_c)


def var_lnrr(m_t, sd_t, n_t, m_c, sd_c, n_c) -> Optional[float]:
    if None in (m_t, sd_t, n_t, m_c, sd_c, n_c) or m_t <= 0 or m_c <= 0 or n_t <= 0 or n_c <= 0:
        return None
    return sd_t ** 2 / (n_t * m_t ** 2) + sd_c ** 2 / (n_c * m_c ** 2)


def lnrr_bias_corrected(m_t, sd_t, n_t, m_c, sd_c, n_c) -> Optional[float]:
    base = lnrr(m_t, m_c)
    if base is None or None in (sd_t, n_t, sd_c, n_c):
        return None
    return base + 0.5 * (sd_t ** 2 / (n_t * m_t ** 2) - sd_c ** 2 / (n_c * m_c ** 2))


def mad_z(values: Sequence[float]) -> List[float]:
    """Robust z = 0.6745 (x - median) / MAD (TFM 3.10)."""
    xs = [v for v in values if v is not None]
    if len(xs) < 3:
        return [0.0 for _ in values]
    med = sorted(xs)[len(xs) // 2] if len(xs) % 2 else sum(sorted(xs)[len(xs) // 2 - 1: len(xs) // 2 + 1]) / 2
    dev = sorted(abs(x - med) for x in xs)
    mad = dev[len(dev) // 2] if len(dev) % 2 else (dev[len(dev) // 2 - 1] + dev[len(dev) // 2]) / 2
    if mad == 0:
        return [0.0 if v is None or v == med else math.copysign(float("inf"), v-med) for v in values]
    return [0.6745 * (v - med) / mad if v is not None else 0.0 for v in values]
