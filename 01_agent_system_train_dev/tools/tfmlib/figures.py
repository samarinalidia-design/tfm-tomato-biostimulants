"""Calibrated figure digitisation.

Agents only *locate* things (tick marks with their printed values, bar tops,
marker centres, error-bar ends) in a declared coordinate space. Values are
computed here from a least-squares axis fit, so every number is reproducible
from the stored calibration and pixel coordinates (TFM 3.8: no visual guesses).
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


class CalibrationError(ValueError):
    pass


def fit_axis(ticks: Sequence[Dict[str, float]], scale: str = "linear") -> Dict[str, float]:
    """Fit value = a + b*px (linear) or log10(value) = a + b*px (log10).

    Returns a, b, r2, max_resid_frac (max |residual| / value range, in the fitted
    space), axis_range (value range spanned by the ticks) and n_ticks.
    """
    pts = [(float(t["px"]), float(t["value"])) for t in ticks]
    if len(pts) < 2:
        raise CalibrationError("need at least 2 ticks")
    if len({p for p, _ in pts}) < 2:
        raise CalibrationError("tick pixel positions must differ")
    if scale == "log10":
        if any(v <= 0 for _, v in pts):
            raise CalibrationError("log10 axis needs positive tick values")
        ys = [math.log10(v) for _, v in pts]
    elif scale == "linear":
        ys = [v for _, v in pts]
    else:
        raise CalibrationError(f"unknown scale '{scale}'")
    xs = [p for p, _ in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    pred = [a + b * x for x in xs]
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, pred))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    yrange = max(ys) - min(ys)
    if yrange <= 0:
        raise CalibrationError("tick values must differ")
    max_resid = max(abs(y - p) for y, p in zip(ys, pred))
    vals = [v for _, v in pts]
    return {
        "a": a, "b": b, "r2": r2, "max_resid_frac": max_resid / yrange,
        "axis_range": max(vals) - min(vals), "n_ticks": n, "scale": scale,
        "max_resid_fitted": max_resid,
    }


def to_value(px: float, cal: Dict[str, Any]) -> float:
    y = cal["a"] + cal["b"] * float(px)
    return 10 ** y if cal.get("scale") == "log10" else y


def point_values(px_mean: float, px_err_hi: Optional[float], px_err_lo: Optional[float],
                 cal: Dict[str, Any]) -> Tuple[float, Optional[float], Dict[str, Any]]:
    """Mean and symmetric error half-width from error-bar ends.

    If both ends are given, the half-width is their average half-distance
    (checked for asymmetry in source values, including on log axes). Asymmetric
    intervals are retained as bounds rather than silently interpreted as SD/SE.
    """
    mean = to_value(px_mean, cal)
    info: Dict[str, Any] = {}
    hi = to_value(px_err_hi, cal) if px_err_hi is not None else None
    lo = to_value(px_err_lo, cal) if px_err_lo is not None else None
    if hi is not None and hi < mean:
        hi, lo = lo, hi   # swapped ends (agent mislabelled); keep geometry, record it
        info["swapped_ends"] = True
    err = None
    info.update(value_hi=hi, value_lo=lo)
    if hi is not None and lo is not None:
        up, down = hi - mean, mean - lo
        err = (up + down) / 2.0
        if up > 0 and down > 0:
            info["asymmetry"] = abs(up - down) / max(up, down)
    elif hi is not None:
        err = hi - mean
    elif lo is not None:
        err = mean - lo
    if err is not None and err < 0:
        info["negative_error"] = True
        err = abs(err)
    return mean, err, info


def calibration_status(cal: Dict[str, Any], min_ticks: int, rec_ticks: int, max_resid: float) -> str:
    if cal["n_ticks"] < min_ticks:
        return "FAIL"
    if cal["max_resid_frac"] > max_resid:
        return "FAIL"
    if cal["n_ticks"] < rec_ticks:
        return "WARN_TWO_TICKS"
    return "OK"


def agree(a: float, b: float, axis_range: Optional[float], abs_frac: float, rel_tol: float) -> bool:
    tol = rel_tol * max(abs(a), abs(b))
    if axis_range:
        tol = max(tol, abs_frac * abs(axis_range))
    return abs(a - b) <= tol + 1e-12


def image_sha256(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return h
    except OSError:
        return None


def image_size(path: Path) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


# ----------------------------------------------------------- raster helpers
def grid_overlay(image_path: Path, out_path: Path, step: int = 50, zoom: float = 2.0,
                 bbox: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
    """Write a zoomed crop with a labelled pixel grid so a vision model can read
    coordinates precisely. Labels are in ORIGINAL image pixels."""
    from PIL import Image, ImageDraw
    im = Image.open(image_path).convert("RGB")
    x0, y0, x1, y1 = bbox if bbox else (0, 0, im.width, im.height)
    crop = im.crop((x0, y0, x1, y1))
    crop = crop.resize((int(crop.width * zoom), int(crop.height * zoom)), Image.LANCZOS)
    dr = ImageDraw.Draw(crop)
    first_x = (x0 // step + 1) * step
    for gx in range(first_x, x1, step):
        X = (gx - x0) * zoom
        dr.line([(X, 0), (X, crop.height)], fill=(0, 160, 255), width=1)
        dr.text((X + 2, 2), str(gx), fill=(0, 90, 200))
    first_y = (y0 // step + 1) * step
    for gy in range(first_y, y1, step):
        Y = (gy - y0) * zoom
        dr.line([(0, Y), (crop.width, Y)], fill=(255, 120, 0), width=1)
        dr.text((2, Y + 2), str(gy), fill=(200, 80, 0))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_path)
    return {"out": str(out_path), "origin": [x0, y0], "zoom": zoom, "step": step,
            "note": "grid labels are original-image pixel coordinates"}


def snap_vertical(image_path: Path, points: List[Dict[str, float]], search: int = 6,
                  half_width: int = 2, offset: int = 0) -> List[Dict[str, Any]]:
    """Refine approximate y coordinates to the strongest horizontal edge nearby.

    points: [{"x":.., "y":.., "offset": optional}]. For BAR TOPS use offset ~6-10 px:
    the profile is sampled left and right of the centre so the error-bar whisker
    (drawn through the centre) does not hide the bar top. For error-bar CAPS and
    markers use offset 0.
    """
    import numpy as np
    from PIL import Image
    g = np.asarray(Image.open(image_path).convert("L"), dtype=float)
    h, w = g.shape
    out = []
    for p in points:
        x, y = int(round(p["x"])), int(round(p["y"]))
        off = int(p.get("offset", offset))
        centres = [x] if off == 0 else [x - off, x + off]
        cols = []
        for cx in centres:
            sl = slice(max(0, cx - half_width), min(w, cx + half_width + 1))
            if sl.start < sl.stop:
                cols.append(g[:, sl].mean(axis=1))
        if not cols:
            out.append({**p, "y_snapped": p["y"], "edge_strength": 0.0})
            continue
        grad = np.mean([np.abs(np.diff(c)) for c in cols], axis=0)   # grad[i] = |col[i+1]-col[i]|
        lo, hi = max(0, y - search), min(h - 2, y + search)
        if hi <= lo:
            out.append({**p, "y_snapped": p["y"], "edge_strength": 0.0})
            continue
        seg = grad[lo:hi + 1]
        i = int(np.argmax(seg))
        out.append({**p, "y_snapped": float(lo + i + 0.5), "edge_strength": float(seg[i])})
    return out


# ----------------------------------------------------------- vector PDF probe
def vector_probe(pdf_path: Path, page_no: int, bbox: Optional[Sequence[float]] = None,
                 max_items: int = 4000) -> Dict[str, Any]:
    """List text spans and vector drawings (bars = rectangles, error bars/axes = lines)
    inside bbox on a PDF page (PyMuPDF required). Coordinates are PDF points, y down.
    For vector figures this gives exact positions: use coord_space = 'pdf_pt'."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - depends on user environment
        raise RuntimeError("PyMuPDF (fitz) is not installed in this environment") from exc
    doc = fitz.open(str(pdf_path))
    page = doc[page_no - 1]
    clip = fitz.Rect(*bbox) if bbox else page.rect

    def inside(r) -> bool:
        return fitz.Rect(r).intersects(clip)

    texts = []
    for block in page.get_text("dict", clip=clip).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = span.get("text", "").strip()
                if t:
                    x0, y0, x1, y1 = span["bbox"]
                    texts.append({"text": t, "bbox": [round(v, 2) for v in span["bbox"]],
                                  "cx": round((x0 + x1) / 2, 2), "cy": round((y0 + y1) / 2, 2)})
    rects, lines = [], []
    for d in page.get_drawings():
        for it in d.get("items", []):
            kind = it[0]
            if kind == "re":
                r = fitz.Rect(it[1])
                if inside(r) and r.width > 0.3 and r.height > 0.3:
                    rects.append({"x0": round(r.x0, 2), "y0": round(r.y0, 2), "x1": round(r.x1, 2),
                                  "y1": round(r.y1, 2), "fill": d.get("fill"), "color": d.get("color")})
            elif kind == "l":
                p1, p2 = it[1], it[2]
                if inside(fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y),
                                    max(p1.x, p2.x) + 0.01, max(p1.y, p2.y) + 0.01)):
                    lines.append({"x1": round(p1.x, 2), "y1": round(p1.y, 2), "x2": round(p2.x, 2),
                                  "y2": round(p2.y, 2), "color": d.get("color"),
                                  "orientation": "v" if abs(p1.x - p2.x) < 0.5 else
                                                 ("h" if abs(p1.y - p2.y) < 0.5 else "d")})
    doc.close()
    return {"pdf": str(pdf_path), "page": page_no, "bbox": list(clip),
            "coord_space": "pdf_pt", "texts": texts[:max_items], "rects": rects[:max_items],
            "lines": lines[:max_items],
            "hint": ("Tick labels are in `texts` (use cy for y-axis ticks); bar tops are rect y0; "
                     "error-bar caps are short horizontal lines; whiskers are vertical lines.")}
