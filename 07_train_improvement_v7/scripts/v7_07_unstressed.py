"""V7 step 7: do unstressed contrasts (B_vs_C) help to predict the effect UNDER STRESS (SB_vs_S)?
A direct, in-data test of whether class C studies (tomato + biostimulant, no stress) could strengthen training.
Same data (V6), engine, folds and bootstrap as v7_03; evaluation rows = the SB_vs_S rows of in_default_v6 only.
  WITH_BvsC     training on SB_vs_S + B_vs_C (contrast type is a feature, is_B_vs_C)
  SBvsS_ONLY    training on SB_vs_S only
  WITH_BvsC_MEAN / SBvsS_ONLY_MEAN: training means (a mean that includes unstressed rows is lower)
Also: share of each studies' unstressed effect that predicts its stressed effect (study level, descriptive).
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


def run(seed):
    folds = cv.make_folds(H.SCHEME, seed)
    src = H.rows('V6')
    ev = H.EVAL[H.EVAL.contrast_type == 'SB_vs_S']
    P = []
    for f in range(cv.N_OUTER):
        te = ev[ev.study_id.map(folds) == f].reset_index(drop=True)
        if te.empty:
            continue
        base = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(set(te.dependency_cluster_id))]
        for name, tr in [('WITH_BvsC', base), ('SBvsS_ONLY', base[base.contrast_type == 'SB_vs_S'])]:
            tr = tr.reset_index(drop=True)
            _, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
            P.append(pd.DataFrame(dict(seed=seed, config=name + '_MEAN', contrast_id=te.contrast_id, study_id=te.study_id,
                                       y=te.target, pred=tr.target.mean())))
            # the mean of the stressed rows only, the fair constant for a stressed target
            P.append(pd.DataFrame(dict(seed=seed, config=name + '_MEAN_SBvsS', contrast_id=te.contrast_id, study_id=te.study_id,
                                       y=te.target, pred=tr.loc[tr.contrast_type == 'SB_vs_S', 'target'].mean())))
            r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
            cat = [c for c in CLEAN if c in A.REF_CAT and c in tr.columns]; num = [c for c in CLEAN if c not in cat and c in tr.columns]
            for m in ['RIDGE', 'RF']:
                p, *_ = cv.fit_predict_ml(m, tr, te, cat, num, 'ivw_re', tau2, H.SCHEME, seed + f)
                P.append(pd.DataFrame(dict(seed=seed, config=f'{name} | {m}', contrast_id=te.contrast_id, study_id=te.study_id,
                                           y=te.target, pred=p)))
        print(f'seed {seed} fold {f}', flush=True)
    return pd.concat(P, ignore_index=True)


if __name__ == '__main__':
    t = time.time()
    P = pd.concat([run(s) for s in H.SEEDS], ignore_index=True)
    P['config'] = P.config.replace({'SBvsS_ONLY_MEAN_SBvsS': 'MEAN'})   # reference constant: mean of stressed training rows
    S = A.summarise(P, ref='SBvsS_ONLY | RIDGE')
    S.to_csv(H.OUT / 'results' / f'v7_unstressed_{EP}.csv', index=False)
    # descriptive: within a study, does the unstressed effect of an arm's product predict its stressed effect?
    d = H.rows('V6')
    s = d[d.contrast_type == 'SB_vs_S'].groupby('study_id').target.mean()
    b = d[d.contrast_type == 'B_vs_C'].groupby('study_id').target.mean()
    j = pd.concat([s.rename('stressed'), b.rename('unstressed')], axis=1).dropna()
    from scipy.stats import spearmanr
    r = spearmanr(j.stressed, j.unstressed)
    pd.set_option('display.width', 250)
    print(S[['config', 'RMSE', 'RMSE_seed_sd', 'd_vs_REF', 'd_vs_REF_lo', 'd_vs_REF_hi', 'd_vs_MEAN_pct', 'd_vs_MEAN_lo', 'd_vs_MEAN_hi']]
          .round(4).to_string(index=False))
    print(f'studies with both: {len(j)}, Spearman(stressed, unstressed study means) = {r.correlation:.2f} (p = {r.pvalue:.3g}); '
          f'mean stressed {j.stressed.mean():.3f}, unstressed {j.unstressed.mean():.3f}')
    print(f'{time.time() - t:.0f}s')
