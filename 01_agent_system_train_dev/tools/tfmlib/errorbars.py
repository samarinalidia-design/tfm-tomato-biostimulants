"""Source-labelled error bars, explicit user assumptions and resolution checks."""
from __future__ import annotations

import json
import math

from .figures import to_value


def resolve_error_bar(panel, point, cal, mean, error, info, policy):
    """Keep reported type separate from the effective project interpretation.

    Pixel/point uncertainty is a geometric bound, not statistical SE/SD.  The
    SE default is applied only to actual unlabelled bars, never to missing bars
    or to an explicitly reported CI, range, or other interval.
    """
    status = point["error_bar_status"]
    reported = panel["error_bar_type"]
    hi, lo = point.get("px_err_hi"), point.get("px_err_lo")
    precision = float(point.get("coordinate_uncertainty") or 0)
    if precision <= 0:
        raise ValueError("coordinate_uncertainty must describe the original point resolution")
    if panel["coord_space"] == "image_px" and precision < 0.5:
        raise ValueError("raster coordinate uncertainty cannot be smaller than half a pixel")
    def bound(px):
        value = to_value(px, cal)
        positional = max(abs(to_value(px + precision, cal) - value),
                         abs(to_value(px - precision, cal) - value))
        residual = float(cal.get("max_resid_fitted") or 0)
        calibration = abs(value) * (10 ** residual - 1) if cal["scale"] == "log10" else residual
        return positional + calibration
    true_zero = bool(point.get("true_zero"))
    if true_zero:
        # A bar at the baseline has no relative bound; the reading must still sit within resolution of 0.
        if status != "ABSENT_IN_SOURCE" or not (point.get("error_bar_note") or "").strip():
            raise ValueError("true_zero needs ABSENT_IN_SOURCE and an original-source note")
        if abs(mean) > bound(point["px_mean"]) + 1e-12:
            raise ValueError("true_zero reading is farther from 0 than the coordinate/calibration bound")
    mean_bound = bound(point["px_mean"]) / abs(mean) if mean and not true_zero else None
    if mean_bound is not None and float(panel["relative_uncertainty"]) < mean_bound - 1e-9:
        raise ValueError("mean uncertainty understates the original coordinate/calibration resolution")
    base = {
        "dispersion_type_reported": reported,
        "dispersion_basis": "SOURCE_REPORTED",
        "error_bar_status": status,
        "error_bar_bounds_json": None,
        "error_bar_relative_uncertainty": None,
    }
    if status in ("ABSENT_IN_SOURCE", "NOT_READABLE"):
        if hi is not None or lo is not None:
            raise ValueError("non-digitized error-bar status conflicts with supplied endpoints")
        if not (point.get("error_bar_note") or "").strip():
            raise ValueError("absent/unreadable error bars need an original-source reason")
        if status == "NOT_READABLE" and int(point.get("recovery_attempts") or 0) < 2:
            raise ValueError("retry original render/vector probe and supplementary before NOT_READABLE")
        base.update(dispersion_type="NONE" if status == "ABSENT_IN_SOURCE" else "UNCLEAR",
                    dispersion_value=None,
                    dispersion_basis="NOT_REPORTED" if status == "ABSENT_IN_SOURCE" else "NOT_READABLE")
        return base
    expected = {
        "DIGITIZED_BOTH": (True, True),
        "DIGITIZED_UPPER_ONLY": (True, False),
        "DIGITIZED_LOWER_ONLY": (False, True),
    }
    if status not in expected or expected[status] != (hi is not None, lo is not None):
        raise ValueError("digitize each visible error-bar endpoint and declare the matching status")
    if reported == "NONE":
        raise ValueError("visible error-bar endpoints cannot have error_bar_type=NONE")
    if hi is not None and to_value(hi, cal) < mean:
        raise ValueError("px_err_hi must be the endpoint above the mean in source values")
    if lo is not None and to_value(lo, cal) > mean:
        raise ValueError("px_err_lo must be the endpoint below the mean in source values")
    if error is None or not math.isfinite(error) or error <= 0:
        raise ValueError("error-bar half-width must be positive and geometrically defensible")
    if hi is not None and lo is not None:
        ends = [to_value(hi, cal), to_value(lo, cal)]
        if not min(ends) <= mean <= max(ends):
            raise ValueError("both error-bar endpoints must bracket the mean")
    geometric = (bound(point["px_mean"]) + max(bound(x) for x in (hi, lo) if x is not None)) / error
    declared = point.get("error_bar_relative_uncertainty")
    if declared is None or not math.isfinite(float(declared)) or float(declared) < geometric - 1e-9:
        raise ValueError(f"error-bar uncertainty understates geometric bound {geometric:.3%}; re-render/probe")
    # Author decision 2026-11-06: a bar above the limit is kept and flagged; the limit still binds the mean.
    bounds = {"upper": to_value(hi, cal) if hi is not None else None,
              "lower": to_value(lo, cal) if lo is not None else None,
              "coordinate_uncertainty": precision,
              "mean_relative_bound": mean_bound,
              "geometric_relative_bound": geometric,
              "note": point.get("error_bar_note")}
    base.update(error_bar_bounds_json=json.dumps(bounds, sort_keys=True),
                error_bar_relative_uncertainty=float(declared))
    dtype = reported
    if reported == "UNCLEAR":
        if policy.get("unlabelled_error_bars", "SE") == "SE":
            dtype = "SE"
            base["dispersion_basis"] = "USER_ASSUMED_SE"
        else:
            dtype = "UNCLEAR"
            base["dispersion_basis"] = "UNRESOLVED_TYPE"
    elif reported == "OTHER_INTERVAL":
        dtype = "UNCLEAR"
        base["dispersion_basis"] = "OTHER_REPORTED_INTERVAL"
    # A difference inside the reading resolution is not evidence of a truly asymmetric interval.
    if info.get("asymmetry", 0) > max(0.10, geometric):
        dtype = "UNCLEAR"
        base["dispersion_basis"] = "ASYMMETRIC_INTERVAL"
    base.update(dispersion_type=dtype,
                dispersion_value=error if dtype in ("SD", "SE", "CI95") else None)
    return base
