"""V7 step 4: what inside the 'raw numeric environment' block carries the yield signal - the printed values or the fact that
a value was (not) reported?  Same data (V6), engine, folds, rows and bootstrap as v7_03_ablation.py.
  ENV_FULL        CORE + 10 environment numerics (median imputation + missing indicators, as in V5)
  ENV_VALUES      values only, imputed by the training median, NO missing indicators
  ENV_REPORTED    only the 0/1 'reported' indicators (no values)
  ENV_ONE_<v>     CORE + one variable (value + indicator)
  REF_CLEAN       REF minus groups that cannot carry information by construction (unit strings, free-text categories
                  whose levels never reach 3 studies) - an a-priori clean-up, not chosen from the ablation numbers
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


def add_reported(df):
    df = df.copy()
    for c in ENV:
        df['envrep_' + c[2:]] = df[c].notna().astype(float)
        df['envval_' + c[2:]] = df[c]
    return df


CONFIGS = {'ENV_FULL': ('raw', A.CORE + ENV), 'ENV_VALUES': ('values', A.CORE + ['envval_' + c[2:] for c in ENV]),
           'ENV_REPORTED': ('raw', A.CORE + ['envrep_' + c[2:] for c in ENV]),
           'REF_FULL': ('raw', A.ALLF), 'REF_CLEAN': ('raw', [c for c in A.ALLF if c not in TEXT])}
for c in ENV:
    CONFIGS['ENV_ONE_' + c] = ('raw', A.CORE + [c])


def run(seed):
    folds = cv.make_folds(H.SCHEME, seed)
    src = add_reported(H.rows('V6')); ev = add_reported(H.EVAL)
    P = []
    for f in range(cv.N_OUTER):
        te = ev[ev.study_id.map(folds) == f].reset_index(drop=True)
        tr = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        _, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
        P.append(pd.DataFrame(dict(seed=seed, config='MEAN', contrast_id=te.contrast_id, study_id=te.study_id, y=te.target, pred=tr.target.mean())))
        r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
        for name, (mode, cols) in CONFIGS.items():
            trx, tex = tr, te
            if mode == 'values':                       # impute values before the featurizer -> no missing indicators
                trx, tex = tr.copy(), te.copy()
                for c in [c for c in cols if c.startswith('envval_')]:
                    m = trx[c].median(); trx[c] = trx[c].fillna(m); tex[c] = tex[c].fillna(m)
            cat = [c for c in cols if c in A.REF_CAT]; num = [c for c in cols if c not in cat and c in trx.columns]
            p, *_ = cv.fit_predict_ml('RIDGE', trx, tex, cat, num, 'ivw_re', tau2, H.SCHEME, seed + f)
            P.append(pd.DataFrame(dict(seed=seed, config=name, contrast_id=te.contrast_id, study_id=te.study_id, y=te.target, pred=p)))
        print(f'seed {seed} fold {f}', flush=True)
    return pd.concat(P, ignore_index=True)


if __name__ == '__main__':
    t = time.time()
    A.CONFIGS = [(k, v[1]) for k, v in CONFIGS.items()]
    P = pd.concat([run(s) for s in H.SEEDS], ignore_index=True)
    S = A.summarise(P, ref='ENV_FULL')
    S.to_csv(H.OUT / 'results' / f'v7_env_probe_{EP}.csv', index=False)
    # coverage of each environment variable (share of studies reporting it)
    d = H.EVAL
    cov = {c: round(float(d[c].notna().groupby(d.study_id).any().mean()), 2) for c in ENV}
    S['coverage'] = S.config.str.replace('ENV_ONE_', '').map(cov)
    pd.set_option('display.width', 250)
    print(S[['config', 'coverage', 'RMSE', 'd_vs_REF', 'd_vs_REF_lo', 'd_vs_REF_hi', 'd_vs_MEAN_pct', 'd_vs_MEAN_lo', 'd_vs_MEAN_hi']].round(4).to_string(index=False))
    print(f'{time.time() - t:.0f}s')
