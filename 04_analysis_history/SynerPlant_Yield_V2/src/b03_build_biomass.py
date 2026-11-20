"""Biomass V2 - build the dry-biomass analysis sets (SECONDARY target) from the V3 working SQLite.

Target: lnRR = ln(dry biomass SB / dry biomass S), shoot or whole plant, one contrast per SB/S arm pair.
Re-uses the frozen yield builder's feature engineering (s03_build_dataset.py helpers and the read-only V1 builder),
imported unchanged. Outputs: outputs/biomass_v2/data/ (same file names as the yield pipeline so the frozen model,
uncertainty and meta code can be re-used by path redirection).

Tiers (pre-specified; decided before any model was fitted on biomass V2):
  STRICT             in the freeze mart A_direct_dry_biomass (dry basis confirmed, terminal, unit resolved)
  DRY_LATEST_TIME    dry confirmed, shoot/whole plant, unit resolved, but the arm pair has no terminal row ->
                     the latest available timepoint is used (same rule as for yield)
  UNIT_UNSTATED      dry confirmed, shoot/whole plant, both arms from the same outcome row but unit not stated
                     (lnRR is unit-free when both arms share the unit)
  BASIS_UNCONFIRMED  shoot/whole plant, dry basis not confirmed (fresh or unspecified) -> sensitivity only
  OTHER_ORGAN_*      root / leaf / stem / other organ -> excluded (different construct)
"""
from __future__ import annotations
import json, re, sqlite3, sys
import numpy as np, pandas as pd
import s03_build_dataset as Y          # frozen yield builder: helpers only (build() is not called)
from v2_common import V2, OUT, V1_ML, now, sha256, write_json

DB3 = V2 / "db" / "TFM_V3_WORKING.sqlite"
BIO = OUT / "biomass_v2"
DATA = BIO / "data"
TIER_RANK = {"STRICT": 0, "DRY_LATEST_TIME": 1, "UNIT_UNSTATED": 2, "BASIS_UNCONFIRMED": 3}
PRIMARY_TIERS = {"STRICT", "DRY_LATEST_TIME", "UNIT_UNSTATED"}
REG3 = json.loads((V2 / "audit" / "v3_register.json").read_text(encoding="utf-8"))
CONFERENCE = re.compile(r"IEC|proceeding|conference|abstract|ECA20|ecsoc|sciforum", re.I)


def connect3(path=None, readonly=True):
    p = path or DB3
    if readonly:
        return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    return sqlite3.connect(p)


def tier_of(r, strict_ids):
    if r.contrast_id in strict_ids:
        return "STRICT"
    if r.organ_scope not in ("SHOOT", "WHOLE_PLANT"):
        return f"OTHER_ORGAN_{r.organ_scope}"
    if r.dry_basis_confirmed != 1:
        return "BASIS_UNCONFIRMED"
    if Y.blank(r.unit_norm):
        return "UNIT_UNSTATED"
    return "DRY_LATEST_TIME"


def build(db_path=None, out_dir=None, year_rule="train", write_db=True, study_rules=True) -> dict:
    """study_rules=False (TEST): decisions that name TRAIN study_ids are not applied; generic rules are."""
    data_dir = out_dir or DATA
    data_dir.mkdir(parents=True, exist_ok=True)
    con = connect3(db_path, readonly=True)
    q = lambda s: pd.read_sql(s, con)
    REG = Y.REG
    v1 = Y.v1
    cc = q("SELECT * FROM contrast_candidates WHERE endpoint='DRY_BIOMASS' AND contrast_type='SB_vs_S'")
    strict_ids = set(q('SELECT contrast_id FROM "A_direct_dry_biomass"').contrast_id)
    d = cc.copy()
    d["bio_tier"] = [tier_of(r, strict_ids) for r in d.itertuples()]

    # ---- moderators: identical procedure to the yield builder (V1 approved mapping + V1 rules + V2 overrides)
    mapping = pd.read_csv(V1_ML / "data/input/moderator_mapping_FOR_APPROVAL.csv", dtype=str).fillna("")
    mdict = v1.mapping_dict(mapping)
    d["protocol_year"] = d["year"]
    d["mapping_source"] = "V1_APPROVED"
    for mod, src in v1.MODERATORS.items():
        raw = d[src].astype(object).where(d[src].notna(), "")
        raw = raw.map(lambda v: str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
        for v in sorted({v for v in raw if (mod, v) not in mdict}):
            if mod == "stress_family":
                texts = d.loc[raw == v, "f_stress_type"].dropna().astype(str).unique().tolist()[:5]
                lab = v1.propose_stress_family(v, texts)[0]
            else:
                lab = v1.PROPOSERS[mod](v)[0]
            mdict[(mod, v)] = lab
            d.loc[raw == v, "mapping_source"] = "V2_V1RULE_UNSEEN_VALUE"
    d = v1.apply_moderators(d, mdict)
    d["biostimulant_class_v1"] = d["biostimulant_class"]
    miss = d.biostimulant_class.isna() | d.biostimulant_class.isin(["UNMAPPED", "NOT_REPORTED"])
    d.loc[miss, "biostimulant_class"] = d.loc[miss, "f_composition"].map(lambda t: v1.propose_biostimulant_class(t)[0])
    d["class_override"] = ""
    for o in REG["biostimulant_class_overrides"]:
        if "bio_code" in o and not study_rules:
            continue
        if "bio_code" in o:
            m = (d.study_id == o["study_id"]) & (d.bio_code == o["bio_code"])
        else:
            pat = re.compile(o["match_composition_regex"], re.I)
            txt = d.f_composition.fillna("") + " " + d.bio_code.fillna("") + " " + d.f_biostimulant_class.fillna("")
            m = txt.map(lambda t: bool(pat.search(t)))
        d.loc[m, "biostimulant_class"] = o["class"]
        d.loc[m, "class_override"] = o["id"]

    # ---- engineered pre-treatment features (frozen yield helpers)
    ac = [Y.parse_app_count(f, s) for f, s in zip(d.f_frequency, d.f_application_stage)]
    d["application_count_v2"] = d["application_count"]
    fill = d.application_count_v2.isna()
    d.loc[fill, "application_count_v2"] = [a[0] for a, f in zip(ac, fill) if f]
    d["log_application_count"] = np.log1p(d.application_count_v2)
    d["stress_timing"] = d.f_stress_onset_stage.map(Y.stress_timing)
    d["substrate_type"] = [Y.substrate_type(a, b) for a, b in zip(d.f_substrate, d.f_system)]
    si = d.apply(lambda r: Y.stress_intensity(r), axis=1, result_type="expand")
    d["salinity_dSm_equiv"], d["salinity_basis"], d["drought_supply_pct"], d["drought_basis"] = si[0], si[1], si[2], si[3]
    d["microbial_log10_cfu_ml"] = [Y.log10_cfu(a, b) for a, b in zip(d.f_dose, d.f_dose_unit)]
    d["is_field"] = d.cultivation_system.astype(str).str.contains("FIELD").astype(float).where(d.cultivation_system.notna())
    # biomass-definition descriptors (design choices fixed before harvest)
    d["organ_scope_v2"] = d.organ_scope.where(d.organ_scope.isin(["SHOOT", "WHOLE_PLANT"]), "OTHER")
    d["mass_basis_v2"] = np.where(d.dry_basis_confirmed == 1, "DRY_CONFIRMED", "UNCONFIRMED")
    un = d.unit_norm.fillna("").astype(str)
    d["biomass_denominator_v2"] = np.select([un.str.contains("plant"), un.str.contains("pot"), un.str.contains("m2")],
                                            ["PER_PLANT", "PER_POT", "PER_AREA"], "UNSPECIFIED")
    d["measurement_day"] = pd.to_numeric(d.timepoint_days, errors="coerce")
    d["log_measurement_day"] = np.log1p(d.measurement_day)

    rob = q("SELECT study_id,experiment_key,domain,judgement FROM risk_of_bias")
    d = pd.concat([d, v1.rob_columns(d, v1.rob_lookup(rob))], axis=1)
    qflags = {}
    for f in (REG["source_quality_flags"] if study_rules else []):
        qflags.setdefault(f["study_id"], []).append(f["flag"])
    d["source_quality_flags"] = d.study_id.map(lambda s: ";".join(qflags.get(s, [])))
    flags = d["flags"].fillna("[]").astype(str)
    d["vi"] = d["var_effect"]
    d["vi_reported"] = d.var_effect.notna() & (d.uncertainty_assumed.fillna(0).astype(float) == 0) & \
        ~d.study_id.isin([s for s, f in qflags.items() if "ERROR_BARS_CONSTANT_ACROSS_GROUPS" in f])
    d["any_figure_source"] = d.any_figure_source.fillna(0).astype(int)
    d["flag_user_assumed_se"] = flags.str.contains("USER_ASSUMED_SE")
    d["lnRR"] = d["effect"]
    d["publication_year"] = d["year"]
    d["yield_tier"] = d["bio_tier"]          # column name expected by the re-used code (tier label, biomass meaning)

    # ---- inclusion decisions
    d["status"] = np.where(d.bio_tier.isin(PRIMARY_TIERS), "INCLUDED", "SENSITIVITY_ONLY")
    d["status_reason"] = d.bio_tier
    oth = d.bio_tier.str.startswith("OTHER_ORGAN")
    d.loc[oth, "status"] = "EXCLUDED"
    d.loc[oth, "status_reason"] = "NOT_SHOOT_OR_WHOLE_PLANT:" + d.loc[oth, "bio_tier"]
    for x in (REG["contrast_exclusions"] if study_rules else []):
        m = pd.Series(True, index=d.index)
        for k, v in x["match"].items():
            if k == "in_mart" or k not in d:
                m &= False
            else:
                m &= d[k] == v
        d.loc[m, "status"] = "EXCLUDED"
        d.loc[m, "status_reason"] = x["id"] + ":" + x["reason"]
    for x in (REG3.get("biomass_decisions", []) if study_rules else []):
        m = pd.Series(True, index=d.index)
        for k, v in x["match"].items():
            m &= d[k].astype(str) == str(v)
        m &= d.status == "INCLUDED"
        d.loc[m, "status"] = x["action"]
        d.loc[m, "status_reason"] = x["id"] + ":" + x["reason"]
    syn = d.biostimulant_class == "SYNTHETIC_PGR_NOT_BIOSTIMULANT"
    d.loc[syn & (d.status == "INCLUDED"), "status_reason"] = "V2-M003:SYNTHETIC_PGR_NOT_BIOSTIMULANT"
    d.loc[syn & (d.status == "INCLUDED"), "status"] = "SENSITIVITY_ONLY"
    yr = pd.to_numeric(d.year, errors="coerce")
    late = (yr > 2023) if year_rule == "train" else (yr < 2024)
    d.loc[late, "status"] = "EXCLUDED"
    d.loc[late, "status_reason"] = "OUTSIDE_YEAR_WINDOW"
    bad = ~(d.mean_t > 0) | ~(d.mean_c > 0) | d.effect.isna()
    d.loc[bad, "status"] = "EXCLUDED"
    d.loc[bad, "status_reason"] = "NON_COMPUTABLE_LNRR"

    # ---- one contrast per SB/S arm pair (best tier, then latest timepoint, whole plant before shoot)
    d["arm_pair"] = d.study_id + "|" + d.experiment_key.astype(str) + "|" + d.arm_key_t + "||" + d.arm_key_c
    tp_num = d.timepoint_key.astype(str).str.extract(r"(\d+)(?!.*\d)")[0].astype(float)
    d["_tp"] = d.measurement_day.fillna(tp_num).fillna(-1)
    d["_rank"] = d.bio_tier.map(TIER_RANK).fillna(9)
    d["_org"] = d.organ_scope_v2.map({"WHOLE_PLANT": 0, "SHOOT": 1}).fillna(2)
    d["_st"] = d.status.map({"INCLUDED": 0, "SENSITIVITY_ONLY": 1, "EXCLUDED": 2})
    d = d.sort_values(["arm_pair", "_st", "_rank", "_tp", "_org", "contrast_id"],
                      ascending=[True, True, True, False, True, True])
    first = ~d.arm_pair.duplicated()
    keep = d.groupby("arm_pair").contrast_id.transform("first")
    dup = ~first & (d.status != "EXCLUDED")
    d.loc[dup, "status_reason"] = "DUPLICATE_ARM_PAIR_kept:" + keep[dup]
    d.loc[dup, "status"] = "EXCLUDED_DUPLICATE"
    d = d.drop(columns=[c for c in d.columns if c.startswith("_")])

    # ---- integrity and pre-specified suspicion flags (not based on any model residual)
    d["chk_lnRR_recomputed"] = np.log(d.mean_t / d.mean_c)
    d["chk_lnRR_mismatch"] = (d.chk_lnRR_recomputed - d.effect).abs() > 1e-6
    n_sb = d[d.status == "INCLUDED"].groupby(["study_id", "experiment_key", "arm_key_c"]).arm_key_t.transform("nunique")
    d["n_sb_sharing_s"] = n_sb.reindex(d.index)
    title = d.get("title", pd.Series("", index=d.index)).fillna("").astype(str)
    susp = []
    for r, t in zip(d.itertuples(), title):
        s = []
        if abs(r.effect) > 1.5:
            s.append("ABS_LNRR_GT_1.5")
        if r.n_sb_sharing_s is not None and not pd.isna(r.n_sb_sharing_s) and r.n_sb_sharing_s > 6:
            s.append("S_SHARED_BY_GT_6_SB")
        if "ERROR_BARS_CONSTANT" in str(r.source_quality_flags):
            s.append("ERROR_BARS_CONSTANT")
        if CONFERENCE.search(str(r.doi)) or CONFERENCE.search(t):
            s.append("CONFERENCE_OR_ABSTRACT")
        susp.append(";".join(s))
    d["suspicion_flags"] = susp
    # study-level unit plausibility: arm means of one study/outcome differing > 50x
    rng = d[d.status == "INCLUDED"].groupby(["study_id", "outcome_standard_name"] if "outcome_standard_name" in d
                                            else ["study_id"]).mean_c.agg(lambda x: x.max() / x.min())
    bad_units = set(rng[rng > 50].index.get_level_values(0))
    d.loc[d.study_id.isin(bad_units) & (d.status == "INCLUDED"), "suspicion_flags"] += ";CONTROL_RANGE_GT_50X"
    d["suspicion_flags"] = d.suspicion_flags.str.strip(";")

    # ---- V1 membership
    v1b = pd.read_csv(V1_ML / "data/input/A_direct_dry_biomass.csv", usecols=["contrast_id"])
    d["in_v1_train"] = d.contrast_id.isin(set(v1b.contrast_id))

    inc = d[d.status == "INCLUDED"].copy()
    sens = d[d.status == "SENSITIVITY_ONLY"].copy()
    sets = {
        "PRIMARY_EXPANDED": inc,
        "STRICT_SENSITIVITY": inc[inc.bio_tier == "STRICT"],
        "SENSITIVITY_WHOLE_PLANT": inc[inc.organ_scope_v2 == "WHOLE_PLANT"],
        "SENSITIVITY_SHOOT": inc[inc.organ_scope_v2 == "SHOOT"],
        "SENSITIVITY_NO_ROB_HIGH": inc[inc.risk_of_bias != "high"],
        "SENSITIVITY_REPORTED_VARIANCE": inc[inc.vi_reported],
        "SENSITIVITY_TABLE_SOURCED": inc[inc.any_figure_source == 0],
        "SENSITIVITY_NO_SUSPICION_FLAGS": inc[inc.suspicion_flags == ""],
        "QUALITY_CORE": inc[(inc.risk_of_bias != "high") & (inc.source_quality_flags == "") &
                            (inc.bio_tier == "STRICT") &
                            ~inc.suspicion_flags.str.contains("CONTROL_RANGE|ERROR_BARS")],
        "SENSITIVITY_PLUS_BASIS_UNCONFIRMED_SYNTH": pd.concat([inc, sens]),
        "V1_EQUIVALENT": d[d.in_v1_train].copy(),
    }
    summary = {}
    for name, df in sets.items():
        df = df.copy()
        df["group_id"] = df["study_id"].astype(str)
        df.to_csv(data_dir / f"{name}.csv", index=False, encoding="utf-8")
        summary[name] = {"rows": int(len(df)), "studies": int(df.study_id.nunique()),
                         "by_tier": df.bio_tier.value_counts().to_dict(),
                         "by_organ": df.organ_scope_v2.value_counts().to_dict()}
    reg_cols = ["contrast_id", "study_id", "experiment_key", "arm_key_t", "arm_key_c", "arm_pair", "stress_code",
                "bio_code", "stress_family", "biostimulant_class", "bio_tier", "organ_scope", "mass_basis",
                "dry_basis_confirmed", "is_terminal_t", "timepoint_key", "status", "status_reason", "in_v1_train",
                "lnRR", "mean_t", "mean_c", "unit_norm", "vi", "vi_reported", "n_sb_sharing_s", "suspicion_flags",
                "source_quality_flags", "risk_of_bias", "doi", "year", "locator_t", "locator_c"]
    reg = d[[c for c in reg_cols if c in d]].sort_values(["study_id", "contrast_id"])
    reg.to_csv(data_dir / "biomass_contrast_register.csv", index=False, encoding="utf-8")
    con.close()
    if write_db:
        w = connect3(db_path, readonly=False)
        reg.to_sql("v3_biomass_contrasts", w, if_exists="replace", index=False)
        w.commit()
        w.close()
    feats = ["stress_family", "biostimulant_class", "application_route", "cultivation_system", "application_timing",
             "genotype_type", "application_count_v2", "relative_dose", "relative_stress_level", "stress_duration_days",
             "stress_timing", "substrate_type", "salinity_dSm_equiv", "drought_supply_pct", "microbial_log10_cfu_ml",
             "organ_scope_v2", "biomass_denominator_v2", "measurement_day", "is_field"]
    fc = []
    for f in feats:
        nn = inc[f].notna() & ~inc[f].astype(str).isin(["UNMAPPED", "NOT_REPORTED", "nan", "UNSPECIFIED", "OTHER"])
        fc.append({"feature": f, "rows_observed": int(nn.sum()), "row_coverage": round(nn.mean(), 3),
                   "studies_observed": int(inc.loc[nn, "study_id"].nunique()),
                   "study_coverage": round(inc.loc[nn, "study_id"].nunique() / inc.study_id.nunique(), 3)})
    pd.DataFrame(fc).to_csv(data_dir / "feature_completeness.csv", index=False)
    rep = {"built_at": now(), "source_db_sha256": sha256(db_path or DB3), "year_rule": year_rule, "sets": summary,
           "status_counts": d.status.value_counts().to_dict(),
           "integrity": {"lnRR_recompute_mismatch": int(d.loc[d.status == "INCLUDED", "chk_lnRR_mismatch"].sum())},
           "suspicion": {"contrasts_flagged": int((inc.suspicion_flags != "").sum()),
                         "studies_flagged": int(inc.loc[inc.suspicion_flags != "", "study_id"].nunique()),
                         "by_flag": inc.suspicion_flags.str.split(";").explode().replace("", np.nan).dropna()
                         .value_counts().to_dict()},
           "files": {p.name: sha256(p) for p in sorted(data_dir.glob("*.csv"))}}
    write_json(data_dir / "dataset_build_report.json", rep)
    return rep


if __name__ == "__main__":
    r = build()
    print(json.dumps({k: v for k, v in r.items() if k != "files"}, indent=1, default=str))
