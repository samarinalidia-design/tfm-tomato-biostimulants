"""V7 step 5: the environment block carries the yield signal (v7_04). Does filling it with the values V6 recovered from the
database text (ranges, +/-, DMS, plants/ha ...) strengthen it?  Same data/engine/folds/rows/bootstrap as v7_03.

Filling rule (no target information, done before the CV, value-for-value): an f_* environment value missing in V5 is
replaced by the V6 parsed value of the same moderator; soil sand/clay % (h3) and N kg/ha are added as extra numerics.
  *_V6   = with the V6-filled environment block
  REF_CLEAN = REF minus unit strings and free-text categories (levels never reach 3 studies; a-priori clean-up)
Usage: python v7_05_env_v6fill.py yield|biomass
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
ENV = A.GROUPS['raw numeric environment (f_ pH, OM, lat, T, RH, PPFD, photoperiod, pot, density)']
TEXT = [c for g, cols in A.GROUPS.items() if 'text' in g or 'unit' in g for c in cols]
FILL = {'f_temperature_day_c': 'v6_temperature_day_c', 'f_temperature_night_c': 'v6_temperature_night_c',
        'f_relative_humidity': 'v6_relative_humidity_pct', 'f_photoperiod_h': 'v6_photoperiod_h',
        'f_pot_volume_l': 'v6_pot_volume_l', 'f_latitude': 'v6_abs_latitude_printed', 'f_plant_density_m2': 'h2_plant_density_m2'}
SOIL_FERT = ['h3_sand_pct', 'h3_clay_pct', 'h3_fert_n_kg_ha']


def v6fill(df):
    df = df.copy()
    for f, src in FILL.items():
        if f in df and src in df:
            df['e6_' + f[2:]] = pd.to_numeric(df[f], errors='coerce').fillna(pd.to_numeric(df[src], errors='coerce'))
        elif f in df:
            df['e6_' + f[2:]] = df[f]
    for f in ENV:
        if 'e6_' + f[2:] not in df:
            df['e6_' + f[2:]] = df[f]
    return df


ENV6 = ['e6_' + c[2:] for c in ENV]
CLEAN = [c for c in A.ALLF if c not in TEXT]
CONFIGS = {'REF_FULL': A.ALLF, 'REF_CLEAN': CLEAN,
           'ENV_FULL': A.CORE + ENV, 'ENV_FULL_V6': A.CORE + ENV6, 'ENV_V6_SOIL_FERT': A.CORE + ENV6 + SOIL_FERT,
           'REF_CLEAN_V6': [c for c in CLEAN if c not in ENV] + ENV6,
           'REF_CLEAN_V6_SOIL_FERT': [c for c in CLEAN if c not in ENV] + ENV6 + SOIL_FERT}


def run(seed):
    folds = cv.make_folds(H.SCHEME, seed)
    src = v6fill(H.rows('V6')); ev = v6fill(H.EVAL)
    P = []
    for f in range(cv.N_OUTER):
        te = ev[ev.study_id.map(folds) == f].reset_index(drop=True)
        tr = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        _, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
        P.append(pd.DataFrame(dict(seed=seed, config='MEAN', contrast_id=te.contrast_id, study_id=te.study_id, y=te.target, pred=tr.target.mean())))
        r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
        for name, cols in CONFIGS.items():
            cat = [c for c in cols if c in A.REF_CAT]; num = [c for c in cols if c not in cat and c in tr.columns]
            p, *_ = cv.fit_predict_ml('RIDGE', tr, te, cat, num, 'ivw_re', tau2, H.SCHEME, seed + f)
            P.append(pd.DataFrame(dict(seed=seed, config=name, contrast_id=te.contrast_id, study_id=te.study_id, y=te.target, pred=p)))
        print(f'seed {seed} fold {f}', flush=True)
    return pd.concat(P, ignore_index=True)


if __name__ == '__main__':
    t = time.time()
    A.CONFIGS = list(CONFIGS.items())
    P = pd.concat([run(s) for s in H.SEEDS], ignore_index=True)
    P.to_parquet(H.OUT / 'results' / f'v7_env_v6fill_oof_{EP}.parquet', index=False)
    S = A.summarise(P, ref='REF_FULL')
    d = v6fill(H.EVAL)
    cov = pd.DataFrame({'variable': ENV, 'coverage_V5': [round(float(d[c].notna().groupby(d.study_id).any().mean()), 2) for c in ENV],
                        'coverage_V6fill': [round(float(d['e6_' + c[2:]].notna().groupby(d.study_id).any().mean()), 2) for c in ENV]})
    S.to_csv(H.OUT / 'results' / f'v7_env_v6fill_{EP}.csv', index=False)
    cov.to_csv(H.OUT / 'results' / f'v7_env_coverage_{EP}.csv', index=False)
    pd.set_option('display.width', 250)
    print(cov.to_string(index=False))
    print(S[['config', 'n_features', 'RMSE', 'RMSE_seed_sd', 'd_vs_REF', 'd_vs_REF_lo', 'd_vs_REF_hi', 'd_vs_MEAN_pct',
             'd_vs_MEAN_lo', 'd_vs_MEAN_hi']].round(4).to_string(index=False))
    print(f'{time.time() - t:.0f}s')
