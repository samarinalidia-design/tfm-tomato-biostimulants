"""V5 step 3: apply the pre-specified selection rule to the TRAIN cross-validation, then fit every candidate on the FULL
TRAIN table (inner tuning grouped by dependency_cluster_id) and freeze the pipeline BEFORE any TEST row is read.

Writes v5/freeze/: MODEL_FREEZE_V5.json (selected models, hyper-parameters, stack weights, feature lists, CV-bar,
evaluation rules and SHA-256 of the TRAIN tables) and models_v5.joblib (fitted featurisers, models, training tables
needed by the meta-regressions). No TEST data is loaded in this script.
"""
import sys, json, hashlib, time, datetime
import numpy as np
import pandas as pd
import joblib
from v5_common import cv, r5, Y, B, fsets, with_dj2, SCHEME, RES, V5, V5Featurizer, DUP_AUDIT
import v5_02_cv_select as S

V3F = r5.V3Featurizer
FZ = V5 / 'freeze'; FZ.mkdir(exist_ok=True)
SEED_FINAL = 11


def fit_ml_final(name, tr, cat, num, tau2, seed, tek, tf):
    """Same procedure as cv.fit_predict_ml (inner grouped CV for the hyper-parameters, refit on all rows,
    95 % interval = quantile of inner out-of-fold residuals) but returns the fitted objects."""
    V3F.TE, V3F.TFIDF = tek, tf
    ytr = tr.target.values; wtr = cv.weights(tr, 'ivw_re', tau2)
    splits = cv.inner_splits(cv.inner_groups(tr, SCHEME), seed=seed)
    best, best_sc, best_res = None, np.inf, None
    for hp in cv.GRIDS[name]:
        res = np.full(len(tr), np.nan)
        for itr, iva in splits:
            fz = cv.Featurizer(cat, num).fit(tr.iloc[itr]); m, kind = cv.make_model(name, hp, seed)
            Xa, _ = fz.transform(tr.iloc[itr], kind); Xb, _ = fz.transform(tr.iloc[iva], kind)
            m.fit(Xa, ytr[itr], sample_weight=wtr[itr]); res[iva] = ytr[iva] - m.predict(Xb)
        sc = np.average(res ** 2, weights=wtr)
        if sc < best_sc:
            best, best_sc, best_res = hp, sc, res
    fz = cv.Featurizer(cat, num).fit(tr); fz.TE, fz.TFIDF = list(tek), bool(tf)      # freeze encoder settings on the instance
    m, kind = cv.make_model(name, best, seed)
    Xa, cols = fz.transform(tr, kind); m.fit(Xa, ytr, sample_weight=wtr)
    V3F.TE, V3F.TFIDF = [], False
    return dict(fz=fz, model=m, kind=kind, hp=best, half=float(np.quantile(np.abs(best_res), 0.95)), columns=cols,
                inner_wmse=float(best_sc))


def main():
    import re
    rows = pd.concat([pd.read_csv(p) for p in sorted(RES.glob('v5_cv_*.csv')) if re.fullmatch(r'v5_cv_(yield|biomass)_\d+', p.stem)])
    rows.to_csv(RES / 'v5_cv_metrics_by_seed.csv', index=False)
    base = rows[rows.model == 'BASELINE_mean'][['endpoint', 'seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_base'})
    j = rows.merge(base, on=['endpoint', 'seed']); j['d_vs_mean_pct'] = 100 * (j.RMSE - j.RMSE_base) / j.RMSE_base
    Sm = j.groupby(['endpoint', 'category', 'model']).agg(seeds=('seed', 'nunique'), RMSE=('RMSE', 'mean'), RMSE_sd=('RMSE', 'std'),
                                                           MAE=('MAE', 'mean'), R2=('R2', 'mean'), bias=('bias', 'mean'), wRMSE=('wRMSE', 'mean'),
                                                           coverage95=('coverage95', 'mean'), PI_width=('mean_PI_width', 'mean'),
                                                           d_vs_mean_pct=('d_vs_mean_pct', 'mean'),
                                                           better_than_mean_all_seeds=('d_vs_mean_pct', lambda x: bool((x < 0).all()))).reset_index()
    assert (Sm.seeds == 3).all(), 'CV incomplete'
    Sm.sort_values(['endpoint', 'category', 'RMSE']).to_csv(RES / 'v5_cv_summary.csv', index=False)
    sel = S.select_final(Sm); sel.to_csv(RES / 'v5_selected_models.csv', index=False)
    print(Sm.sort_values(['endpoint', 'category', 'RMSE']).round(4).to_string()); print(sel.to_string())

    frozen, spec = {}, {}
    for ep in ('yield', 'biomass'):
        df, pool = S.pools(ep, cv.Y, cv.B)
        FS = fsets(ep)
        mu, lo, hi, m0, _ = cv.fit_mr(df, df.iloc[:1], 'MR0', ep); tau2 = float(m0.sigma2.sum())
        mr2 = cv.fit_mr(with_dj2(pool), with_dj2(df.iloc[:1]), 'MR2', ep, True)
        ml = {}
        for nm, key, fs in [('RIDGE_REF', 'RIDGE', 'REF'), ('RF_REF', 'RF', 'REF'), ('RIDGE_V3TE', 'RIDGE', 'V3TE'), ('RF_V3TETF', 'RF', 'V3TETF')]:
            cat, num, tek, tf = FS[fs]
            V5Featurizer.CONTEXT = f'FINAL|{ep}|{nm}'
            ml[nm] = fit_ml_final(key, df, cat, num, tau2, SEED_FINAL, tek, tf)
            ml[nm].update(feature_set=fs, cat=cat, num=num)
            print(ep, nm, ml[nm]['hp'], round(ml[nm]['half'], 3), flush=True)
        lw = S.learn_weights(df, pool, ep, SEED_FINAL, tau2, f'FINAL|{ep}')
        c = float(df.target.mean()); hw = float(np.quantile(np.abs(df.target - c), 0.95))
        frozen[ep] = dict(train=df, pool=pool, mr0=m0, mr2=mr2[3], mr2_names=mr2[4], ml=ml, lstack={k: (m, w.tolist(), h) for k, (m, w, h) in lw.items()},
                          baseline=(c, hw), tau2=tau2)
        spec[ep] = dict(
            n_train_contrasts=len(df), n_train_studies=int(df.study_id.nunique()), n_train_clusters=int(df.dependency_cluster_id.nunique()),
            tau2_MR0=tau2, baseline_mean=c, baseline_half_width=hw,
            selected=sel[sel.endpoint == ep].set_index('category').selected.to_dict(),
            ml={k: dict(feature_set=v['feature_set'], hyperparameters=v['hp'], interval_half_width_95=v['half'],
                        n_model_columns=len(v['columns']), target_encoding_keys=v['fz'].TE, tfidf=v['fz'].TFIDF) for k, v in ml.items()},
            learned_stacks={k: dict(members=m, weights=[round(x, 4) for x in w], interval_half_width_95=h) for k, (m, w, h) in lw.items()},
            equal_stacks=S.EQUAL, MR2_moderators=list(mr2[4]))
    pd.DataFrame(DUP_AUDIT).to_csv(RES / 'v5_feature_duplicates_audit_FINAL.csv', index=False)
    sha = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((V5 / 'data').glob('train_*.parquet'))}
    rules = dict(
        label='POST_HOC_TEST_REUSE (the 2024-2026 TEST corpus was already used in earlier versions V2/V4; this is not a first, blind test)',
        primary_endpoint='yield', secondary_endpoint='dry biomass',
        test_rows='same selection as TRAIN DEFAULT (no box-plot centres; biomass: last timepoint per group); TEST variance imputation uses TRAIN CV-bar',
        no_tuning_on_test='models, hyper-parameters, stack weights, encoders and intervals are fixed in this file; TEST is predicted once',
        category_A='a-priori prediction from design features only (primary claim)',
        category_B='CONDITIONAL: requires the observed stress effect S_vs_C of the new study (meta-regression moderator); reported separately',
        metrics='RMSE, MAE, R2 (1 - SSE/SST around the TEST mean), bias (mean pred - obs), 95 % interval coverage and mean width, '
                'all on contrast level; 2000 study-cluster bootstrap resamples for 95 % CIs and for differences vs BASELINE_mean and MR0',
        criteria={'H1_point': 'selected category-A model: RMSE_TEST < RMSE_TEST(BASELINE_mean) with bootstrap 95 % CI of the difference < 0',
                  'H2_transfer': 'RMSE_TEST <= 1.25 x RMSE_CV of the same model',
                  'H3_intervals': '95 % interval coverage on TEST >= 0.90',
                  'H4_conditional': 'selected category-B model: RMSE_TEST < RMSE_TEST of the selected category-A model (reported, conditional only)'},
        verdict_rule='CONFIRMED if H1-H3 pass; PARTIAL if 1-2 of H1-H3 pass; NOT_CONFIRMED otherwise')
    freeze = dict(version='V5', created_utc=datetime.datetime.utcnow().isoformat() + 'Z', cv_scheme='nested, outer 5 folds x seeds 11/22/33 and inner 3 folds, grouped by dependency_cluster_id',
                  selection_rule=S.__doc__.split('Rule:')[1].strip(), train_sha256=sha, variance_imputation=pd.read_csv(RES / 'variance_imputation_v5.csv').to_dict('records'),
                  endpoints=spec, evaluation_rules=rules)
    json.dump(freeze, open(FZ / 'MODEL_FREEZE_V5.json', 'w'), indent=2, default=str)
    joblib.dump(frozen, FZ / 'models_v5.joblib', compress=3)
    (FZ / 'MODEL_FREEZE_V5.sha256').write_text(hashlib.sha256((FZ / 'MODEL_FREEZE_V5.json').read_bytes()).hexdigest() + '  MODEL_FREEZE_V5.json\n' +
                                               hashlib.sha256((FZ / 'models_v5.joblib').read_bytes()).hexdigest() + '  models_v5.joblib\n')
    print(json.dumps(spec, indent=1, default=str)[:4000])


if __name__ == '__main__':
    main()
