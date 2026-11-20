"""Block 2: quality of the biostimulant CHOICE (TRAIN only, out-of-fold predictions of the V5 nested cluster CV; TEST not read).

Choice sets: arms tested against the SAME control in the same study/experiment and the same measurement signature
(endpoint definition, unit, timepoint). Within a set, a model "chooses" the arm with the highest predicted lnRR.
  pairs (all)        : every pair of arms with different bio_code (different product or dose)
  pairs (classes)    : pairs whose du Jardin class (h2_dujardin) differs - choice between product TYPES
Metrics (study-balanced: each study counts once; 2000 study bootstrap resamples):
  pairwise accuracy  : model orders the pair like the observed effects; prediction ties count 0.5
  noise-aware acc.   : P(true order = observed order) = Phi(|d|/SE_d), SE_d^2 = CV1^2/n1 + CV2^2/n2 (control cancels);
                       expected accuracy = c*w + (1-c)*(1-w)
  decisive pairs     : |d| > 1.96 SE_d (observed order unlikely to be noise)
  regret             : observed lnRR of the best arm - observed lnRR of the chosen arm, as % yield lost vs the best
Comparators: RANDOM (0.5; expected regret = best - mean of arms), CLASS_PRIOR (in-fold training mean of study means per du Jardin class),
mean/MR0 (constant within a set -> random), and the ML / meta models of the CV.
"""
import json
import numpy as np
import pandas as pd
from scipy.stats import norm
from v5_common import cv, SCHEME, RES, SEEDS, DATA

OUT = RES / 'choice'; OUT.mkdir(exist_ok=True)
MODELS = ['RIDGE_REF', 'RF_V3TETF', 'RIDGE_V3TE', 'STACK_A_REF', 'LSTACK_A', 'MR2mt', 'STACK_B_REF', 'MR0']


def class_prior(df, seed):
    folds = cv.make_folds(SCHEME, seed); f = df.study_id.map(folds)
    out = pd.Series(np.nan, index=df.index)
    for k in range(cv.N_OUTER):
        tr = df[f != k]
        sm = tr.groupby(['h2_dujardin', 'study_id']).effect.mean().groupby(level=0).mean()
        g = tr.groupby('study_id').effect.mean().mean()
        out[f == k] = df.loc[f == k, 'h2_dujardin'].map(sm).fillna(g)
    return out


def pairs_table(ep, seed):
    tab = pd.read_parquet(DATA / ('train_yield.parquet' if ep == 'yield' else 'train_dry_biomass.parquet'))
    tab = tab[(tab.in_default == 1)].copy()
    tab['grp'] = tab.study_id + '|' + tab.experiment_key + '|' + tab.arm_key_c + '|' + tab.signature
    oof = pd.read_parquet(RES / f'v5_cv_oof_{ep}_{seed}.parquet')
    P = oof[oof.model.isin(MODELS)].pivot_table(index='contrast_id', columns='model', values='pred')
    tab = tab.join(P, on='contrast_id')
    tab['CLASS_PRIOR'] = class_prior(tab, seed)
    tab['se2'] = tab.cv_used_t ** 2 / tab.n_imp_t
    rows, regs = [], []
    for g, x in tab.groupby('grp'):
        if x.arm_key_t.nunique() < 2:
            continue
        x = x.drop_duplicates('arm_key_t').reset_index(drop=True)
        y = x.effect.values
        best = y.max()
        for m in MODELS + ['CLASS_PRIOR']:
            p = x[m].values; ch = np.flatnonzero(p == p.max())
            regs.append(dict(endpoint=ep, seed=seed, study_id=x.study_id[0], grp=g, model=m, n_arms=len(x),
                             multi_class=int(x.h2_dujardin.nunique() > 1),
                             regret=float(best - y[ch].mean()), regret_random=float(best - y.mean())))
        for i in range(len(x)):
            for j in range(i + 1, len(x)):
                if x.bio_code[i] == x.bio_code[j]:
                    continue
                d = y[i] - y[j]; se = np.sqrt(x.se2[i] + x.se2[j]); w = norm.cdf(abs(d) / se) if se > 0 else 1.0
                base = dict(endpoint=ep, seed=seed, study_id=x.study_id[0], grp=g, diff_class=int(x.h2_dujardin[i] != x.h2_dujardin[j]),
                            d_obs=d, se_d=se, w_true_order=w, decisive=int(abs(d) > 1.96 * se))
                for m in MODELS + ['CLASS_PRIOR']:
                    dp = x[m][i] - x[m][j]
                    c = 0.5 if dp == 0 or d == 0 else float(np.sign(dp) == np.sign(d))
                    rows.append(dict(base, model=m, correct=c, correct_noise=c * w + (1 - c) * (1 - w)))
    return pd.DataFrame(rows), pd.DataFrame(regs)


def boot_mean(per_study, B=2000, seed=0):
    v = per_study.values; rng = np.random.default_rng(seed)
    bs = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)]
    return float(v.mean()), float(np.quantile(bs, .025)), float(np.quantile(bs, .975))


def summarise(Pr, Rg):
    out = []
    for (ep, m), g in Pr.groupby(['endpoint', 'model']):
        for subset, s in [('all pairs', g), ('different class', g[g.diff_class == 1]), ('decisive pairs', g[g.decisive == 1]),
                          ('decisive, different class', g[(g.decisive == 1) & (g.diff_class == 1)])]:
            if s.empty:
                continue
            for metric in ['correct', 'correct_noise']:
                ps = s.groupby(['seed', 'study_id'])[metric].mean().groupby('study_id').mean()
                mu, lo, hi = boot_mean(ps)
                out.append(dict(endpoint=ep, model=m, subset=subset, metric=metric, value=mu, ci_lo=lo, ci_hi=hi,
                                studies=len(ps), pairs=int(len(s) / s.seed.nunique())))
    for (ep, m), g in Rg.groupby(['endpoint', 'model']):
        for subset, s in [('all sets', g), ('multi-class sets', g[g.multi_class == 1])]:
            ps = s.groupby(['seed', 'study_id'])[['regret', 'regret_random']].mean().groupby('study_id').mean()
            d = ps.regret - ps.regret_random
            for metric, v in [('regret', ps.regret), ('regret_random', ps.regret_random), ('regret_minus_random', d)]:
                mu, lo, hi = boot_mean(v)
                out.append(dict(endpoint=ep, model=m, subset=subset, metric=metric, value=mu, ci_lo=lo, ci_hi=hi, studies=len(ps),
                                pairs=int(len(s) / s.seed.nunique())))
    S = pd.DataFrame(out); S.to_csv(OUT / 'choice_summary.csv', index=False)
    return S


if __name__ == '__main__':
    Pr, Rg = [], []
    for ep in ('yield', 'biomass'):
        for s in SEEDS:
            p, r = pairs_table(ep, s); Pr.append(p); Rg.append(r)
    Pr, Rg = pd.concat(Pr), pd.concat(Rg)
    Pr.to_parquet(OUT / 'choice_pairs.parquet', index=False); Rg.to_parquet(OUT / 'choice_regret_sets.parquet', index=False)
    S = summarise(Pr, Rg)
    pd.set_option('display.width', 250)
    print(S[S.metric.isin(['correct', 'correct_noise'])].pivot_table(index=['endpoint', 'subset', 'model'], columns='metric', values='value').round(3).to_string())
    print(S[S.metric.str.startswith('regret')].round(4).to_string())
