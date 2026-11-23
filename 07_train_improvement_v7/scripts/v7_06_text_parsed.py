"""V7 step 6: the raw free-text fields contribute nothing because no level reaches 3 studies (v7_03). Does a PROPER encoding
of the same text carry signal?  Controlled test, same data (V6) / engine / folds / evaluation rows / bootstrap as v7_03.

Reference REF_CLEAN = REF without the raw text categories and unit strings (text dropped).
Each block adds the parsed, study-transferable version of one text field (built in V5 by 07_features_v2 / 11_features_v3
from the same text; parsing uses no target information):
  PRODUCT   class / composition / microorganism / strain -> taxon flags (Bacillus, Pseudomonas, AMF, Trichoderma ...),
            active-ingredient flags (seaweed, humic, amino acids, chitosan, Si, Se ...), counts, main genus
  GENOTYPE  cultivar / fruit type -> small-fruited, processing type, hybrid, declared tolerance
  SEASON    season text -> start month (sin, cos), experiment year, warm season
  SOIL_FERT soil texture / fertilisation -> sand %, clay %, no fertiliser, nutrient solution, N kg/ha, reported
  TIMING    application stage / stress onset text -> phase ordinals, application-minus-stress phase
  ALL_PARSED      all blocks;  ALL_PARSED_TE  + in-fold target encoding of class/cultivar/country/genus keys (V5 K=5)
  ALL_PARSED_TFIDF  + in-fold TF-IDF/SVD of the concatenated text (V5 round 5)
Models: Ridge for every set; RF for REF_CLEAN and ALL_PARSED.
"""
import sys, pathlib, time
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
EP = sys.argv[1] if len(sys.argv) > 1 else 'yield'
sys.argv = [sys.argv[0], EP]
sys.path.insert(0, str(HERE))
import v7_03_ablation as A

H, cv, r5 = A.H, A.cv, A.r5
TEXT = [c for g, cols in A.GROUPS.items() if 'text' in g or 'unit' in g for c in cols]
CLEAN = [c for c in A.ALLF if c not in TEXT]
BLOCKS = {
    'PRODUCT': ['h3_taxon_bacillus', 'h3_taxon_pseudomonas', 'h3_taxon_azoto_azospir', 'h3_taxon_trichoderma', 'h3_taxon_amf',
                'h3_taxon_rhizobia', 'h3_taxon_streptomyces', 'h3_taxon_other_bacteria', 'h3_taxon_yeast', 'h3_active_seaweed',
                'h3_active_humic', 'h3_active_protein_amino', 'h3_active_chitosan', 'h3_active_silicon', 'h3_active_selenium',
                'h3_active_hormone_like', 'h3_active_botanical_extract', 'h3_active_nano', 'h3_n_taxa', 'h3_n_actives', 'h3_genus_main'],
    'GENOTYPE': ['h3_small_fruited', 'h3_processing_type', 'h3_hybrid', 'h3_declared_tolerance'],
    'SEASON': ['h3_start_month_sin', 'h3_start_month_cos', 'h3_experiment_year', 'h3_warm_season'],
    'SOIL_FERT': ['h3_sand_pct', 'h3_clay_pct', 'h3_fert_none', 'h3_fert_nutrient_solution', 'h3_fert_n_kg_ha', 'h3_fert_reported'],
    'TIMING': ['h2_application_phase', 'h2_stress_onset_phase', 'h3_application_phase_ord', 'h3_stress_onset_phase_ord',
               'h3_phase_app_minus_stress'],
}
CAT_PARSED = {'h3_genus_main', 'h2_application_phase', 'h2_stress_onset_phase'}
ALL_PARSED = CLEAN + [c for b in BLOCKS.values() for c in b]
CONFIGS = [('REF_CLEAN (text dropped)', CLEAN, [], False, ['RIDGE', 'RF'])]
CONFIGS += [(f'+ {b}', CLEAN + cols, [], False, ['RIDGE']) for b, cols in BLOCKS.items()]
CONFIGS += [('ALL_PARSED', ALL_PARSED, [], False, ['RIDGE', 'RF']),
            ('ALL_PARSED_TE', ALL_PARSED, r5.TE_KEYS, False, ['RIDGE']),
            ('ALL_PARSED_TFIDF', ALL_PARSED, [], True, ['RIDGE'])]


def run(seed):
    folds = cv.make_folds(H.SCHEME, seed)
    src = H.rows('V6')
    P = []
    for f in range(cv.N_OUTER):
        te = H.EVAL[H.EVAL.study_id.map(folds) == f].reset_index(drop=True)
        tr = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        _, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
        P.append(pd.DataFrame(dict(seed=seed, config='MEAN', contrast_id=te.contrast_id, study_id=te.study_id, y=te.target, pred=tr.target.mean())))
        for name, cols, te_keys, tfidf, models in CONFIGS:
            cat = [c for c in cols if (c in A.REF_CAT or c in CAT_PARSED) and c in tr.columns]
            num = [c for c in cols if c not in cat and c in tr.columns]
            r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = list(te_keys), tfidf
            for m in models:
                p, *_ = cv.fit_predict_ml(m, tr, te, cat, num, 'ivw_re', tau2, H.SCHEME, seed + f)
                P.append(pd.DataFrame(dict(seed=seed, config=f'{name} | {m}', contrast_id=te.contrast_id, study_id=te.study_id,
                                           y=te.target, pred=p)))
        r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
        print(f'seed {seed} fold {f}', flush=True)
    return pd.concat(P, ignore_index=True)


if __name__ == '__main__':
    t = time.time()
    A.CONFIGS = [(f'{n} | {m}', c) for n, c, _, _, ms in CONFIGS for m in ms]
    P = pd.concat([run(s) for s in H.SEEDS], ignore_index=True)
    P.to_parquet(H.OUT / 'results' / f'v7_text_parsed_oof_{EP}.parquet', index=False)
    S = A.summarise(P, ref='REF_CLEAN (text dropped) | RIDGE')
    S.to_csv(H.OUT / 'results' / f'v7_text_parsed_{EP}.csv', index=False)
    d = H.EVAL
    cov = {b: round(float(d[[c for c in cols if c in d]].notna().any(axis=1).groupby(d.study_id).any().mean()), 2) for b, cols in BLOCKS.items()}
    print('study coverage of parsed blocks:', cov)
    pd.set_option('display.width', 250)
    print(S[['config', 'RMSE', 'RMSE_seed_sd', 'd_vs_REF', 'd_vs_REF_lo', 'd_vs_REF_hi', 'd_vs_MEAN_pct', 'd_vs_MEAN_lo',
             'd_vs_MEAN_hi']].round(4).to_string(index=False))
    print(f'{time.time() - t:.0f}s')
