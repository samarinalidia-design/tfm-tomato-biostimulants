"""Stage II/III - build the V2 yield analysis sets and features from the corrected V2 SQLite.

Outputs (outputs/data/):
  v2_yield_contrast_register.csv  every candidate yield contrast with tier, inclusion status and reason
  PRIMARY_EXPANDED.csv            maximal scientifically admissible set (one contrast per SB/S arm pair)
  STRICT_SENSITIVITY.csv          strict yield definition only
  SENSITIVITY_*.csv               prespecified quality / definition sensitivity sets
  V1_EQUIVALENT.csv               the 371 V1 training contrasts processed with the V2 pipeline (comparability)
  feature_completeness.csv        per-feature coverage in rows and independent studies
The DB receives the same register as table v2_yield_contrasts.
"""
from __future__ import annotations
import importlib.util, json, re, sys
import numpy as np, pandas as pd
from v2_common import connect, AUDIT, OUT, V1_ML, now, write_json, sha256

DATA = OUT / "data"
DATA.mkdir(parents=True, exist_ok=True)
REG = json.loads((AUDIT / "corrections_register.json").read_text(encoding="utf-8"))

# --- read-only import of the V1 handoff builder (moderator rules + approved mapping) -----------------
_spec = importlib.util.spec_from_file_location("v1_builder", V1_ML / "build_handoff_from_freeze.py")
v1 = importlib.util.module_from_spec(_spec)
sys.modules["v1_builder"] = v1
_spec.loader.exec_module(v1)

TIER_RANK = {"STRICT": 0, "ASSUMED_DEFINITION": 1, "BROAD_DEFINITION": 2, "RELATIVE_SHARED_UNIT": 3,
             "BOX_CENTRE": 4, "AMBIGUOUS_IDENTITY": 5, "AMBIENT_STRESS_BVC": 6, "DRY_OR_NONMARKETABLE": 7,
             "UNRESOLVED": 8}
PRIMARY_TIERS = {"STRICT", "ASSUMED_DEFINITION", "BROAD_DEFINITION", "RELATIVE_SHARED_UNIT"}
NUM_WORDS = {"once": 1, "single": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "thrice": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


# ------------------------------------------------------------------ helpers
def blank(v):
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() in ("", "nan", "None", "NaN")


def parse_app_count(freq, stage):
    """Explicit counts only. 'every 2 weeks' without a duration is NOT converted."""
    t = " ".join(str(x).lower() for x in (freq, stage) if not blank(x))
    if not t:
        return np.nan, "NOT_REPORTED"
    m = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:sprays|applications|times|doses|"
                  r"treatments|drenches|inoculations|foliar)", t)
    if m:
        g = m.group(1)
        return float(NUM_WORDS.get(g, g)), "PARSED_EXPLICIT_COUNT"
    m = re.search(r"(?:weekly|once a week)[^;.]*?\bfor\s+(\d+|six|five|four|eight|ten)\s+weeks", t)
    if m:
        g = m.group(1)
        return float(NUM_WORDS.get(g, g)), "PARSED_WEEKLY_FOR_N_WEEKS"
    days = re.findall(r"(\d+)(?:\s*,\s*|\s+and\s+)(?=\d+\s*(?:,|and|days|d\b|dat|das))", t)
    m = re.search(r"((?:\d+\s*,\s*)+\d+\s+and\s+\d+|\d+\s+and\s+\d+)\s*(?:days|d\b|dat|das)", t)
    if m:
        return float(len(re.findall(r"\d+", m.group(1)))), "PARSED_LISTED_DAYS"
    if re.search(r"\b(single|once|one[- ]time|no repeat|no further)\b", t):
        return 1.0, "PARSED_SINGLE"
    if re.search(r"\btwice\b", t):
        return 2.0, "PARSED_TWICE"
    return np.nan, "NOT_PARSEABLE"


def stress_timing(text):
    t = str(text).lower()
    if blank(text):
        return np.nan
    if re.search(r"flower|anthes|fruit|reproductive|bloom|truss", t):
        return "REPRODUCTIVE"
    if re.search(r"throughout|entire|whole|planting-to-harvest|production period|all season|full cycle|until harvest|"
                 r"from transplant|before field transplanting|band-placed|at transplant|from sowing|from planting", t):
        return "WHOLE_CYCLE"
    m = re.search(r"(\d+)\s*(?:days?|d)\s*after\s*(?:transplant|planting)", t)
    if m:
        return "EARLY_VEGETATIVE" if int(m.group(1)) <= 30 else "MID_VEGETATIVE_OR_LATER"
    if re.search(r"seedling|establishment|vegetative|true leaf|leaf stage|weeks? (?:of|after) (?:post-)?transplant", t):
        return "EARLY_VEGETATIVE"
    return np.nan


SOILLESS = re.compile(r"peat|perlite|vermiculite|rock ?wool|coco|coir|hydropon|nutrient solution|soilless|soil-less|"
                      r"sand culture|nft|substrate mix|pumice|zeolite|grodan", re.I)


def substrate_type(sub, system):
    s = " ".join(str(x) for x in (sub, system) if not blank(x))
    if not s:
        return np.nan
    if SOILLESS.search(s) and not re.search(r"\bsoil\b(?!-?less)", s.replace("soilless", "")):
        return "SOILLESS"
    if re.search(r"soil|loam|clay|sand|field", s, re.I):
        return "SOIL"
    if SOILLESS.search(s):
        return "SOILLESS"
    return np.nan


def first_num(v):
    if blank(v):
        return np.nan
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else np.nan


def stress_intensity(row):
    """Family-specific, physically homogeneous intensity scales. Returns (salinity_dSm_equiv, salinity_basis,
    drought_supply_pct, drought_basis). Conversions: 1 dS/m ~ 10 mM NaCl ~ 640 mg/L TDS (USDA Handbook 60 rule of
    thumb; used only within salinity and kept in a separate sensitivity feature)."""
    fam = row.get("stress_family")
    unit = str(row.get("context_stress_intensity_unit") or "").lower()
    val = first_num(row.get("context_stress_intensity"))
    sal, sb, dr, db = np.nan, np.nan, np.nan, np.nan
    if fam == "SALINITY":
        nacl = first_num(row.get("f_nacl_mm"))
        ec = first_num(row.get("f_ec_irrigation_ds_m"))
        if not np.isnan(ec) and ec > 0:
            sal, sb = ec, "EC_IRRIGATION_dS_m"
        elif not np.isnan(nacl) and nacl > 0:
            sal, sb = nacl / 10.0, "NaCl_mM_div10"
        elif not np.isnan(val) and val > 0:
            if "mm" in unit and "nacl" in unit or unit.strip() in ("mm", "mmol/l", "mmol l-1"):
                sal, sb = val / 10.0, "NaCl_mM_div10"
            elif "ds" in unit or "ms/cm" in unit or "ms cm" in unit:
                sal, sb = val, "EC_dS_m"
            elif "ppm" in unit or "mg/l" in unit or "mg l-1" in unit or "tds" in unit:
                sal, sb = val / 640.0, "TDS_mgL_div640"
    elif fam == "DROUGHT":
        fc = first_num(row.get("f_field_capacity_pct"))
        if not np.isnan(fc) and 0 < fc <= 100:
            dr, db = fc, "PCT_FIELD_CAPACITY"
        elif not np.isnan(val) and 0 < val <= 100:
            if re.search(r"fc|field capacity|whc|water holding|sfc", unit):
                dr, db = val, "PCT_FIELD_CAPACITY"
            elif re.search(r"etc|\bet\b|evapotrans|et-based|irrigation dose|irrigation", unit):
                dr, db = val, "PCT_ETC_OR_IRRIGATION"
    return sal, sb, dr, db


def log10_cfu(dose, unit):
    u = str(unit or "").lower()
    d = first_num(dose)
    if np.isnan(d) or d <= 0:
        return np.nan
    if re.search(r"cfu|cells|spores|conidia", u) and re.search(r"/ ?ml|ml-1|ml−1|per ml", u) and d >= 100:
        return float(np.log10(d))
    return np.nan


# ------------------------------------------------------------------ build
def build() -> dict:
    con = connect(readonly=False)
    q = lambda s: pd.read_sql(s, con)
    cc = q("SELECT * FROM contrast_candidates WHERE endpoint='FRUIT_YIELD'")
    mem = {}
    for m in ["A_direct_yield", "A_direct_yield_assumed", "A_direct_yield_broad", "A_direct_yield_unit_unresolved",
              "A_box_centre_assumed", "A_descriptive"]:
        mem[m] = set(q(f'SELECT contrast_id FROM "{m}"').contrast_id)
    sbs = cc[cc.contrast_type == "SB_vs_S"].copy()

    def tier(cid, sid):
        if cid in mem["A_direct_yield"]:
            return "STRICT"
        if cid in mem["A_direct_yield_assumed"]:
            return "ASSUMED_DEFINITION"
        if cid in mem["A_direct_yield_broad"]:
            return "BROAD_DEFINITION"
        if cid in mem["A_direct_yield_unit_unresolved"]:
            ok = {r["study_id"] for r in REG["relative_unit_inclusions"]}
            return "RELATIVE_SHARED_UNIT" if sid in ok else "UNRESOLVED"
        if cid in mem["A_box_centre_assumed"]:
            return "BOX_CENTRE"
        return "DRY_OR_NONMARKETABLE"

    sbs["yield_tier"] = [tier(c, s) for c, s in zip(sbs.contrast_id, sbs.study_id)]
    # ambient-stress B_vs_C sensitivity rows
    amb_ids = {r["study_id"] for r in REG["ambient_stress_bvc_sensitivity"]}
    amb = cc[(cc.contrast_type == "B_vs_C") & cc.study_id.isin(amb_ids)].copy()
    amb["yield_tier"] = "AMBIENT_STRESS_BVC"
    d = pd.concat([sbs, amb], ignore_index=True)

    # ---- moderators: V1 approved mapping + V1 rules for unseen values + V2 overrides
    mapping = pd.read_csv(V1_ML / "data/input/moderator_mapping_FOR_APPROVAL.csv", dtype=str).fillna("")
    mdict = v1.mapping_dict(mapping)
    d["protocol_year"] = d["year"]
    d["mapping_source"] = "V1_APPROVED"
    for mod, src in v1.MODERATORS.items():
        raw = d[src].astype(object).where(d[src].notna(), "")
        raw = raw.map(lambda v: str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
        unseen = sorted({v for v in raw if (mod, v) not in mdict})
        for v in unseen:
            if mod == "stress_family":
                texts = d.loc[raw == v, "f_stress_type"].dropna().astype(str).unique().tolist()[:5]
                lab = v1.propose_stress_family(v, texts)[0]
            else:
                lab = v1.PROPOSERS[mod](v)[0]
            mdict[(mod, v)] = lab
            d.loc[raw == v, "mapping_source"] = "V2_V1RULE_UNSEEN_VALUE"
    d = v1.apply_moderators(d, mdict)
    d["biostimulant_class_v1"] = d["biostimulant_class"]   # as V1 would label it (for the F0 ablation)
    # biostimulant class: fill from composition when the class field is missing, then explicit overrides
    miss = d.biostimulant_class.isna() | d.biostimulant_class.isin(["UNMAPPED", "NOT_REPORTED"])
    d.loc[miss, "biostimulant_class"] = d.loc[miss, "f_composition"].map(lambda t: v1.propose_biostimulant_class(t)[0])
    d["biostimulant_subclass"] = np.nan
    d["class_override"] = ""
    for o in REG["biostimulant_class_overrides"]:
        if "bio_code" in o:
            m = (d.study_id == o["study_id"]) & (d.bio_code == o["bio_code"])
        else:
            pat = re.compile(o["match_composition_regex"], re.I)
            txt = d.f_composition.fillna("") + " " + d.bio_code.fillna("") + " " + d.f_biostimulant_class.fillna("")
            m = txt.map(lambda t: bool(pat.search(t)))
        d.loc[m, "biostimulant_class"] = o["class"]
        d.loc[m, "biostimulant_subclass"] = o.get("subclass", np.nan)
        d.loc[m, "class_override"] = o["id"]

    # ---- V2 engineered pre-treatment features
    ac = [parse_app_count(f, s) for f, s in zip(d.f_frequency, d.f_application_stage)]
    d["application_count_v2"] = d["application_count"]
    d["application_count_v2_status"] = d["application_count_status"]
    fill = d.application_count_v2.isna()
    d.loc[fill, "application_count_v2"] = [a[0] for a, f in zip(ac, fill) if f]
    d.loc[fill, "application_count_v2_status"] = [a[1] for a, f in zip(ac, fill) if f]
    d["log_application_count"] = np.log1p(d.application_count_v2)
    d["stress_timing"] = d.f_stress_onset_stage.map(stress_timing)
    d["substrate_type"] = [substrate_type(a, b) for a, b in zip(d.f_substrate, d.f_system)]
    si = d.apply(lambda r: stress_intensity(r), axis=1, result_type="expand")
    d["salinity_dSm_equiv"], d["salinity_basis"], d["drought_supply_pct"], d["drought_basis"] = si[0], si[1], si[2], si[3]
    d["microbial_log10_cfu_ml"] = [log10_cfu(a, b) for a, b in zip(d.f_dose, d.f_dose_unit)]
    d["is_microbial"] = d.biostimulant_class.isin(["AMF", "PGPR_BACTERIA", "BENEFICIAL_FUNGI_NON_AMF",
                                                   "MICROBIAL_UNSPECIFIED", "MICROBIAL_CONSORTIUM_MIXED"]).astype(int)
    d["is_field"] = d.cultivation_system.astype(str).str.contains("FIELD").astype(float).where(d.cultivation_system.notna())
    # yield-definition descriptors (design choices known before harvest -> allowed as F3 features)
    d["yield_scope_v2"] = d.yield_scope.where(d.yield_scope.isin(["TOTAL", "MARKETABLE"]), "UNSPECIFIED")
    d["harvest_window_v2"] = d.harvest_window.where(d.harvest_window.isin(["CUMULATIVE", "SINGLE_HARVEST", "PARTIAL"]),
                                                    "UNSPECIFIED")
    den = d.denominator.where(d.denominator.isin(["PER_PLANT", "PER_AREA"]), "OTHER_OR_UNSPECIFIED")
    for r in REG["relative_unit_inclusions"]:
        den[(d.study_id == r["study_id"]) & (d.yield_tier == "RELATIVE_SHARED_UNIT")] = \
            "PER_PLOT" if r["denominator_v2"] == "PER_PLOT" else "OTHER_OR_UNSPECIFIED"
    d["denominator_v2"] = den

    # ---- risk of bias (V1 rule: high if any of 10 domains high)
    rob = q("SELECT study_id,experiment_key,domain,judgement FROM risk_of_bias")
    d = pd.concat([d, v1.rob_columns(d, v1.rob_lookup(rob))], axis=1)

    # ---- source-quality flags
    qflags = {}
    for f in REG["source_quality_flags"]:
        qflags.setdefault(f["study_id"], []).append(f["flag"])
    qflags.setdefault("D_6b5d82abb9f7e388", []).append("SOURCE_VALUES_QUANTIZED")
    d["source_quality_flags"] = d.study_id.map(lambda s: ";".join(qflags.get(s, [])))
    d["stress_is_ambient"] = d.f_stress_type.fillna("").str.contains("ambient|no non-|without a non", case=False) | \
        d.stress_code.fillna("").str.contains("AMBIENT|NATURAL|RAINFED")
    flags = d["flags"].fillna("[]").astype(str)
    d["vi"] = d["var_effect"]
    d["vi_reported"] = d.var_effect.notna() & (d.uncertainty_assumed.fillna(0).astype(float) == 0) & \
        ~d.study_id.isin([s for s, f in qflags.items() if "ERROR_BARS_CONSTANT_ACROSS_GROUPS" in f])
    d["any_figure_source"] = d.any_figure_source.fillna(0).astype(int)
    d["flag_user_assumed_se"] = flags.str.contains("USER_ASSUMED_SE")
    d["flag_two_tick_axis"] = flags.str.contains("TWO_TICK")
    d["flag_per_plant_context_assumed"] = flags.str.contains("PER_PLANT_CONTEXT_ASSUMED")
    d["lnRR"] = d["effect"]
    d["publication_year"] = d["year"]

    # ---- inclusion decisions
    d["status"] = np.where(d.yield_tier.isin(PRIMARY_TIERS), "INCLUDED", "SENSITIVITY_ONLY")
    d["status_reason"] = d.yield_tier
    d.loc[d.yield_tier == "UNRESOLVED", "status"] = "EXCLUDED"
    d.loc[d.yield_tier == "DRY_OR_NONMARKETABLE", "status"] = "EXCLUDED"
    d.loc[d.yield_tier == "DRY_OR_NONMARKETABLE", "status_reason"] = "NOT_FRESH_HARVESTED_YIELD(dry fruit mass / non-marketable / early-only)"
    for x in REG["contrast_exclusions"]:
        m = pd.Series(True, index=d.index)
        for k, v in x["match"].items():
            if k == "in_mart":
                m &= d.contrast_id.isin(mem[v])
            else:
                m &= d[k] == v
        d.loc[m, "status"] = np.where(x["reason"] == "YIELD_IDENTITY_AMBIGUOUS", "SENSITIVITY_ONLY", "EXCLUDED")
        d.loc[m, "status_reason"] = x["id"] + ":" + x["reason"]
        if x["reason"] == "YIELD_IDENTITY_AMBIGUOUS":
            d.loc[m, "yield_tier"] = "AMBIGUOUS_IDENTITY"
    syn = d.biostimulant_class == "SYNTHETIC_PGR_NOT_BIOSTIMULANT"
    d.loc[syn & (d.status == "INCLUDED"), "status_reason"] = "V2-M003:SYNTHETIC_PGR_NOT_BIOSTIMULANT"
    d.loc[syn & (d.status == "INCLUDED"), "status"] = "SENSITIVITY_ONLY"
    late = pd.to_numeric(d.year, errors="coerce") > 2023
    d.loc[late, "status"] = "EXCLUDED"
    d.loc[late, "status_reason"] = "POST_2023_NOT_TRAIN_DEV"
    bad = ~(d.mean_t > 0) | ~(d.mean_c > 0) | d.effect.isna()
    d.loc[bad, "status"] = "EXCLUDED"
    d.loc[bad, "status_reason"] = "NON_COMPUTABLE_LNRR"

    # ---- one contrast per SB/S arm pair (terminal cumulative total preferred)
    d["arm_pair"] = d.study_id + "|" + d.experiment_key.astype(str) + "|" + d.arm_key_t + "||" + d.arm_key_c
    tp_num = d.timepoint_key.astype(str).str.extract(r"(\d+)(?!.*\d)")[0].astype(float)
    d["_tp"] = pd.to_numeric(d.timepoint_days, errors="coerce").fillna(tp_num).fillna(-1)
    d["_rank"] = d.yield_tier.map(TIER_RANK)
    d["_scope"] = d.yield_scope_v2.map({"TOTAL": 0, "UNSPECIFIED": 1, "MARKETABLE": 2})
    d["_win"] = d.harvest_window_v2.map({"CUMULATIVE": 0, "UNSPECIFIED": 1, "SINGLE_HARVEST": 2, "PARTIAL": 3})
    d["_den"] = d.denominator_v2.map({"PER_PLANT": 0, "PER_AREA": 1, "PER_PLOT": 2, "OTHER_OR_UNSPECIFIED": 3})
    d["_st"] = d.status.map({"INCLUDED": 0, "SENSITIVITY_ONLY": 1, "EXCLUDED": 2})
    d = d.sort_values(["arm_pair", "_st", "_rank", "_tp", "_scope", "_win", "_den", "contrast_id"],
                      ascending=[True, True, True, False, True, True, True, True])
    first = ~d.arm_pair.duplicated()
    keep_reason = d.groupby("arm_pair").contrast_id.transform("first")
    dup = ~first & (d.status != "EXCLUDED")
    d.loc[dup, "status_reason"] = "DUPLICATE_ARM_PAIR_kept:" + keep_reason[dup]
    d.loc[dup, "status"] = "EXCLUDED_DUPLICATE"
    d = d.drop(columns=[c for c in d.columns if c.startswith("_")])

    # ---- V1 membership (comparability)
    v1p = pd.read_csv(V1_ML / "data/input/A_yield_primary.csv", usecols=["contrast_id"])
    d["in_v1_train"] = d.contrast_id.isin(set(v1p.contrast_id))

    # ---- analysis sets
    inc = d[d.status == "INCLUDED"].copy()
    sens = d[d.status == "SENSITIVITY_ONLY"].copy()
    sets = {
        "PRIMARY_EXPANDED": inc,
        "STRICT_SENSITIVITY": inc[inc.yield_tier == "STRICT"],
        "SENSITIVITY_STRICT_PLUS_ASSUMED": inc[inc.yield_tier.isin(["STRICT", "ASSUMED_DEFINITION"])],
        "SENSITIVITY_NO_ROB_HIGH": inc[inc.risk_of_bias != "high"],
        "SENSITIVITY_REPORTED_VARIANCE": inc[inc.vi_reported],
        "SENSITIVITY_TABLE_SOURCED": inc[inc.any_figure_source == 0],
        "SENSITIVITY_NO_SOURCE_FLAGS": inc[inc.source_quality_flags == ""],
        "SENSITIVITY_NO_AMBIENT_STRESS": inc[~inc.stress_is_ambient],
        "QUALITY_CORE": inc[(inc.risk_of_bias != "high") & (inc.source_quality_flags == "") &
                            inc.yield_tier.isin(["STRICT", "ASSUMED_DEFINITION"])],
        "SENSITIVITY_PLUS_BOX_AMBIG_SYNTH": pd.concat([inc, sens[sens.yield_tier.isin(
            ["BOX_CENTRE", "AMBIGUOUS_IDENTITY"]) | (sens.biostimulant_class == "SYNTHETIC_PGR_NOT_BIOSTIMULANT")]]),
        "SENSITIVITY_PLUS_AMBIENT_BVC": pd.concat([inc, sens[sens.yield_tier == "AMBIENT_STRESS_BVC"]]),
    }
    v1eq = d[d.in_v1_train].copy()
    sets["V1_EQUIVALENT"] = v1eq
    # V1 rows that V2 does not keep: keep a record
    keep_cols = None
    summary = {}
    for name, df in sets.items():
        df = df.copy()
        df["group_id"] = df["study_id"].astype(str)   # studies_with_more_than_one_cluster == 0 (checked)
        df.to_csv(DATA / f"{name}.csv", index=False, encoding="utf-8")
        summary[name] = {"rows": int(len(df)), "studies": int(df.study_id.nunique()),
                         "by_tier": df.yield_tier.value_counts().to_dict(),
                         "biotic_studies": int(df[df.stress_family == "BIOTIC"].study_id.nunique())}
    reg_cols = ["contrast_id", "study_id", "experiment_key", "contrast_type", "arm_key_t", "arm_key_c", "arm_pair",
                "stress_code", "bio_code", "stress_family", "biostimulant_class", "yield_tier", "status",
                "status_reason", "in_v1_train", "lnRR", "mean_t", "mean_c", "unit_norm", "yield_scope",
                "harvest_window", "denominator", "denominator_v2", "timepoint_key", "source_quality_flags",
                "risk_of_bias", "doi", "year", "locator_t", "locator_c"]
    reg = d[reg_cols].sort_values(["study_id", "contrast_id"])
    reg.to_csv(DATA / "v2_yield_contrast_register.csv", index=False, encoding="utf-8")
    reg.to_sql("v2_yield_contrasts", con, if_exists="replace", index=False)
    con.commit()

    # ---- feature completeness (rows and independent studies) on PRIMARY_EXPANDED
    feats = ["stress_family", "biostimulant_class", "application_route", "cultivation_system", "application_timing",
             "genotype_type", "application_count", "application_count_v2", "relative_dose", "relative_stress_level",
             "stress_duration_days", "stress_timing", "substrate_type", "salinity_dSm_equiv", "drought_supply_pct",
             "microbial_log10_cfu_ml", "yield_scope_v2", "harvest_window_v2", "denominator_v2", "is_field"]
    rows = []
    for f in feats:
        nn = inc[f].notna() & ~inc[f].astype(str).isin(["UNMAPPED", "NOT_REPORTED", "nan", "OTHER_OR_UNSPECIFIED",
                                                        "UNSPECIFIED"])
        rows.append({"feature": f, "rows_observed": int(nn.sum()), "rows_total": len(inc),
                     "row_coverage": round(nn.mean(), 3),
                     "studies_observed": int(inc.loc[nn, "study_id"].nunique()),
                     "study_coverage": round(inc.loc[nn, "study_id"].nunique() / inc.study_id.nunique(), 3),
                     "v1_rows_observed": int(nn[inc.in_v1_train].sum())})
    fc = pd.DataFrame(rows)
    fc.to_csv(DATA / "feature_completeness.csv", index=False)
    lost = pd.read_csv(V1_ML / "data/input/A_yield_primary.csv", usecols=["contrast_id", "study_id"])
    lost = lost[~lost.contrast_id.isin(set(inc.contrast_id))].merge(
        d[["contrast_id", "status", "status_reason"]], on="contrast_id", how="left")
    lost.to_csv(DATA / "v1_rows_not_in_v2_primary.csv", index=False)
    rep = {"built_at": now(), "sets": summary, "status_counts": d.status.value_counts().to_dict(),
           "v1_rows_not_in_v2_primary": lost.status_reason.str.split(":").str[0].value_counts().to_dict(),
           "files": {p.name: sha256(p) for p in sorted(DATA.glob("*.csv"))}}
    write_json(DATA / "dataset_build_report.json", rep)
    return rep


if __name__ == "__main__":
    r = build()
    print(json.dumps({k: v for k, v in r.items() if k != "files"}, indent=1, default=str))
