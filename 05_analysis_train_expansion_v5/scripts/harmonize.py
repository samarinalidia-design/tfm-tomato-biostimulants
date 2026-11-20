"""Rule-based harmonisation of free-text FEATURE columns (f_*) into compact categories.

All rules read only pre-treatment design descriptors (role FEATURE in feature_policy.csv,
plus the contrast design codes stress_code / bio_code). No outcome is used.
"""
import re
import numpy as np
import pandas as pd


def _txt(df, cols):
    out = pd.Series('', index=df.index)
    for c in cols:
        if c in df:
            out = out + ' | ' + df[c].astype(str).replace({'nan': '', 'None': ''})
    return out.str.lower().str.replace('_', ' ', regex=False)


# ---------------------------------------------------------------- du Jardin 2015 (7 categories)
DJ_RULES = [
    ('DJ_HUMIC_FULVIC', r'humic|fulvic|humate|leonardite|vermicompost tea|compost extract'),
    ('DJ_PROTEIN_N', r'protein hydroly|aminolevulin|\bala\b|amino ?acid|glutam|glycine ?betaine|peptide|collagen|\bproline\b|polyamine|spermidine|putrescine|\bgaba\b|melatonin'),
    ('DJ_SEAWEED_BOTANICAL', r'seaweed|ascophyllum|kelp|ecklonia|sargassum|ulva|algae|algal|microalga|chlorella|spirulina|arthrospira|dunaliella|cyanobacteri|plant extract|leaf extract|moringa|botanical|garlic|licorice|aloe|neem|propolis|tea extract|willow|pollen'),
    ('DJ_CHITOSAN_BIOPOLYMER', r'chitosan|chitin|oligosacchar|alginate|carrageenan|exopolysacch|\beps\b|polysacchar|biopolymer'),
    ('DJ_INORGANIC', r'silic|\bsi\b|selen|nanopartic|\bnps?\b|zinc|zno|potassium silicate|calcium silicate|cobalt|titanium|cerium|iodine|sulfur|sulphur|phosphite|\bnano'),
    ('DJ_BENEFICIAL_FUNGI', r'mycorrh|\bamf\b|glomus|funneliformis|rhizophagus|claroideoglomus|trichoderma|piriformospora|serendipita|endophytic fung|dark septate|\bdse\b|penicillium|aspergillus|fusarium oxysporum f|beauveria|metarhizium|fung|yeast|saccharomyces|\bscer\b'),
    ('DJ_BENEFICIAL_BACTERIA', r'pgpr|pgpb|(?<!cyano)bacteri|bacillus|pseudomonas|azotobacter|azospirillum|rhizobi|enterobacter|serratia|streptomyces|actinomyc|burkholderia|paenibacillus|arthrobacter|citrobacter|klebsiella|acc deaminase|rhizobacter|\bksm|solubiliz'),
]
DJ_OTHER = r'biochar|manure|compost|hormone|gibberell|auxin|cytokinin|salicyl|jasmon|brassino|sucrose|trehalose|vinasse|wood vinegar|smoke|ozone|uv|magnetic|plasma|hydrogen|nitric oxide|h2s|strigol|karrikin|ascorbic|tocoph|glutathione|thidiazuron|\btdz|regulator|\bnaa\b|nitrophenol|\bsa\d|salicyl'
DJ_CATS = [c for c, _ in DJ_RULES]
DJ_MICROBIAL = r'microbial|probiotic|endophyt|inoculant|consorti'


def dujardin(df):
    # the curated class label decides first; composition / organism text is only a fallback
    t1 = _txt(df, ['f_biostimulant_class', 'bio_code'])
    t = _txt(df, ['f_biostimulant_class', 'bio_code', 'f_microorganism', 'f_composition', 'f_strain'])
    h1 = pd.DataFrame({c: t1.str.contains(p, regex=True) for c, p in DJ_RULES}, index=df.index)
    h2 = pd.DataFrame({c: t.str.contains(p, regex=True) for c, p in DJ_RULES}, index=df.index)
    use1 = h1.any(axis=1)
    hits = h2.copy(); hits[use1] = h1[use1]
    # microbial strain names override generic matches of the word "fung"/"bacteri" in mixed products
    other = t.str.contains(DJ_OTHER, regex=True)
    n = hits.sum(axis=1)
    primary = pd.Series('DJ_OTHER_NON_DUJARDIN', index=df.index)
    primary[n == 1] = hits[n == 1].idxmax(axis=1)
    primary[n >= 2] = 'DJ_MIXTURE'
    primary[(n == 0) & ~other] = 'DJ_UNCLASSIFIED'
    primary[(n == 0) & ~other & t.str.contains(DJ_MICROBIAL, regex=True)] = 'DJ_MICROBIAL_UNSPECIFIED'
    hits.columns = ['h_' + c.lower() for c in hits.columns]
    return primary, hits.astype(int)


# ---------------------------------------------------------------- dose
def dose(df):
    unit = _txt(df, ['f_dose_unit'])
    d = pd.to_numeric(df['f_dose'], errors='coerce')
    cls = pd.Series('UNKNOWN', index=df.index)
    val = pd.Series(np.nan, index=df.index)
    rules = [
        ('CFU', r'cfu|cells|spores|propagul|conidia', 1.0),
        ('MOLAR_mM', r'\bmm\b|mmol', 1.0),
        ('MOLAR_uM', r'\bµm\b|\bum\b|μm|umol|µmol|μmol', 1e-3),
        ('MASS_CONC_gL', r'mg ?l|mg/l|mg l-1|ppm|mg ?/ ?l|mg dm', 1e-3),
        ('MASS_CONC_gL', r'g ?l-1|g/l|g l|g ?/ ?l', 1.0),
        ('VOL_CONC_mLL', r'ml ?l|ml/l|ml l-1|cc/l|ml per l', 1.0),
        ('PERCENT', r'%|percent', 10.0),  # 1 % ~ 10 g/L or 10 mL/L
        ('PER_PLANT_OR_POT', r'per plant|plant-1|/plant|per pot|pot-1|/pot|per seedling', 1.0),
        ('PER_AREA', r'ha-1|/ha|per ha|m-2|/m2|kg ha', 1.0),
        ('PER_SOIL_MASS', r'kg-1|/kg|per kg|g-1 soil|/g soil', 1.0),
    ]
    for name, pat, mult in rules:
        m = unit.str.contains(pat, regex=True) & (cls == 'UNKNOWN') & d.notna()
        cls[m] = name
        val[m] = d[m] * mult
    # concentration classes share one canonical scale (approx. g/L ~ mL/L)
    cls_h = cls.replace({'VOL_CONC_mLL': 'CONC_gL_or_mLL', 'MASS_CONC_gL': 'CONC_gL_or_mLL', 'PERCENT': 'CONC_gL_or_mLL'})
    logd = np.log10(val.where(val > 0))
    cls_h[d.isna()] = 'NOT_REPORTED'
    return cls_h, logd


# ---------------------------------------------------------------- stress
STRESS_RULES = [
    ('NONE', r'^none$'),
    ('SALINITY', r'salin|nacl|salt|\bec\d|sodic'),
    ('DROUGHT', r'drought|water deficit|deficit irrig|\bwd\b|wd_|\bfc\b|\d+fc|water stress|withhold|rainfed|\bdi_|\bdi\b|osmotic|peg'),
    ('HEAT', r'heat|high temp|\bht\b|ht_'),
    ('COLD', r'cold|chill|low temp|\blt_|\blt\b|frost'),
    ('NUTRIENT', r'nutrient|deficien|low n|n deficiency|pdef|\bp def|low p|nitrogen|phosph|potassium def'),
    ('HEAVY_METAL', r'cadmium|\bcd\b|lead|\bpb\b|arsenic|chromium|nickel|copper|heavy metal|boron tox|alumin'),
    ('BIOTIC', r'nematode|meloidogyne|rkn|minc|fusarium|ralstonia|botrytis|phytophthora|rhizoctonia|alternaria|pathogen|virus|tylcv|wilt|pythium|cmm|clavibacter|xanthomonas|pseudomonas syringae|insect|whitefly|tuta|larva|replant|disease'),
    ('ALKALINITY_CALCAREOUS', r'alkalin|calcare|bicarbonate|high ph'),
    ('LIGHT_UV_OZONE', r'shade|low light|uv|ozone'),
    ('FLOOD_HYPOXIA', r'flood|waterlog|hypox'),
]


def stress(df):
    code = df['stress_code'].astype(str).str.lower()
    t = code + ' | ' + _txt(df, ['f_stress_type'])
    cls = pd.Series('OTHER', index=df.index)
    for name, pat in STRESS_RULES:
        src = code if name == 'NONE' else t
        m = src.str.contains(pat, regex=True) & (cls == 'OTHER')
        cls[m] = name
    cls[code == 'none'] = 'NONE'
    # --- intensity, design based only (no outcome)
    sc = df['stress_code'].astype(str)
    nacl = pd.to_numeric(df['f_nacl_mm'], errors='coerce')
    m_code = pd.to_numeric(sc.str.extract(r'(?i)nacl[_ ]?(\d+(?:\.\d+)?)\s*mm', expand=False), errors='coerce')
    nacl = nacl.fillna(m_code)
    ec = pd.to_numeric(df['f_ec_irrigation_ds_m'], errors='coerce')
    ec = ec.where(df['f_ec_irrigation_ds_m_unit'].astype(str).str.contains('ds', case=False))
    ec_code = pd.to_numeric(sc.str.extract(r'(?i)ec[_ ]?(\d+(?:\.\d+)?)', expand=False), errors='coerce')
    ec = ec.fillna(ec_code)
    pct = pd.to_numeric(sc.str.extract(r'(?i)nacl[_ ]?(\d+(?:\.\d+)?)\s*pct', expand=False), errors='coerce')  # % NaCl w/v
    nacl_eq = nacl.copy()
    nacl_eq = nacl_eq.fillna(ec * 10.0)                 # ~10 mM NaCl per dS/m
    nacl_eq = nacl_eq.fillna(pct * 171.1)               # 1 % w/v NaCl = 171 mM
    fc = pd.to_numeric(df['f_field_capacity_pct'], errors='coerce')
    fc_code = pd.to_numeric(sc.str.extract(r'(?i)(\d+(?:\.\d+)?)\s*(?:pct)?_?fc', expand=False), errors='coerce')
    fc = fc_code.fillna(fc)
    di = pd.to_numeric(sc.str.extract(r'(?i)di_?(\d+)\s*pct', expand=False), errors='coerce')
    fc = fc.fillna(di)
    inten = pd.Series(np.nan, index=df.index)
    sal = cls == 'SALINITY'
    inten[sal] = (nacl_eq[sal] / 200.0).clip(0, 2)       # 200 mM NaCl ~ "severe" = 1
    dr = cls == 'DROUGHT'
    inten[dr] = (1 - fc[dr] / 100.0).clip(0, 1)
    inten[cls == 'NONE'] = 0.0
    # within-study relative rank of the stress level (design only)
    lvl = pd.Series(np.where(sal, nacl_eq, np.where(dr, 100 - fc, np.nan)), index=df.index)
    rank = lvl.groupby([df['study_id'], cls]).rank(method='dense')
    mx = rank.groupby([df['study_id'], cls]).transform('max')
    rel_rank = (rank / mx).where(mx > 0)
    rel_rank[cls == 'NONE'] = 0.0
    return cls, inten, rel_rank, nacl_eq


# ---------------------------------------------------------------- crop / system / route groups
def crop(df):
    t = _txt(df, ['f_fruit_type', 'f_cultivar'])
    g = pd.Series('UNSPECIFIED', index=df.index)
    for name, pat in [('CHERRY_COCKTAIL', r'cherry|cerasiforme|cocktail|grape tomato|micro ?tom|microtom|mini|small'),
                      ('PROCESSING', r'processing|industrial|heinz|h-\d|ug ?\d|roma|san marzano|plum|oval|square|saladette|pear'),
                      ('BEEF_LARGE', r'beef|large|marmande|cuore')]:
        m = t.str.contains(pat, regex=True) & (g == 'UNSPECIFIED')
        g[m] = name
    g[(g == 'UNSPECIFIED') & df['f_fruit_type'].notna() & (df['f_fruit_type'].astype(str) != 'nan')] = 'ROUND_FRESH_MARKET'
    hab = _txt(df, ['f_growth_habit'])
    habit = np.select([hab.str.contains('semi'), hab.str.contains('indetermin'), hab.str.contains('determin|dwarf')],
                      ['SEMI_DETERMINATE', 'INDETERMINATE', 'DETERMINATE'], 'UNSPECIFIED')
    gt = _txt(df, ['f_genotype_type', 'f_cultivar'])
    hybrid = np.select([gt.str.contains(r'hybrid|f1'), gt.str.contains(r'cultivar|landrace|open|variety|line|wild')], ['HYBRID', 'OP_CULTIVAR_LINE'], 'UNSPECIFIED')
    return g, pd.Series(habit, index=df.index), pd.Series(hybrid, index=df.index)


def system(df):
    t = _txt(df, ['f_system'])
    s = np.select([t.str.contains(r'growth chamber|climate chamber|phytotron|controlled environment|growth room|incubator'),
                   t.str.contains(r'hydropon|soilless|nft|rockwool|coco|perlite|nutrient film|aeropon'),
                   t.str.contains(r'greenhouse|glasshouse|polyhouse|net ?house|screenhouse|tunnel|shade'),
                   t.str.contains(r'field|plot|farm')], ['CHAMBER', 'SOILLESS', 'GREENHOUSE', 'FIELD'], 'UNSPECIFIED')
    pot = t.str.contains(r'pot|bag|container|tray').astype(int)
    r = _txt(df, ['f_route', 'bio_code'])
    route = np.select([r.str.contains(r'foliar|spray|leaf'), r.str.contains(r'seed|priming|coat'),
                       r.str.contains(r'dip|soak|root dip|immers'), r.str.contains(r'fertig|irrigat|nutrient solution|hydropon'),
                       r.str.contains(r'drench|soil|substrate|inocul|incorpor|sowing|planting hole|mixed|amend')],
                      ['FOLIAR', 'SEED', 'ROOT_DIP', 'FERTIGATION', 'SOIL_SUBSTRATE'], 'UNSPECIFIED')
    return pd.Series(s, index=df.index), pot, pd.Series(route, index=df.index)


def harmonize(df):
    out = pd.DataFrame(index=df.index)
    out['h_dujardin'], hits = dujardin(df)
    out = out.join(hits)
    out['h_dose_class'], out['h_log10_dose'] = dose(df)
    ld = out['h_log10_dose']
    grp = [df['study_id'], out['h_dose_class']]
    mx, mn = ld.groupby(grp).transform('max'), ld.groupby(grp).transform('min')
    out['h_dose_rel_study'] = ((ld - mn) / (mx - mn)).where(mx > mn)
    out['h_stress_class'], out['h_stress_intensity'], out['h_stress_rank_study'], out['h_nacl_equiv_mm'] = stress(df)
    out['h_crop_group'], out['h_growth_habit'], out['h_hybrid'] = crop(df)
    out['h_system'], out['h_potted'], out['h_route'] = system(df)
    out['h_n_applications'] = pd.to_numeric(df['f_n_applications'], errors='coerce')
    return out
