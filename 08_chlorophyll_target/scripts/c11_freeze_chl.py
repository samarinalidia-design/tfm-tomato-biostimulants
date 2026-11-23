"""Freeze the chlorophyll models on the FULL TRAIN tables BEFORE any TEST chlorophyll extraction (TEST protocol, TFM 3.1).

For both chlorophyll targets (CHL_CONTENT = train_chlorophyll_V8, CHL_INDEX = train_chl_index_V8) every configuration of the
comparable CV (c09) is fitted on all default TRAIN rows with the V5 procedure (inner grouped CV for the hyper-parameters on
dependency clusters, refit on all rows; same seed 11 as V5's final fit): RIDGE / RF x weights ivw_re / none / n, plus MR0
(3-level mean) and the TRAIN mean. Pre-declared primary models (from the strict research-group CV of c09, chosen before TEST):
  CHL_INDEX   : RF_REF_wivw_re (best in both CV variants; -10.9 % [-15.4, -3.6] under research-group grouping)
  CHL_CONTENT : no ML model beat the mean in CV; primary = TRAIN 3-level mean (MR0); RF_REF_wn reported as the ML candidate.
Also frozen: CV-bar and median n per endpoint learnt on TRAIN (applied to TEST variance imputation), feature lists, SHA-256 of
the TRAIN tables, of this script, c05/c06/c08 and the V5 engine.
Writes freeze/MODEL_FREEZE_CHL.json, freeze/models_chl.joblib, freeze/MODEL_FREEZE_CHL.sha256. No TEST data is read.
"""
import sys, json, hashlib, datetime, pathlib
import numpy as np
import pandas as pd
import joblib

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
_argv = sys.argv; sys.argv = sys.argv[:1]
import v5_common as V
sys.argv = _argv
cv, r5 = V.cv, V.r5
FZ = OUT / 'freeze'; FZ.mkdir(exist_ok=True)
SEED = 11
CONFIGS = [('RIDGE', 'ivw_re'), ('RIDGE', 'none'), ('RIDGE', 'n'), ('RF', 'ivw_re'), ('RF', 'n')]
PRIMARY = {'CHL_INDEX': 'RF_REF_wivw_re', 'CHL_CONTENT': 'MR0'}
ML_CANDIDATE = {'CHL_INDEX': 'RF_REF_wivw_re', 'CHL_CONTENT': 'RF_REF_wn'}


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def prep(T):
    T = T[T.in_default == 1].copy()
    T['study_id'] = T.study_id.astype(str)
    T['target'] = T.effect.astype(float); T['v'] = T.var_lnrr_imp.astype(float)
    T['exp_uid'] = T.study_id + '|' + T.experiment_key.astype(str)
    T['endpoint_is_yield'] = 0
    T['w_n'] = 1.0 / T.groupby('study_id').target.transform('size')
    return T[T.target.notna() & T.v.notna() & (T.v > 0)].reset_index(drop=True)


def features():
    cat, num, _, _ = V.fsets('biomass')['REF']
    cat = ['chl_basis', 'chl_measure_kind'] + [c for c in cat if c != 'organ_scope']
    num = [c for c in num if c != 'dry_basis_confirmed'] + ['is_computed_total']
    return cat, num


def fit_ml(name, tr, cat, num, wscheme, tau2):
    ytr = tr.target.values; wtr = cv.weights(tr, wscheme, tau2)
    splits = cv.inner_splits(cv.inner_groups(tr, 'cluster'), seed=SEED)
    best, best_sc, best_res = None, np.inf, None
    for hp in cv.GRIDS[name]:
        res = np.full(len(tr), np.nan)
        for itr, iva in splits:
            fz = cv.Featurizer(cat, num).fit(tr.iloc[itr]); m, kind = cv.make_model(name, hp, SEED)
            Xa, _ = fz.transform(tr.iloc[itr], kind); Xb, _ = fz.transform(tr.iloc[iva], kind)
            m.fit(Xa, ytr[itr], sample_weight=wtr[itr]); res[iva] = ytr[iva] - m.predict(Xb)
        sc = np.average(res ** 2, weights=wtr)
        if sc < best_sc:
            best, best_sc, best_res = hp, sc, res
    fz = cv.Featurizer(cat, num).fit(tr); m, kind = cv.make_model(name, best, SEED)
    Xa, cols = fz.transform(tr, kind); m.fit(Xa, ytr, sample_weight=wtr)
    return dict(fz=fz, model=m, kind=kind, hp=best, half=float(np.quantile(np.abs(best_res), 0.95)), columns=cols)


def main():
    r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
    cat, num = features()
    frozen, spec = {}, {}
    for ep, f in [('CHL_CONTENT', 'train_chlorophyll_V8.parquet'), ('CHL_INDEX', 'train_chl_index_V8.parquet')]:
        T = prep(pd.read_parquet(OUT / 'data' / f))
        c = [x for x in cat if x in T.columns]; n = [x for x in num if x in T.columns]
        cv.ALL = T[['study_id', 'dependency_cluster_id']].drop_duplicates('study_id')
        cv.STUDY2CLUSTER = cv.ALL.set_index('study_id').dependency_cluster_id
        cv.ROWS_PER_STUDY = T.study_id.value_counts()
        mu, lo, hi, m0, _ = cv.fit_mr(T, T.iloc[:1], 'MR0', 'biomass'); tau2 = float(m0.sigma2.sum())
        models = {'MR0': dict(value=float(mu[0]), tau2=tau2), 'BASELINE_mean': dict(value=float(T.target.mean()))}
        for name, w in CONFIGS:
            models[f'{name}_REF_w{w}'] = fit_ml(name, T, c, n, w, tau2)
            print(ep, name, w, models[f'{name}_REF_w{w}']['hp'], flush=True)
        frozen[ep] = dict(models=models, cat=c, num=n)
        spec[ep] = dict(train_rows=len(T), train_studies=int(T.study_id.nunique()), primary=PRIMARY[ep], ml_candidate=ML_CANDIDATE[ep],
                        MR0=models['MR0'], train_mean=models['BASELINE_mean']['value'],
                        hyper_parameters={k: v['hp'] for k, v in models.items() if isinstance(v, dict) and 'hp' in v},
                        features_cat=c, features_num=n)
    # TRAIN-learnt variance imputation constants (c05 definition)
    VR = pd.read_csv(OUT / 'data' / 'all_values_with_roles.csv', low_memory=False)
    cvbar = (VR.sd / VR['mean']).replace([np.inf, -np.inf], np.nan)
    imput = dict(cv_bar_by_endpoint=VR.assign(cv=cvbar).groupby('endpoint').cv.mean().to_dict(), median_n=float(VR.n.median()))
    files = {p: sha(OUT / p) for p in ['data/train_chlorophyll_V8.parquet', 'data/train_chl_index_V8.parquet', 'data/all_values_with_roles.csv',
                                         'scripts/c05_contrasts.py', 'scripts/c06_training_dataset.py', 'scripts/c08_train_dataset_like_v6.py',
                                         'scripts/c11_freeze_chl.py', 'scripts/c09_cv_three_targets.py']}
    files['05_analysis_train_expansion_v5/scripts/02_cv_models.py'] = sha(REPO / '05_analysis_train_expansion_v5' / 'scripts' / '02_cv_models.py')
    freeze = dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), seed=SEED,
                  note='Frozen before any TEST chlorophyll source work. TEST corpus (2024-2026) was used earlier for yield / biomass '
                       '(POST_HOC_TEST_REUSE); its chlorophyll values have never been extracted before this freeze.',
                  targets=spec, variance_imputation_from_train=imput, sha256=files,
                  evaluation='TEST default rows (in_default_chl), same contrast types (SB_vs_S, B_vs_C); RMSE, MAE, R2 vs the TRAIN mean '
                             '(primary comparison: primary model vs TRAIN mean), study bootstrap 2000 for the RMSE difference; '
                             'secondary: all frozen configurations.')
    (FZ / 'MODEL_FREEZE_CHL.json').write_text(json.dumps(freeze, indent=2, default=str), encoding='utf-8')
    joblib.dump(frozen, FZ / 'models_chl.joblib', compress=3)
    (FZ / 'MODEL_FREEZE_CHL.sha256').write_text(f"{sha(FZ / 'MODEL_FREEZE_CHL.json')}  MODEL_FREEZE_CHL.json\n{sha(FZ / 'models_chl.joblib')}  models_chl.joblib\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ('features_cat', 'features_num')} for k, v in spec.items()}, indent=1, default=str))
    print(imput)


if __name__ == '__main__':
    main()
