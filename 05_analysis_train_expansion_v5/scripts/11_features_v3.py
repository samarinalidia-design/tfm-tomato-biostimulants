"""Features v3: deterministic recoding of the raw free-text FEATURE columns into numeric / low-cardinality
variables (training tables only; the database freeze is not touched).

Sources: only columns with role FEATURE in feature_policy.csv (pre-treatment descriptors). The target is NOT
used here; target-based encodings are computed later inside CV training folds (12_round5_v3.py).

Blocks (prefix h3_):
  agent      genus-level multi-hot (bacillus, pseudomonas, azotobacter/azospirillum, trichoderma, AMF, rhizobia,
             streptomyces, other bacteria, yeast) + active-ingredient multi-hot (seaweed, humic, protein/amino,
             chitosan, silicon, selenium, phytohormone-like, nano) + counts (n taxa, n actives)
  route      multi-hot (foliar, soil/drench, seed, root dip, fertigation, substrate mixing) + n routes
  n_apps     number of applications: numeric f_n_applications, else parsed from f_frequency text (flagged)
  stress     multi-hot (salinity, drought, heat, cold, nutrient, biotic, metal, other) + combined + ambient flag
  phase      ordinal application / stress-onset phase (seed 0 ... fruiting 5) and their difference
  soil       sand % / clay % (printed numbers, else USDA texture-class centroid; flagged)
  fert       none / nutrient-solution flags, N kg/ha parsed
  season     start month (sin, cos), warm-season flag, experiment year
  site       |latitude| (printed, else country centroid; flagged), arid-climate flag, region dummies
  genotype   hybrid, declared stress-tolerant / -sensitive, small-fruited / processing type
  clean keys lower-case cleaned category keys for in-fold target / frequency encoding
             (genus_main, country, cultivar, class_key)
"""
import re, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC, RES = ROOT / 'data' / 'processed', ROOT / 'results'


NA_STR = {'', 'nan', 'none', 'null', 'na', 'n/a', 'not reported', 'not stated', 'unspecified'}


def t(x):
    if pd.isna(x):
        return ''
    s = str(x).strip().lower()
    return '' if s in NA_STR else s


def isna_txt(col):
    return col.map(t) == ''


def has(s, pat):
    return s.str.contains(pat, regex=True, na=False).astype(int)


GENUS = {'bacillus': r'bacillus|b\. ?subtilis|b\. ?amylo', 'pseudomonas': r'pseudomonas|p\. ?fluoresc|p\. ?putida',
         'azoto_azospir': r'azotobacter|azospirillum', 'trichoderma': r'trichoderma',
         'amf': r'glomus|rhizophagus|funneliformis|mycorrhiz|\bamf\b|claroideo|gigaspora|acaulospora',
         'rhizobia': r'rhizobium|bradyrhizob|sinorhizob|mesorhizob', 'streptomyces': r'streptomyces|actinomyc',
         'other_bacteria': r'enterobacter|citrobacter|serratia|burkholderia|paenibacillus|klebsiella|arthrobacter|'
                           r'stenotrophomonas|achromobacter|bacterium|bacteria|pgpr|rhizobacter|cyanobacter|spirulina|nostoc',
         'yeast': r'yeast|saccharomyces'}
ACTIVE = {'seaweed': r'seaweed|ascophyllum|ecklonia|kelp|alga|sargassum|ulva|kappaphycus',
          'humic': r'humic|fulvic|humate|leonardite', 'protein_amino': r'amino|protein|hydrolys|peptide|glycine betaine',
          'chitosan': r'chitosan|chitin', 'silicon': r'silic|\bsi\b|sio2', 'selenium': r'selen|\bse\b|na2seo',
          'hormone_like': r'salicyl|melatonin|jasmon|brassino|gibberel|auxin|cytokinin|strigolact|proline|putrescine|spermidine|polyamine',
          'botanical_extract': r'extract|moringa|plant-derived|botanical|vermicompost|compost tea',
          'nano': r'nano'}
ROUTE = {'foliar': r'foliar|spray|leaf', 'soil_drench': r'drench|soil appl|soil amend|to the soil|soil-appl|irrigation water|applied to soil|pot soil',
         'seed': r'seed (treat|coat|immers|soak|prim|inocul|dress)|seed,|seeds? before|before sowing|priming|seed immersion|seed soak',
         'root_dip': r'root dip|root soak|dipp|root immers|seedling root', 'fertigation': r'fertigat|drip|nutrient solution|hydropon',
         'substrate_mix': r'mix|incorporat|placement|placed|substrate|planting hole|transplant hole|inoculum placed'}
STRESS = {'salinity': r'salin|nacl|salt|seawater|sodic', 'drought': r'drought|water deficit|water stress|withhold|deficit irrig|reduced water|% ?fc|field capacity|peg',
          'heat': r'heat|high temperature|thermo', 'cold': r'cold|chill|low temperature|frost',
          'nutrient': r'nutrient|phosph|nitrogen|low-p|low n|deficien|limitation',
          'biotic': r'pathogen|nematode|fusarium|meloidogyne|pythium|disease|fungal|virus|blight|wilt',
          'metal': r'cadmium|\bcd\b|lead|arsenic|heavy metal|chromium|nickel|zinc toxic|copper toxic', 'other': r'flood|waterlog|ozone|uv|alkalin|boron'}
PHASE_ORD = {'SEED': 0, 'NURSERY_SEEDLING': 1, 'TRANSPLANT': 2, 'VEGETATIVE': 3, 'FLOWERING': 4, 'FRUITING': 5, 'MULTIPLE_STAGES': 2.5}
TEXTURE = [('loamy sand', 82, 6), ('sandy clay loam', 60, 27), ('sandy clay', 52, 42), ('sandy loam', 65, 10),
           ('silty clay loam', 10, 34), ('silty clay', 7, 47), ('silt loam', 20, 15), ('silty loam', 20, 15),
           ('clay loam', 33, 34), ('loam', 40, 20), ('clay', 20, 60), ('sand', 92, 5), ('silt', 7, 6)]
COUNTRY = {'albania': (41.2, 'EUR'), 'bangladesh': (23.7, 'SAS'), 'belgium': (50.5, 'EUR'), 'brazil': (10.0, 'AMS'),
           'canada': (50.0, 'AMN'), 'chile': (33.0, 'AMS'), 'china': (33.0, 'EAS'), 'colombia': (4.0, 'AMS'),
           'denmark': (56.0, 'EUR'), 'egypt': (28.0, 'MENA'), 'france': (46.0, 'EUR'), 'germany': (51.0, 'EUR'),
           'greece': (39.0, 'EUR'), 'hungary': (47.2, 'EUR'), 'india': (22.0, 'SAS'), 'iran': (32.0, 'MENA'),
           'israel': (31.5, 'MENA'), 'italy': (42.0, 'EUR'), 'japan': (36.0, 'EAS'), 'mexico': (23.0, 'AMN'),
           'morocco': (32.0, 'MENA'), 'nigeria': (9.0, 'AFR'), 'oman': (21.0, 'MENA'), 'pakistan': (30.0, 'SAS'),
           'peru': (10.0, 'AMS'), 'korea': (36.5, 'EAS'), 'romania': (46.0, 'EUR'), 'saudi': (24.0, 'MENA'),
           'south africa': (29.0, 'AFR'), 'spain': (40.0, 'EUR'), 'taiwan': (23.7, 'EAS'), 'thailand': (15.5, 'SEA'),
           'trinidad': (10.5, 'AMN'), 'turkey': (39.0, 'MENA'), 'türkiye': (39.0, 'MENA'), 'usa': (38.0, 'AMN'),
           'uzbekistan': (41.0, 'CAS'), 'tunisia': (34.0, 'MENA'), 'algeria': (28.0, 'MENA'), 'iraq': (33.0, 'MENA'),
           'jordan': (31.0, 'MENA'), 'poland': (52.0, 'EUR'), 'portugal': (39.5, 'EUR'), 'australia': (25.0, 'OCE')}
ARID = {'egypt', 'oman', 'saudi', 'iran', 'israel', 'morocco', 'pakistan', 'tunisia', 'algeria', 'iraq', 'jordan', 'uzbekistan'}
MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
WORDNUM = {'once': 1, 'single': 1, 'one': 1, 'twice': 2, 'two': 2, 'thrice': 3, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
           'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'twelve': 12}


def parse_napps(s):
    s = t(s)
    if not s:
        return np.nan
    m = re.search(r'(\d+)\s*(?:times|applications|sprays|doses|drenches)', s)
    if m:
        return float(m.group(1))
    m = re.search(r'(?:weekly|once a week|every week)[^.;]*?(?:for\s+)?(\d+|' + '|'.join(WORDNUM) + r')\s*weeks', s)
    if m:
        g = m.group(1); return float(g) if g.isdigit() else float(WORDNUM[g])
    for w, n in sorted(WORDNUM.items(), key=lambda kv: -kv[1]):
        if re.search(rf'\b{w}\b', s) and re.search(r'time|appl|spray|inocul|dose|drench|\bonce\b|\btwice\b|single|thrice', s):
            return float(n)
    if re.search(r'at sowing|at the time of sowing|pre-sowing|before sowing|at transplant', s):
        return 1.0
    return np.nan


def parse_soil(s):
    s = t(s)
    if not s:
        return np.nan, np.nan, 'MISSING'
    sa = re.search(r'sand[^0-9;]{0,12}(\d+(?:\.\d+)?)\s*%?|(\d+(?:\.\d+)?)\s*%\s*sand', s)
    cl = re.search(r'clay[^0-9;]{0,12}(\d+(?:\.\d+)?)\s*%?|(\d+(?:\.\d+)?)\s*%\s*clay', s)
    if sa and cl:
        f = lambda m: float(m.group(1) or m.group(2))
        a, c = f(sa), f(cl)
        if 0 <= a <= 100 and 0 <= c <= 100:
            return a, c, 'PRINTED_PCT'
    for name, a, c in TEXTURE:
        if name in s:
            return float(a), float(c), 'TEXTURE_CLASS_CENTROID'
    return np.nan, np.nan, 'UNPARSED'


def parse_season(s):
    s = t(s)
    if not s:
        return np.nan, np.nan, np.nan
    yrs = [int(y) for y in re.findall(r'\b(19[89]\d|20[0-2]\d)\b', s)]
    pos = [(s.find(m), i + 1) for i, m in enumerate(MONTHS) if s.find(m) >= 0]
    mon = min(pos)[1] if pos else ({'spring': 4, 'summer': 7, 'autumn': 10, 'fall': 10, 'winter': 1}.get(
        next((w for w in ('spring', 'summer', 'autumn', 'fall', 'winter') if w in s), ''), np.nan))
    warm = 1.0 if re.search(r'summer|jul|aug|jun', s) else (0.0 if re.search(r'winter|dec|jan|feb', s) else np.nan)
    return mon, (min(yrs) if yrs else np.nan), warm


def build(df):
    x = df.copy()
    agent = (x.f_biostimulant_class.map(t) + ' | ' + x.f_composition.map(t) + ' | ' + x.f_microorganism.map(t) + ' | ' + x.f_strain.map(t))
    agent_s = pd.Series(agent.values, index=x.index)
    for k, p in GENUS.items():
        x[f'h3_taxon_{k}'] = has(agent_s, p)
    for k, p in ACTIVE.items():
        x[f'h3_active_{k}'] = has(agent_s, p)
    # inorganic Si/Se keyword can fire on microbe strain codes; restrict to non-living or explicit class text
    specific = [f'h3_taxon_{k}' for k in GENUS if k != 'other_bacteria']
    x['h3_taxon_other_bacteria'] = ((x.h3_taxon_other_bacteria == 1) & (x[specific].sum(1) == 0)).astype(int)  # generic word only if no named genus
    x['h3_n_taxa'] = x[[f'h3_taxon_{k}' for k in GENUS]].sum(1)
    x['h3_n_actives'] = x[[f'h3_active_{k}' for k in ACTIVE]].sum(1)
    tax = x[[f'h3_taxon_{k}' for k in GENUS]]
    x['h3_genus_main'] = np.where(x.h3_n_taxa == 0, np.where(x.h3_n_actives > 0, 'NON_MICROBIAL', 'UNSPECIFIED'),
                                  np.where(x.h3_n_taxa > 1, 'MULTI_TAXA', tax.idxmax(axis=1).str.replace('h3_taxon_', '')))
    route = x.f_route.map(t) + ' | ' + x.f_application_stage.map(t)
    route = pd.Series(route.values, index=x.index)
    for k, p in ROUTE.items():
        x[f'h3_route_{k}'] = has(route, p)
    x['h3_n_routes'] = x[[f'h3_route_{k}' for k in ROUTE]].sum(1)
    parsed = x.f_frequency.map(parse_napps)
    nap = pd.to_numeric(x.f_n_applications, errors='coerce')
    x['h3_n_applications'] = nap.fillna(parsed)
    x['h3_n_applications_source'] = np.where(nap.notna(), 'NUMERIC_FIELD', np.where(parsed.notna(), 'PARSED_FREQUENCY_TEXT', 'MISSING'))
    x['h3_log_n_applications'] = np.log1p(x.h3_n_applications.clip(upper=60))
    st = pd.Series(x.f_stress_type.map(t).values, index=x.index)
    nost = (x.is_B_vs_C == 1)
    for k, p in STRESS.items():
        x[f'h3_stress_{k}'] = np.where(nost, 0, has(st, p))
    x['h3_n_stresses'] = x[[f'h3_stress_{k}' for k in STRESS]].sum(1)
    x['h3_stress_combined'] = (x.h3_n_stresses >= 2).astype(int)
    x['h3_stress_ambient'] = np.where(nost, 0, has(st, r'ambient|natural|season|field condition|not experimental'))
    pa = x.h2_application_phase.map(PHASE_ORD); ps = x.h2_stress_onset_phase.map(PHASE_ORD)
    x['h3_application_phase_ord'] = pa
    x['h3_stress_onset_phase_ord'] = ps
    x['h3_phase_app_minus_stress'] = pa - ps                     # <0: applied before stress phase
    soil = x.f_soil_texture.map(parse_soil)
    x['h3_sand_pct'] = [a for a, _, _ in soil]; x['h3_clay_pct'] = [c for _, c, _ in soil]
    x['h3_soil_texture_source'] = [s for _, _, s in soil]
    fe = pd.Series(x.f_fertilization.map(t).values, index=x.index)
    x['h3_fert_none'] = has(fe, r'^none|no fertili|without fertili|not fertili')
    x['h3_fert_nutrient_solution'] = has(fe, r'hoagland|steiner|nutrient solution|fertigat|half-strength|murashige')
    x['h3_fert_n_kg_ha'] = fe.str.extract(r'(\d+(?:\.\d+)?)\s*kg\s*n\b', expand=False).astype(float)
    x['h3_fert_reported'] = (~isna_txt(x.f_fertilization)).astype(float)
    se = x.f_season.map(parse_season)
    mon = pd.Series([m for m, _, _ in se], index=x.index)
    x['h3_start_month_sin'] = np.sin(2 * np.pi * mon / 12); x['h3_start_month_cos'] = np.cos(2 * np.pi * mon / 12)
    x['h3_experiment_year'] = [y for _, y, _ in se]
    x['h3_warm_season'] = [w for _, _, w in se]
    ck = x.f_country.map(t).replace('', np.nan).str.extract(r'^\s*([a-zü ]+?)(?:\s*[\(;,]|$)', expand=False).str.strip()
    ck = ck.replace({'republic of korea': 'korea', 'south korea': 'korea', 'türkiye': 'turkey', 'saudi arabia': 'saudi'})
    ck = ck.map(lambda c: next((k for k in COUNTRY if isinstance(c, str) and c.startswith(k)), c if isinstance(c, str) and c else np.nan))
    x['h3_country'] = ck.fillna('UNSPECIFIED')
    lat_p = pd.to_numeric(x.f_latitude, errors='coerce').abs()
    lat_c = ck.map(lambda c: COUNTRY.get(c, (np.nan, None))[0] if isinstance(c, str) else np.nan)
    x['h3_abs_latitude'] = lat_p.fillna(lat_c)
    x['h3_latitude_source'] = np.where(lat_p.notna(), 'PRINTED', np.where(lat_c.notna(), 'COUNTRY_CENTROID', 'MISSING'))
    x['h3_arid_country'] = np.where(ck.isna(), np.nan, ck.isin(ARID).astype(float))
    x['h3_region'] = ck.map(lambda c: COUNTRY.get(c, (None, 'OTHER'))[1] if isinstance(c, str) else 'UNSPECIFIED')
    gt = pd.Series((x.f_genotype_type.map(t) + ' | ' + x.f_cultivar.map(t)).values, index=x.index)
    x['h3_hybrid'] = np.where(isna_txt(x.f_genotype_type) & isna_txt(x.f_cultivar), np.nan, has(gt, r'hybrid|\bf1\b').astype(float))
    x['h3_declared_tolerance'] = np.select([gt.str.contains(r'toleran|resistant', na=False), gt.str.contains(r'sensitiv|suscept', na=False)], [1.0, -1.0], 0.0)
    ft = pd.Series(x.f_fruit_type.map(t).values, index=x.index)
    x['h3_small_fruited'] = np.where(isna_txt(x.f_fruit_type), np.nan, has(ft, r'cherry|grape|cerasiform|cocktail|small').astype(float))
    x['h3_processing_type'] = np.where(isna_txt(x.f_fruit_type), np.nan, has(ft, r'process|canning|plum|saladette|roma|oval').astype(float))
    x['h3_cultivar_key'] = x.f_cultivar.map(t).replace('', np.nan).str.replace(r'\(.*?\)', '', regex=True).str.replace(r'[^a-z0-9 ]', ' ', regex=True) \
        .str.split(r'\s{2,}|;').str[0].str.strip().replace('', 'UNSPECIFIED').fillna('UNSPECIFIED')
    x['h3_class_key'] = x.f_biostimulant_class.map(t).replace('', np.nan).str.replace(r'\(.*?\)', '', regex=True).str.replace(r'[^a-z ]', ' ', regex=True) \
        .str.split().str[:3].str.join(' ').replace('', 'UNSPECIFIED').fillna('UNSPECIFIED')
    # one text field for in-fold TF-IDF/SVD
    x['h3_text_all'] = (agent + ' | ' + route + ' | ' + x.f_system.map(t) + ' | ' + x.f_substrate.map(t) + ' | ' + st)
    return x


if __name__ == '__main__':
    audit = []
    for name in ('train_yield', 'train_dry_biomass'):
        d = build(pd.read_parquet(PROC / f'{name}_v2.parquet'))
        d.to_parquet(PROC / f'{name}_v3.parquet', index=False)
        d.drop(columns=['h3_text_all']).to_csv(PROC / f'{name}_v3.csv', index=False)
        dd = d[d.in_default == 1]
        for c in [c for c in d.columns if c.startswith('h3_') and c != 'h3_text_all']:
            s = dd[c]
            if pd.api.types.is_numeric_dtype(s):
                nz = (s.fillna(0) != 0)
                audit.append(dict(table=name, column=c, kind='numeric', non_missing=round(s.notna().mean(), 3),
                                  nonzero_rows=int(nz.sum()), nonzero_studies=int(dd[nz].study_id.nunique()), levels=s.nunique()))
            else:
                ns = dd.groupby(s.astype(str)).study_id.nunique()
                audit.append(dict(table=name, column=c, kind='category', non_missing=round((~s.astype(str).isin(['UNSPECIFIED', 'MISSING', 'nan'])).mean(), 3),
                                  levels=s.nunique(), levels_ge3_studies=int((ns >= 3).sum()),
                                  top=' | '.join(f'{k}:{v}' for k, v in s.value_counts().head(5).items())))
    A = pd.DataFrame(audit)
    A.to_csv(RES / 'features_v3_audit.csv', index=False)
    # dictionary
    dic = pd.read_csv(PROC / 'new_columns_dictionary.csv')
    new = [c for c in A.column.unique() if c not in set(dic.iloc[:, 0])]
    rows = [{dic.columns[0]: c, dic.columns[1]: 'v3 recoding of raw FEATURE text (scripts/11_features_v3.py); see module docstring for block'}
            for c in new]
    pd.concat([dic, pd.DataFrame(rows)], ignore_index=True).to_csv(PROC / 'new_columns_dictionary.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 90)
    print(A.to_string())
