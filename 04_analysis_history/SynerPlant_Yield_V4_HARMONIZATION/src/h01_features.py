"""H1 - harmonized representation of the intervention (pre-experiment information only).

Adds to the V3.1 ML file, without changing any existing column or row:
  * comp_*      multi-hot component flags (bacteria, AMF, other fungi, seaweed, humic, ...) parsed from the declared
                composition / microorganism / product text plus the curated class. A mixture gets several flags
                instead of one opaque COMBINATION class.
  * n_components, comp_living_microbe
  * log_n_arm   log of the mean replicate number of the two arms (design precision, known before the experiment)
  * cv2_t, cv2_c  squared coefficients of variation where SD is reported (used only to impute vi inside folds)
Nothing is derived from the outcome, so these columns can be computed once on the whole TRAIN file.
Post-treatment plant damage or physiology is NOT added (not available before an experiment).
"""
from __future__ import annotations
import re
import numpy as np, pandas as pd
from h00_common import snapshot_input, SNAPSHOT, DATA, OUT, write_json, now

COMP = {
    "comp_bacteria": (r"bacill|pseudomon|azospiril|azotobact|serratia|rhizob|streptomy|enterobact|paenibac|burkhold|"
                      r"\bpgpr\b|bacteri|klebsiell|arthrobact|lactobac|clostrid|herbaspir|acinetobact|methylobact|"
                      r"brevibac|microbacter|ochrobact|stenotroph|variovorax|kosakon", ["PGPR_BACTERIA"]),
    "comp_amf": (r"mycorrhiz|\bamf\b|glomus|rhizophag|funnelif|claroideo|intraradic|mosseae|etunicat|septoglom",
                 ["AMF"]),
    "comp_fungi_other": (r"trichoderm|piriformo|serendip|saccharomy|yeast(?! extract)|penicill|aspergill|beauveria|"
                         r"metarhiz|clonostach", ["BENEFICIAL_FUNGI_NON_AMF"]),
    "comp_seaweed": (r"seaweed|\balga|macroalga|microalga|kelp|ascophyll|ecklon|sargass|\bulva|laminar|fucus|"
                     r"spirulin|arthrospira|chlorella|macrocyst|durvill|fucoidan|alginate|alganic", ["SEAWEED_ALGAL_EXTRACT"]),
    "comp_humic": (r"humic|fulvic|humate|leonard", ["HUMIC_FULVIC"]),
    "comp_protein_aa": (r"amino acid|protein hydrol|peptide|hydrolys", ["PROTEIN_HYDROLYSATE_AMINO_ACIDS"]),
    "comp_chitosan": (r"chitosan|chitin|oligosacchar", ["CHITOSAN_BIOPOLYMERS"]),
    "comp_silicon": (r"silic|monosilic|\bsi\b|nano-?si", []),
    "comp_selenium": (r"selen|\bse\b", []),
    "comp_organic_amend": (r"compost|manure|biochar|vermicompost|dung|farmyard|olive pomace|straw", ["ORGANIC_AMENDMENT"]),
    "comp_hormone": (r"salicyl|jasmon|gibberell|auxin|\biaa\b|cytokinin|brassinost|abscisic|ethephon|strigol|kinetin",
                     ["PHYTOHORMONE_PGR"]),
    "comp_osmolyte_antiox": (r"melatonin|proline|betaine|trehalose|ascorb|glutathion|spermid|putrescin|polyamine|"
                             r"\bgaba\b|tocoph", ["SMALL_MOLECULE_OSMOLYTE_ANTIOXIDANT"]),
    "comp_botanical": (r"moringa|plant extract|botanical|leaf extract|licorice|garlic|pollen|aloe", ["BOTANICAL_EXTRACT"]),
    "comp_cell_free": (r"cell-?free|supernatant|filtrate|metabolite", ["CELL_FREE_MICROBIAL_DERIVED"]),
}
OTHER_INORGANIC = "INORGANIC_BENEFICIAL_ELEMENTS"
MIXTURE_CLASSES = {"COMBINATION_MULTI_CLASS", "MICROBIAL_CONSORTIUM_MIXED", "MICROBIAL_UNSPECIFIED"}
# flags that are set from text only when the curated class is a mixture (otherwise class flag only)
CONSTITUENT_ONLY = {"comp_protein_aa", "comp_hormone", "comp_osmolyte_antiox", "comp_botanical"}


def build():
    rec = snapshot_input()
    d = pd.read_csv(SNAPSHOT, low_memory=False)
    n0 = d.shape
    txt = (d.f_composition.fillna("") + " | " + d.f_microorganism.fillna("") + " | " + d.f_strain.fillna("") + " | "
           + d.context_product_name_all.fillna("")).str.lower()
    cls = d.biostimulant_class.fillna("")
    txt = txt.str.replace(r"no (si|silicon|se|selenium)", " ", regex=True)   # explicit negations
    mixture = cls.isin(MIXTURE_CLASSES)
    for col, (rx, classes) in COMP.items():
        hit = txt.str.contains(rx, regex=True)
        if col in CONSTITUENT_ONLY:     # in a single-class product these words describe its analysed constituents
            hit = hit & mixture
        d[col] = (hit | cls.isin(classes)).astype(int)
    # microbial-class rows with no parsed organism still contain a living microbe
    unk_mic = cls.isin(["MICROBIAL_UNSPECIFIED", "MICROBIAL_CONSORTIUM_MIXED"]) & \
        (d[["comp_bacteria", "comp_amf", "comp_fungi_other"]].sum(1) == 0)
    d["comp_microbe_unspecified"] = unk_mic.astype(int)
    inorg = (cls == OTHER_INORGANIC) & (d.comp_silicon + d.comp_selenium == 0)
    d["comp_inorganic_other"] = inorg.astype(int)
    flags = [c for c in d.columns if c.startswith("comp_")]
    d["n_components"] = d[flags].sum(1)
    d["comp_living_microbe"] = ((d.comp_bacteria + d.comp_amf + d.comp_fungi_other + d.comp_microbe_unspecified) > 0
                                & (d.comp_cell_free == 0)).astype(int)
    d["comp_none_parsed"] = (d["n_components"] == 0).astype(int)
    # design precision
    n_arm = pd.concat([d.n_t, d.n_c], axis=1).mean(1)
    d["log_n_arm"] = np.log(n_arm.where(n_arm > 0))
    d["cv2_t"] = (d.sd_t / d.mean_t.abs()).pow(2).where((d.sd_t > 0) & (d.mean_t.abs() > 0))
    d["cv2_c"] = (d.sd_c / d.mean_c.abs()).pow(2).where((d.sd_c > 0) & (d.mean_c.abs() > 0))
    assert d.shape[0] == n0[0]
    d.to_csv(DATA / "TRAIN_HARMONIZED.csv", index=False)

    rep = {"built_at": now(), "input": rec, "rows": int(len(d)), "studies": int(d.study_id.nunique()),
           "new_columns": flags + ["n_components", "comp_living_microbe", "comp_none_parsed", "log_n_arm", "cv2_t", "cv2_c"],
           "flag_rows": {c: int(d[c].sum()) for c in flags + ["comp_living_microbe", "comp_none_parsed"]},
           "flag_studies": {c: int(d.loc[d[c] == 1, "study_id"].nunique()) for c in flags},
           "n_components_dist": d.n_components.value_counts().sort_index().to_dict(),
           "combination_class_rows_resolved": int(((cls == "COMBINATION_MULTI_CLASS") & (d.n_components >= 1)).sum()),
           "combination_class_rows": int((cls == "COMBINATION_MULTI_CLASS").sum())}
    write_json(OUT / "h01_features_report.json", rep)
    # audit sheet: one line per distinct intervention text so the parsing can be checked by eye
    aud = d.assign(text=txt.str[:200]).drop_duplicates(["study_id", "text"])[
        ["study_id", "biostimulant_class", "text"] + flags + ["n_components"]]
    aud.to_csv(OUT / "h01_composition_parsing_audit.csv", index=False, encoding="utf-8-sig")
    return rep


if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=1, ensure_ascii=False))
