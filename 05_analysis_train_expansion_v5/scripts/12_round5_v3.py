"""Round 5: better categorical coding -> numeric features (v3), retrained with the same study-grouped nested CV.

Encodings learnt INSIDE each training fold only (and inside each inner fold during tuning):
  * deterministic recoding from 11_features_v3.py (multi-hot / ordinal / parsed numerics; no target use)
  * target encoding (TE) of high-cardinality keys: study-level empirical-Bayes mean
        enc(level) = (n_s * mean_over_studies(level) + k * global) / (n_s + k),  k = 5 studies
    training rows get grouped out-of-fold encodings (5 study groups) so a row never sees its own study's target;
    unseen / validation rows get the full training-fold map
  * frequency encoding: log(1 + number of training studies with the level)
  * TF-IDF (1-2-grams, term in >= 3 training studies) on the concatenated text, one document per study,
    compressed by truncated SVD (10 components); unsupervised, fitted on training studies only
Feature sets (ML models RF / GBM / RIDGE, nested tuning as before):
  REF_V2DJ            current best a-priori set (round 3)
  V3_PARSED           REF + all h3 recodings
  V3_NORAW            h3 recodings + harmonised + definitions, raw free-text f_* categories removed
  V3_NORAW_TE         + target & frequency encoding
  V3_NORAW_TFIDF      + TF-IDF/SVD text components
  V3_NORAW_TE_TFIDF   + both
Pre-specified equal-weight stacks per set: STACK_A = mean(RIDGE, RF) (a-priori),
STACK_B = mean(RIDGE, MR2 multitask v2DJ) (conditional on the S_vs_C moderator, as in round 4).
"""
import sys, json, time, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('r3', HERE / '08_round3_features_outliers.py')
r3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r3)
cv, RES, PROC = r3.cv, r3.RES, r3.PROC
warnings.filterwarnings('ignore')
_mm = cv.make_model
def make_model_lowmem(*a, **k):
    m, kind = _mm(*a, **k)
    if hasattr(m, 'n_jobs'):
        m.set_params(n_jobs=4)
    return m, kind
cv.make_model = make_model_lowmem

Y3 = pd.read_parquet(PROC / 'train_yield_v3.parquet'); B3 = pd.read_parquet(PROC / 'train_dry_biomass_v3.parquet')
for x in (Y3, B3):
    x['exp_uid'] = x.study_id + '|' + x.experiment_key
    x['endpoint_is_yield'] = int(x is Y3)
    for c in ['h2_drought_supply_reported', 'h2_salinity_reported', 'h2_stress_duration_reported']:
        x[c + '_cat'] = np.select([x[c] == 1, x[c] == 0], ['REPORTED', 'NOT_REPORTED'], 'NOT_APPLICABLE')
cv.Y, cv.B = Y3, B3

H3_NUM = [c for c in Y3.columns if c.startswith('h3_') and pd.api.types.is_numeric_dtype(Y3[c])]
H3_CAT = ['h3_genus_main', 'h3_region', 'h3_n_applications_source', 'h3_soil_texture_source', 'h3_latitude_source']
TE_KEYS = ['h3_class_key', 'h3_cultivar_key', 'h3_country', 'h3_genus_main', 'h2_dujardin', 'h_stress_class']
K_SHRINK, N_SVD, SEEDS = 5.0, 10, [11, 22, 33]


class V3Featurizer(cv.Featurizer):
    TE, TFIDF = [], False

    def _te_map(self, df):
        g = df.groupby('study_id').target.mean().mean()
        maps = {}
        for c in self.TE:
            sm = df.groupby([df[c].astype(str), 'study_id']).target.mean().groupby(level=0).agg(['mean', 'size'])
            maps[c] = ((sm['size'] * sm['mean'] + K_SHRINK * g) / (sm['size'] + K_SHRINK)).to_dict(), \
                      np.log1p(sm['size']).to_dict()
        return g, maps

    def fit(self, df):
        super().fit(df)
        self.extra_cols = []
        if self.TE:
            self.g, self.maps = self._te_map(df)
            # grouped out-of-fold encodings for the training rows themselves
            st = np.array(sorted(df.study_id.unique())); rng = np.random.default_rng(0); rng.shuffle(st)
            grp = {s: i % 5 for i, s in enumerate(st)}
            gi = df.study_id.map(grp).values
            self.oof = {}
            for k in range(5):
                rest, part = df[gi != k], df[gi == k]
                g, maps = self._te_map(rest)
                for c in self.TE:
                    enc = part[c].astype(str).map(maps[c][0]).fillna(g).values
                    for cid, v in zip(part.contrast_id.values, enc):
                        self.oof[(c, cid)] = v
        if self.TFIDF:
            docs = df.groupby('study_id').h3_text_all.first()
            self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, max_features=3000,
                                       token_pattern=r'(?u)\b[a-z][a-z0-9\-]+\b')
            Xs = self.vec.fit_transform(docs.values)
            self.svd = TruncatedSVD(n_components=min(N_SVD, Xs.shape[1] - 1), random_state=0).fit(Xs)
        E = self._extra(df, training=True)
        self.e_mu, self.e_sd = E.mean(), E.std().replace(0, 1)
        return self

    def _extra(self, df, training=False):
        parts = {}
        for c in self.TE:
            full = df[c].astype(str).map(self.maps[c][0]).fillna(self.g).values
            if training:
                full = np.array([self.oof.get((c, cid), f) for cid, f in zip(df.contrast_id.values, full)])
            parts[f'TE__{c}'] = full
            parts[f'FREQ__{c}'] = df[c].astype(str).map(self.maps[c][1]).fillna(0).values
        if self.TFIDF:
            Z = self.svd.transform(self.vec.transform(df.h3_text_all.fillna('').values))
            for j in range(Z.shape[1]):
                parts[f'SVD__{j}'] = Z[:, j]
        return pd.DataFrame(parts, index=df.index)

    def transform(self, df, kind):
        X, cols = super().transform(df, kind)
        E = self._extra(df)
        if E.shape[1] == 0:
            return X, cols
        if kind == 'scaled':
            E = (E - self.e_mu) / self.e_sd
        return np.column_stack([X, E.values.astype(float)]), cols + list(E.columns)


cv.Featurizer = V3Featurizer


def fsets(ep):
    cat_ref, num_ref = r3.feats(ep, 'V2_DUJARDIN_FIX')
    raw_cat = set(cv.RAW_CAT)
    noraw_cat = [c for c in cat_ref if c not in raw_cat] + H3_CAT + ['h2_substrate_type', 'h2_application_phase', 'h2_stress_onset_phase',
                                                                     'h2_drought_supply_type', 'h2_salinity_measure_type']
    noraw_num = num_ref + H3_NUM + ['h2_drought_fc_pct', 'h2_drought_etc_pct', 'h2_salinity_nacl_mm', 'h2_salinity_ecw_dsm', 'h2_plant_density_m2']
    return {'REF_V2DJ': (cat_ref, num_ref, [], False),
            'V3_PARSED': (cat_ref + H3_CAT, num_ref + H3_NUM, [], False),
            'V3_NORAW': (noraw_cat, noraw_num, [], False),
            'V3_NORAW_TE': (noraw_cat, noraw_num, TE_KEYS, False),
            'V3_NORAW_TFIDF': (noraw_cat, noraw_num, [], True),
            'V3_NORAW_TE_TFIDF': (noraw_cat, noraw_num, TE_KEYS, True)}


def with_dj2(df):
    d = df.copy(); d['h_dujardin'] = d['h2_dujardin']; return d


def run(ep, seed, tau2_ref):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    other = cv.select('biomass' if ep == 'yield' else 'yield', cv.BASE)
    pool = pd.concat([df, other], ignore_index=True)
    df = df.reindex(columns=pool.columns)
    folds = cv.make_folds('study', seed)
    FS = fsets(ep)
    P = []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True)
        te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        trm = pool[pool.study_id.map(folds) != f].reset_index(drop=True)
        if len(te) == 0:
            continue
        out = {}
        mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
        out['MR0_3level_intercept'] = (mu, lo, hi)
        c = tr.target.mean(); h = np.quantile(np.abs(tr.target - c), 0.95)
        out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - h), np.full(len(te), c + h))
        mu, lo, hi, _, _ = cv.fit_mr(with_dj2(trm), with_dj2(te), 'MR2', ep, True)
        out['MR2_v2DJ_MULTITASK'] = (mu, lo, hi)
        for fs, (cat, num, tek, tfidf) in FS.items():
            V3Featurizer.TE, V3Featurizer.TFIDF = tek, tfidf
            for key in ('RIDGE', 'RF'):   # GBM dropped: weakest model in rounds 1-4
                p, lo, hi, hp, _ = cv.fit_predict_ml(key, tr, te, cat, num, 'ivw_re', tau2, 'study', seed + f)
                out[f'{key}|{fs}'] = (p, lo, hi)
            for nm, mem in [('STACK_A_RIDGE+RF', [f'RIDGE|{fs}', f'RF|{fs}']), ('STACK_B_RIDGE+MR2mt', [f'RIDGE|{fs}', 'MR2_v2DJ_MULTITASK'])]:
                p = np.mean([out[k][0] for k in mem], axis=0); hw = np.mean([(out[k][2] - out[k][1]) / 2 for k in mem], axis=0)
                out[f'{nm}|{fs}'] = (p, p - hw, p + hw)
        V3Featurizer.TE, V3Featurizer.TFIDF = [], False
        for nm, (p, lo, hi) in out.items():
            P.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, fold=f, model=nm, y=te.target,
                                       pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
    P = pd.concat(P, ignore_index=True)
    rows = []
    for nm, g in P.groupby('model'):
        model, fs = (nm.split('|') + [''])[:2]
        rows.append(dict(endpoint=ep, model=model, feature_set=fs, seed=seed, n_studies=g.study_id.nunique(),
                         **cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref))))
    return rows, P.assign(endpoint=ep, seed=seed)


if __name__ == '__main__':
    only = sys.argv[1:]                      # optional: 'yield' / 'biomass'
    tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
    out_csv = RES / 'cv_metrics_round5_v3.csv'
    allr = pd.read_csv(out_csv).to_dict('records') if out_csv.exists() else []
    done = {(r['endpoint'], r['seed']) for r in allr}
    allp = []
    for ep in ('yield', 'biomass'):
        if only and ep not in only:
            continue
        for s in SEEDS:
            if (ep, s) in done:
                continue
            t = time.time()
            r, p = run(ep, s, tau2_ref[ep]); allr += r; allp.append(p)
            pd.DataFrame(allr).to_csv(out_csv, index=False)
            p.to_parquet(RES / f'cv_oof_round5_{ep}_{s}.parquet', index=False)
            print(f'{ep} seed={s} {time.time() - t:.0f}s', flush=True)
    M = pd.DataFrame(allr)
    b = M[M.model == 'BASELINE_mean'][['endpoint', 'seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_base'})
    ref = M[M.feature_set == 'REF_V2DJ'][['endpoint', 'model', 'seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_ref'})
    j = M.merge(b, on=['endpoint', 'seed']).merge(ref, on=['endpoint', 'model', 'seed'], how='left')
    j['d_vs_mean_pct'] = 100 * (j.RMSE - j.RMSE_base) / j.RMSE_base
    j['d_vs_REF_pct'] = 100 * (j.RMSE - j.RMSE_ref) / j.RMSE_ref
    S = j.groupby(['endpoint', 'model', 'feature_set']).agg(
        seeds=('seed', 'nunique'), RMSE=('RMSE', 'mean'), RMSE_sd=('RMSE', 'std'), MAE=('MAE', 'mean'), R2=('R2', 'mean'),
        wRMSE=('wRMSE', 'mean'), coverage95=('coverage95', 'mean'), d_vs_mean_pct=('d_vs_mean_pct', 'mean'),
        d_vs_REF_pct=('d_vs_REF_pct', 'mean'), better_than_REF_all_seeds=('d_vs_REF_pct', lambda x: bool((x < 0).all()))).reset_index()
    S.sort_values(['endpoint', 'RMSE']).to_csv(RES / 'cv_metrics_round5_summary.csv', index=False)
    pd.set_option('display.width', 250)
    print(S.sort_values(['endpoint', 'RMSE']).round(4).to_string())
