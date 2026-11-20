"""Round 7 (dry biomass): apply the round-5 recommendation (v3 features with target encoding) and combine with
the meta-regression models.

Members (refit in every outer training fold, same study-grouped folds / seeds 11-22-33):
  MR0                  3-level intercept
  MR2mt                MR2 v2DJ multitask (yield+biomass), uses S_vs_C moderator -> category B
  RIDGE_V3TE           Ridge on V3_NORAW_TE   (round 5 best Ridge)
  RF_V3TETF            RF on V3_NORAW_TE_TFIDF (round 5 best RF)
Stacks:
  * LEARNED (clean estimate): non-negative weights (NNLS, normalised to 1, RE-weighted) fitted on INNER out-of-fold
    predictions of the members (3 inner folds by study, training studies only; every member refit inside each inner
    fold incl. its own nested tuning / TE). Interval: 95% quantile of |inner-OOF stack residuals|.
      LSTACK_A = MR0 + RIDGE_V3TE + RF_V3TETF   (a-priori, category A)
      LSTACK_B = A + MR2mt                       (category B)
  * EQUAL-weight (members chosen after round 5 -> optimistic upper estimate, reported for completeness)
      ESTACK_A2 = MR0 + RIDGE_V3TE ; ESTACK_A3 = MR0 + RIDGE_V3TE + RF_V3TETF
      ESTACK_B3 = MR0 + MR2mt + RIDGE_V3TE ; ESTACK_B4 = all four
"""
import sys, json, time, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd
from scipy.optimize import nnls

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('r5', HERE / '12_round5_v3.py')
r5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r5)
cv, RES = r5.cv, r5.RES
V3F = r5.V3Featurizer
warnings.filterwarnings('ignore')
SEEDS, EP = [11, 22, 33], 'biomass'
FS = r5.fsets(EP)
A_MEM = ['MR0', 'RIDGE_V3TE', 'RF_V3TETF']
B_MEM = A_MEM + ['MR2mt']


def members(tr, te, trm, seed):
    out = {}
    mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
    out['MR0'] = (mu, lo, hi)
    mu, lo, hi, _, _ = cv.fit_mr(r5.with_dj2(trm), r5.with_dj2(te), 'MR2', EP, True)
    out['MR2mt'] = (mu, lo, hi)
    for nm, key, fs in [('RIDGE_V3TE', 'RIDGE', 'V3_NORAW_TE'), ('RF_V3TETF', 'RF', 'V3_NORAW_TE_TFIDF')]:
        cat, num, tek, tf = FS[fs]
        V3F.TE, V3F.TFIDF = tek, tf
        p, lo, hi, _, _ = cv.fit_predict_ml(key, tr, te, cat, num, 'ivw_re', tau2, 'study', seed)
        out[nm] = (p, lo, hi)
    V3F.TE, V3F.TFIDF = [], False
    return out, tau2


def learn_weights(tr, trm, seed, tau2):
    splits = cv.inner_splits(cv.inner_groups(tr, 'study'), seed=seed + 1000)
    O = {k: np.full(len(tr), np.nan) for k in B_MEM}
    for a, b in splits:
        tri, vai = tr.iloc[a].reset_index(drop=True), tr.iloc[b].reset_index(drop=True)
        trmi = trm[~trm.study_id.isin(set(vai.study_id))].reset_index(drop=True)
        o, _ = members(tri, vai, trmi, seed)
        for k in B_MEM:
            O[k][b] = o[k][0]
    y, w = tr.target.values, cv.weights(tr, 'ivw_re', tau2)
    res = {}
    for nm, mem in [('LSTACK_A', A_MEM), ('LSTACK_B', B_MEM)]:
        X = np.column_stack([O[k] for k in mem]); sw = np.sqrt(w)
        wt, _ = nnls(X * sw[:, None], y * sw)
        wt = wt / wt.sum() if wt.sum() > 0 else np.full(len(mem), 1 / len(mem))
        half = np.quantile(np.abs(y - X @ wt), 0.95)
        res[nm] = (mem, wt, half)
    return res


def run(seed, tau2_ref):
    df = cv.select(EP, cv.BASE).reset_index(drop=True)
    other = cv.select('yield', cv.BASE)
    pool = pd.concat([df, other], ignore_index=True)
    df = df.reindex(columns=pool.columns)
    folds = cv.make_folds('study', seed)
    P, W = [], []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True)
        te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        trm = pool[pool.study_id.map(folds) != f].reset_index(drop=True)
        assert not set(trm.study_id) & set(te.study_id)
        if len(te) == 0:
            continue
        t0 = time.time()
        out, tau2 = members(tr, te, trm, seed + f)
        c = tr.target.mean(); hw = np.quantile(np.abs(tr.target - c), 0.95)
        out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - hw), np.full(len(te), c + hw))
        for nm, mem in [('ESTACK_A2', ['MR0', 'RIDGE_V3TE']), ('ESTACK_A3', A_MEM),
                        ('ESTACK_B3', ['MR0', 'MR2mt', 'RIDGE_V3TE']), ('ESTACK_B4', B_MEM)]:
            p = np.mean([out[k][0] for k in mem], axis=0); h = np.mean([(out[k][2] - out[k][1]) / 2 for k in mem], axis=0)
            out[nm] = (p, p - h, p + h)
        for nm, (mem, wt, half) in learn_weights(tr, trm, seed + f, tau2).items():
            p = np.column_stack([out[k][0] for k in mem]) @ wt
            out[nm] = (p, p - half, p + half)
            W.append(dict(seed=seed, fold=f, stack=nm, **{k: round(float(x), 3) for k, x in zip(mem, wt)}))
            print(f'  seed={seed} fold={f} {nm} weights {W[-1]}', flush=True)
        print(f'  seed={seed} fold={f} {time.time() - t0:.0f}s', flush=True)
        for nm, (p, lo, hi) in out.items():
            P.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, fold=f, model=nm, y=te.target,
                                       pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
    P = pd.concat(P, ignore_index=True)
    rows = [dict(endpoint=EP, model=nm, seed=seed, n_studies=g.study_id.nunique(),
                 **cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref)))
            for nm, g in P.groupby('model')]
    return rows, P.assign(endpoint=EP, seed=seed), W


if __name__ == '__main__':
    tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
    out_csv, w_csv = RES / 'cv_metrics_round7_biomass.csv', RES / 'round7_stack_weights.csv'
    allr = pd.read_csv(out_csv).to_dict('records') if out_csv.exists() else []
    allw = pd.read_csv(w_csv).to_dict('records') if w_csv.exists() else []
    done = {r['seed'] for r in allr}
    for s in SEEDS:
        if s in done:
            continue
        t = time.time()
        r, p, w = run(s, tau2_ref[EP]); allr += r; allw += w
        pd.DataFrame(allr).to_csv(out_csv, index=False); pd.DataFrame(allw).to_csv(w_csv, index=False)
        p.to_parquet(RES / f'cv_oof_round7_biomass_{s}.parquet', index=False)
        print(f'biomass seed={s} {time.time() - t:.0f}s', flush=True)
    M = pd.DataFrame(allr)
    b = M[M.model == 'BASELINE_mean'][['seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_base'})
    m0 = M[M.model == 'MR0'][['seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_mr0'})
    j = M.merge(b, on='seed').merge(m0, on='seed')
    j['d_vs_mean_pct'] = 100 * (j.RMSE - j.RMSE_base) / j.RMSE_base
    j['d_vs_MR0_pct'] = 100 * (j.RMSE - j.RMSE_mr0) / j.RMSE_mr0
    S = j.groupby(['endpoint', 'model']).agg(
        seeds=('seed', 'nunique'), RMSE=('RMSE', 'mean'), RMSE_sd=('RMSE', 'std'), MAE=('MAE', 'mean'), R2=('R2', 'mean'),
        wRMSE=('wRMSE', 'mean'), coverage95=('coverage95', 'mean'), PI_width=('mean_PI_width', 'mean'),
        d_vs_mean_pct=('d_vs_mean_pct', 'mean'), d_vs_MR0_pct=('d_vs_MR0_pct', 'mean'),
        better_than_MR0_all_seeds=('d_vs_MR0_pct', lambda x: bool((x < 0).all()))).reset_index()
    S.sort_values('RMSE').to_csv(RES / 'cv_metrics_round7_summary.csv', index=False)
    pd.set_option('display.width', 250)
    print(S.sort_values('RMSE').round(4).to_string())
    print(pd.DataFrame(allw).groupby('stack').mean(numeric_only=True).round(3).to_string())
