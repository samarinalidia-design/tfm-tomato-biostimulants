"""Section 6.4 - can early physiological/biochemical measurements on the SAME arms support an auxiliary yield model?

Counts, for every PRIMARY_EXPANDED yield contrast, physiology/biochemistry measurements recorded on both its SB and
its S arm (same trait). Source: legacy raw_measurements layer (imported, NOT verified by the agent pipeline, per the
project contract) joined to verified arms via arm_id/experiment_id. Decision rule (project analysis contract):
an exploratory model needs >= 8 independent studies sharing the predictor, measured before harvest.
"""
from __future__ import annotations
import pandas as pd
from v2_common import connect, OUT, now, write_json

PHYS = {"photosynthesis", "pigments", "osmolality_balance", "enzyme_activity", "antioxidant_enzyme", "physiology",
        "biochemistry", "ion_homeostasis", "growth_plant_physiology", "phytohormones", "mineral_nutrition"}
TERMINAL = r"harvest|terminal|final|end of|maturity|fruit"


def main():
    con = connect(readonly=True)
    m = pd.read_sql("SELECT experiment_id, arm_id, outcome_standard_name, outcome_family, timepoint_raw "
                    "FROM raw_measurements", con)
    arms = pd.read_sql("SELECT study_id, arm_key, arm_id, experiment_id FROM arms", con)
    p = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    mp = m[m.outcome_family.isin(PHYS)].merge(arms.dropna(subset=["arm_id"]), on=["arm_id", "experiment_id"])
    mp["pre_harvest"] = ~mp.timepoint_raw.fillna("").str.contains(TERMINAL, case=False)
    h = p[["study_id", "arm_key_t", "arm_key_c", "contrast_id"]].merge(
        mp.rename(columns={"arm_key": "arm_key_t"})[["study_id", "arm_key_t", "outcome_standard_name", "pre_harvest"]],
        on=["study_id", "arm_key_t"]).merge(
        mp.rename(columns={"arm_key": "arm_key_c"})[["study_id", "arm_key_c", "outcome_standard_name"]],
        on=["study_id", "arm_key_c", "outcome_standard_name"]).drop_duplicates()
    per_trait = h.groupby("outcome_standard_name").agg(studies=("study_id", "nunique"),
                                                       contrasts=("contrast_id", "nunique"),
                                                       pre_harvest_share=("pre_harvest", "mean")).sort_values(
        "studies", ascending=False)
    per_trait.to_csv(OUT / "data" / "physiology_linkage_by_trait.csv")
    best = int(per_trait.studies.max()) if len(per_trait) else 0
    rep = {"generated_at": now(), "primary_studies": int(p.study_id.nunique()),
           "contrasts_with_any_matched_trait": int(h.contrast_id.nunique()),
           "studies_with_any_matched_trait": int(h.study_id.nunique()),
           "max_studies_sharing_one_trait": best,
           "decision": "NOT_FEASIBLE" if best < 8 else "FEASIBLE_EXPLORATORY",
           "reason": f"largest number of independent studies sharing one trait = {best} (< 8 required); source layer "
                     "raw_measurements is unverified legacy import; most timepoints are at harvest/terminal "
                     "(post-treatment, would not be an early predictor)",
           "data_needed": "verified early (pre-flowering / <=30 d after stress onset) leaf RWC, Fv/Fm, SPAD, proline, "
                          "Na+/K+ and MDA on the same SB and S arms of the yield studies"}
    write_json(OUT / "data" / "physiology_feasibility.json", rep)
    return rep


if __name__ == "__main__":
    print(main())
