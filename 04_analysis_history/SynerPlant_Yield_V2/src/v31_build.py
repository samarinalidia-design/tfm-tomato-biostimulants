"""V3.1 corrections layer (post-TEST, exploratory), applied on top of the frozen V2 builds (s03 yield, b03 biomass,
both unchanged). Triggered by an external review of the V3.0 Excel export (2026-11-18).

A. Contrast fixes (generic rules + audit/v3_register.json "v31_*" entries)
   R1 non-stressed 'S' arm (pre-stress cohort, well-watered reference, stress_code NONE/PRESTRESS/WW)  -> AUX
   R2 non-biostimulant 'B' arm (solvent/vehicle/mock control, mineral NPK alone)                       -> AUX
   R3 control re-basing: a biostimulant applied in a solvent/with a fertilizer is compared with the matching
      vehicle/fertilizer arm (register), lnRR = ln(m_t / m_vehicle), vi from arm SD/n when available
B. Feature fixes (new *_v3 columns; V2 columns are kept unchanged for traceability)
   drought: separate % field capacity / % ETc-irrigation / FTSW / withheld-rounds pattern; substrate WHC kept apart
   salinity: separate NaCl mM, EC of water/solution, EC of soil; equivalent dS/m from water EC or NaCl only
   stress timing: negation-aware ('before flowering' is NOT reproductive), sowing-based onset
   stress duration: recovered from context_stress_duration_days_all when a single unconflicted number is given
   dose: unit recovered from context_dose_unit_all; canonical unit family + log10 dose (within-family centred)
Outputs: outputs/v31/<target>/data/PRIMARY_EXPANDED.csv (+ AUX_removed.csv, v31_changes.csv, report.json)
  python v31_build.py [--test]   (--test: the same generic rules on the TEST inputs, post-hoc only)
"""
from __future__ import annotations
import json, re, sys
import numpy as np, pandas as pd
import s03_build_dataset as Y
from v2_common import V2, OUT, now, write_json

V31 = OUT / "v31"
REG3 = json.loads((V2 / "audit" / "v31_register.json").read_text(encoding="utf-8"))
SRC = {"yield": {"train": OUT / "data" / "PRIMARY_EXPANDED.csv", "test": OUT / "test_inputs" / "TEST_PRIMARY.csv"},
       "biomass": {"train": OUT / "biomass_v2" / "data" / "PRIMARY_EXPANDED.csv",
                   "test": OUT / "biomass_v2" / "test_inputs" / "TEST_PRIMARY.csv"}}
NOSTRESS = re.compile(r"^(NONE|PRESTRESS|WW[_-]|WELL[_-]?WATER|NO[_-]?STRESS|CONTROL)", re.I)
NOSTRESS_TXT = re.compile(r"^\s*none\b|pre-?stress (first-harvest )?cohort|well-watered reference", re.I)
NONBIO_CODE = re.compile(r"(^|[_.+-])(VEHICLE|VEH|MOCK|SOLVENT|PLACEBO|CARRIER)([_.+-]|$)|^NPK$|^MINERAL", re.I)
NONBIO_TXT = re.compile(r"^[^;]*\b(solvent control|vehicle control)\b|\bmedium, no bacteria\b|^[^;]*\bbacteria-free medium\b", re.I)


def blank(v):
    return Y.blank(v)


def jlist(v):
    if blank(v):
        return []
    try:
        x = json.loads(v) if isinstance(v, str) and v.strip().startswith("[") else [v]
    except Exception:
        x = [v]
    return [str(i) for i in x if not blank(i)]


# ------------------------------------------------------------------ B. feature parsers
NUMONLY = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*%?\s*$")


def drought_v3(r):
    out = {"drought_pct_fc_v3": np.nan, "drought_pct_etc_v3": np.nan, "drought_ftsw_v3": np.nan, "drought_days_withheld_v3": np.nan,
           "drought_pattern_v3": np.nan, "substrate_whc_pct_v3": np.nan}
    if r.get("stress_family") != "DROUGHT":
        return out
    txt, unit = str(r.get("context_stress_intensity") or ""), str(r.get("context_stress_intensity_unit") or "").lower()
    val = float(re.search(r"[-+]?\d+(?:\.\d+)?", txt).group(0)) if NUMONLY.match(txt) else np.nan
    if re.search(r"withh|rounds|interval|skipp|missed|frequency", unit + " " + txt.lower()):
        out["drought_pattern_v3"] = "IRRIGATION_EVENTS_WITHHELD"
    elif re.fullmatch(r"\s*(days?|d)\s*", unit):
        out["drought_pattern_v3"], out["drought_days_withheld_v3"] = "IRRIGATION_WITHHELD_DAYS", val
    elif "ftsw" in unit:
        out["drought_ftsw_v3"], out["drought_pattern_v3"] = val, "FTSW"
    elif re.search(r"\b[s]?fc\b|field capacity|whc|water[- ]holding|swc|rswc|soil water|substrate water", unit):
        out["drought_pct_fc_v3"], out["drought_pattern_v3"] = (val if 0 < val <= 100 else np.nan), "PCT_FIELD_CAPACITY"
    elif re.search(r"etc|\bet\b|evapo|pan|irrigation|water amount|regular|water supply|deficit", unit):
        out["drought_pct_etc_v3"], out["drought_pattern_v3"] = (val if 0 < val <= 100 else np.nan), "PCT_ETC_OR_IRRIGATION"
    if np.isnan(out["drought_pct_fc_v3"]) and out["drought_pattern_v3"] is np.nan:
        m = re.search(r"(\d{2,3})\s*(?:PCT)?_?FC\b", str(r.get("stress_code") or ""), re.I)
        if m and 0 < float(m.group(1)) <= 100:
            out["drought_pct_fc_v3"], out["drought_pattern_v3"] = float(m.group(1)), "PCT_FIELD_CAPACITY"
    fc = Y.first_num(r.get("f_field_capacity_pct"))
    if not np.isnan(fc) and fc != out["drought_pct_fc_v3"]:
        out["substrate_whc_pct_v3"] = fc          # property of the substrate, not the imposed regime
    return out


def salinity_v3(r):
    out = {"nacl_mM_v3": np.nan, "ec_water_dSm_v3": np.nan, "ec_soil_dSm_v3": np.nan, "tds_ppm_v3": np.nan,
           "salinity_basis_v3": np.nan, "salinity_dSm_equiv_v3": np.nan}
    if r.get("stress_family") != "SALINITY":
        return out
    unit, txt = str(r.get("context_stress_intensity_unit") or "").lower(), str(r.get("context_stress_intensity") or "")
    val = float(re.search(r"[-+]?\d+(?:\.\d+)?", txt).group(0)) if NUMONLY.match(txt) else np.nan
    if np.isnan(val) and not txt.strip():
        m = re.match(r"\s*([-+]?\d+(?:\.\d+)?)\s*(ds|ms)", unit)          # number written in the unit field
        val = float(m.group(1)) if m else np.nan
    nacl, ec = Y.first_num(r.get("f_nacl_mm")), Y.first_num(r.get("f_ec_irrigation_ds_m"))
    if not np.isnan(nacl) and nacl > 0:
        out["nacl_mM_v3"] = nacl
    elif not np.isnan(val) and re.search(r"\bmm\b|mmol", unit):
        out["nacl_mM_v3"] = val
    soil = bool(re.search(r"soil|ece|paste|saturat|caco3|organic matter", unit))
    if soil:
        if np.isnan(val) and re.match(r"\s*EC\s*[-+]?\d", txt):
            val = Y.first_num(txt)
        out["ec_soil_dSm_v3"] = val                       # soil salinity is NOT mixed with water EC
    elif not np.isnan(ec) and ec > 0:
        out["ec_water_dSm_v3"] = ec
    elif not np.isnan(val) and re.search(r"ds|ms/cm|ms cm", unit):
        out["ec_water_dSm_v3"] = val
    elif not np.isnan(val) and re.search(r"ppm|mg/l|mg l-1|tds", unit):
        out["tds_ppm_v3"] = val
    if not np.isnan(out["ec_water_dSm_v3"]):
        out["salinity_dSm_equiv_v3"], out["salinity_basis_v3"] = out["ec_water_dSm_v3"], "EC_WATER"
    elif not np.isnan(out["nacl_mM_v3"]):
        out["salinity_dSm_equiv_v3"], out["salinity_basis_v3"] = out["nacl_mM_v3"] / 10.0, "NaCl_mM_div10"
    elif not np.isnan(out["tds_ppm_v3"]):
        out["salinity_dSm_equiv_v3"], out["salinity_basis_v3"] = out["tds_ppm_v3"] / 640.0, "TDS_ppm_div640"
    elif not np.isnan(out["ec_soil_dSm_v3"]):
        out["salinity_basis_v3"] = "SOIL_EC_ONLY"
    return out


NEG = re.compile(r"(before|prior to|until|pre-?)\s*(the\s+)?(onset of\s+)?(flower|anthes|fruit|bloom|truss|reproductive)\w*", re.I)


def timing_v3(text):
    if blank(text):
        return np.nan
    t = str(text)
    neg = bool(NEG.search(t))
    clean = NEG.sub(" ", t)
    m = re.search(r"(\d+)\s*(?:days?|d)\s*(?:of growth\s*)?(?:after|from)\s*sowing", clean, re.I)
    if m:
        return "EARLY_VEGETATIVE" if int(m.group(1)) <= 30 else "MID_VEGETATIVE_OR_LATER"
    v = Y.stress_timing(clean)
    if (v is np.nan or (isinstance(v, float) and np.isnan(v))) and neg:
        return "VEGETATIVE_PRE_FLOWERING"
    return v


def duration_v3(r):
    v = r.get("stress_duration_days")
    if not blank(v):
        return float(v), "V2"
    vals = jlist(r.get("context_stress_duration_days_all"))
    if not vals or any("CONFLICT" in x.upper() or "UNRESOLVED" in x.upper() for x in vals):
        return np.nan, "NOT_RECOVERED"
    nums = {float(x) for x in vals if NUMONLY.match(x)}
    return (nums.pop(), "RECOVERED_CONTEXT") if len(nums) == 1 else (np.nan, "AMBIGUOUS")


DOSE_RULES = [  # (regex on unit, family, factor to canonical)
    (r"cfu|cells|spores|conidia|propagules", "CFU_PER_ML", None),
    (r"^\s*(mm|mmol)", "MOLAR_mM", 1.0), (r"\bmm\b|mmol\s*l", "MOLAR_mM", 1.0), (r"\bµm|\bum\b|umol", "MOLAR_mM", 1e-3),
    (r"ha", "PER_AREA", None), (r"m-?2|m²", "PER_AREA", None),
    (r"plant|pot|seedling|hole", "PER_PLANT_OR_POT", None),
    (r"ppm|mg\s*/?\s*l|mg l-1|mg·l", "CONC_g_per_L", 1e-3), (r"g\s*/?\s*l\b|g l-1|g·l", "CONC_g_per_L", 1.0),
    (r"ml\s*/?\s*l|ml l-1|ml·l", "CONC_mL_per_L", 1.0), (r"w/v", "CONC_g_per_L", 10.0), (r"v/v", "CONC_mL_per_L", 10.0),
    (r"%", "PERCENT_UNSPECIFIED", 1.0), (r"dilution", "DILUTION", None)]


def dose_v3(r):
    unit = r.get("f_dose_unit")
    src = "V2"
    if blank(unit):
        u = jlist(r.get("context_dose_unit_all"))
        unit, src = (u[0], "RECOVERED_CONTEXT") if len(set(u)) == 1 else (np.nan, "NOT_RECOVERED")
    val = Y.first_num(r.get("f_dose"))
    if blank(unit) or np.isnan(val) or val <= 0:
        return np.nan, np.nan, np.nan, src
    u = str(unit).lower()
    for pat, fam, f in DOSE_RULES:
        if re.search(pat, u):
            if fam == "CFU_PER_ML":
                return unit, fam, float(np.log10(val)) if val >= 10 else np.nan, src
            return unit, fam, float(np.log10(val * (f or 1.0))), src
    return unit, "OTHER", float(np.log10(val)), src


# ------------------------------------------------------------------ A. contrast fixes
def contrast_fixes(d, target, split):
    d = d.copy()
    d["v31_action"], d["v31_reason"] = "", ""
    s_txt = d.f_stress_type.fillna("")
    r1 = d.stress_code.fillna("").str.match(NOSTRESS) | s_txt.str.contains(NOSTRESS_TXT)
    r2 = d.bio_code.fillna("").str.contains(NONBIO_CODE) | d.f_composition.fillna("").str.contains(NONBIO_TXT)
    d.loc[r1, ["v31_action", "v31_reason"]] = ["AUX", "R1_NON_STRESSED_REFERENCE_ARM"]
    d.loc[r2 & ~r1, ["v31_action", "v31_reason"]] = ["AUX", "R2_NOT_A_BIOSTIMULANT(vehicle/solvent/fertilizer)"]
    for x in REG3.get("v31_contrast_exclusions", []) if split == "train" else []:
        m = (d.study_id.astype(str) == x["study_id"]) & d[x["field"]].astype(str).str.fullmatch(x["pattern"])
        d.loc[m, ["v31_action", "v31_reason"]] = ["AUX", x["id"] + ":" + x["reason"]]
    # R3 control re-basing (study-specific register: TRAIN only)
    d["lnRR_v2"] = d.lnRR
    for x in REG3.get("v31_control_rebasing", []) if split == "train" else []:
        st = d.study_id.astype(str) == x["study_id"]
        veh = d[st & d.arm_key_t.astype(str).str.fullmatch(x["vehicle_arm"])]
        if veh.empty:
            continue
        v = veh.iloc[0]
        for i in d.index[st & d.arm_key_t.astype(str).str.fullmatch(x["treated_arms"])]:
            r = d.loc[i]
            if r.arm_key_c != v.arm_key_c:
                continue
            d.loc[i, "lnRR"] = float(np.log(r.mean_t / v.mean_t))
            vi = np.nan
            if all(not blank(z) for z in (r.sd_t, r.n_t, v.sd_t, v.n_t)) and r.n_t > 0 and v.n_t > 0:
                vi = r.sd_t ** 2 / (r.n_t * r.mean_t ** 2) + v.sd_t ** 2 / (v.n_t * v.mean_t ** 2)
            d.loc[i, "vi"] = vi
            d.loc[i, "arm_key_c"] = v.arm_key_t
            d.loc[i, "mean_c"] = v.mean_t
            d.loc[i, "v31_action"] = "REBASED"
            d.loc[i, "v31_reason"] = x["id"] + ":" + x["reason"]
    return d


def build_one(target, split):
    d = pd.read_csv(SRC[target][split], low_memory=False)
    n0, k0 = len(d), d.study_id.nunique()
    d = contrast_fixes(d, target, split)
    dr = pd.DataFrame([drought_v3(r) for r in d.to_dict("records")], index=d.index)
    sa = pd.DataFrame([salinity_v3(r) for r in d.to_dict("records")], index=d.index)
    d = pd.concat([d, dr, sa], axis=1)
    d["drought_supply_pct_v3"] = d.drought_pct_fc_v3.fillna(d.drought_pct_etc_v3)
    d["stress_timing_v3"] = d.f_stress_onset_stage.map(timing_v3)
    du = [duration_v3(r) for r in d.to_dict("records")]
    d["stress_duration_days_v3"] = [a for a, _ in du]
    d["stress_duration_source_v3"] = [b for _, b in du]
    do = [dose_v3(r) for r in d.to_dict("records")]
    d["dose_unit_v3"], d["dose_family_v3"], d["log10_dose_canon_v3"], d["dose_unit_source_v3"] = zip(*do)
    d["log10_dose_canon_v3"] = pd.to_numeric(d.log10_dose_canon_v3, errors="coerce")
    d["vi_reported_v3"] = d.vi.notna() & (d.uncertainty_assumed.fillna(0).astype(float) == 0)
    aux = d[d.v31_action == "AUX"]
    d = d[d.v31_action != "AUX"].copy()
    # within-family centring of log dose (feature-only statistic; no target involved)
    med = d.groupby("dose_family_v3").log10_dose_canon_v3.transform("median")
    d["log_dose_within_family_v3"] = d.log10_dose_canon_v3 - med
    d["group_id"] = d.study_id.astype(str)
    out = V31 / target / ("data" if split == "train" else "test_inputs")
    out.mkdir(parents=True, exist_ok=True)
    name = "PRIMARY_EXPANDED.csv" if split == "train" else "TEST_PRIMARY.csv"
    d.to_csv(out / name, index=False)
    aux.to_csv(out / "AUX_removed.csv", index=False)
    ch = pd.concat([aux, d[d.v31_action == "REBASED"]])[["contrast_id", "study_id", "stress_code", "bio_code", "arm_key_t",
                                                         "arm_key_c", "lnRR_v2", "lnRR", "v31_action", "v31_reason"]]
    ch.to_csv(out / "v31_changes.csv", index=False)
    def cnt(old, new):
        return {"v2_rows": int(old.notna().sum()), "v31_rows": int(new.notna().sum()),
                "v31_studies": int(d.loc[new.notna(), "study_id"].nunique())}
    rep = {"generated_at": now(), "target": target, "split": split, "rows_in": n0, "studies_in": k0,
           "rows_out": int(len(d)), "studies_out": int(d.study_id.nunique()), "aux_removed": int(len(aux)),
           "aux_by_reason": aux.v31_reason.value_counts().to_dict(),
           "rebased": int((d.v31_action == "REBASED").sum()),
           "features": {
               "stress_duration_days": cnt(d.stress_duration_days, d.stress_duration_days_v3),
               "drought_supply_pct": cnt(d.drought_supply_pct.where(d.stress_family == "DROUGHT"),
                                         d.drought_supply_pct_v3.where(d.stress_family == "DROUGHT")),
               "drought_pattern_withheld": int((d.drought_pattern_v3 == "IRRIGATION_EVENTS_WITHHELD").sum()),
               "drought_ftsw": int(d.drought_ftsw_v3.notna().sum()),
               "substrate_whc_kept_apart": int(d.substrate_whc_pct_v3.notna().sum()),
               "salinity_dSm_equiv": cnt(d.salinity_dSm_equiv, d.salinity_dSm_equiv_v3),
               "ec_soil_separate": int(d.ec_soil_dSm_v3.notna().sum()),
               "stress_timing_changed": int((d.stress_timing.astype(str) != d.stress_timing_v3.astype(str)).sum()),
               "dose_unit_recovered": int((d.dose_unit_source_v3 == "RECOVERED_CONTEXT").sum()),
               "log_dose": cnt(pd.Series(np.nan, index=d.index), d.log10_dose_canon_v3),
               "dose_family": d.dose_family_v3.value_counts().to_dict()},
           "variance": {"vi_available": int(d.vi.notna().sum()), "vi_reported_not_assumed": int(d.vi_reported_v3.sum())}}
    write_json(out / "v31_report.json", rep)
    return rep


if __name__ == "__main__":
    split = "test" if "--test" in sys.argv else "train"
    for t in ("yield", "biomass"):
        r = build_one(t, split)
        print(json.dumps({k: r[k] for k in ("target", "rows_in", "studies_in", "rows_out", "studies_out", "aux_by_reason",
                                            "rebased", "features", "variance")}, indent=1, default=str))
