"""V5 shared modelling state: loads the v5 TRAIN (and optionally TEST) tables into the CV engine of rounds 1-7
(02_cv_models.py / 08_round3 / 12_round5), adds duplicate-feature removal learnt on training rows, and defines
the pre-specified candidate models.

Duplicate features: after featurisation on the TRAINING rows of each fit, columns that are exact duplicates of an
earlier column (or constant) are dropped; the same columns are dropped from validation/TEST rows. Audit in
v5/results/feature_duplicates_audit.csv.
"""
import sys, json, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd

V5 = pathlib.Path(__file__).resolve().parents[1]
ROOT = V5.parent
sys.path.insert(0, str(ROOT / 'scripts'))
warnings.filterwarnings('ignore')
_argv = sys.argv; sys.argv = sys.argv[:1]
spec = importlib.util.spec_from_file_location('r5', ROOT / 'scripts/12_round5_v3.py')
r5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r5)
sys.argv = _argv
cv, r3 = r5.cv, r5.r3
DATA, RES = V5 / 'data', V5 / 'results'
RES.mkdir(exist_ok=True)


def prep(x, is_yield):
    x = x.copy()
    x['exp_uid'] = x.study_id + '|' + x.experiment_key
    x['endpoint_is_yield'] = int(is_yield)
    for c in ['h2_drought_supply_reported', 'h2_salinity_reported', 'h2_stress_duration_reported']:
        x[c + '_cat'] = np.select([x[c] == 1, x[c] == 0], ['REPORTED', 'NOT_REPORTED'], 'NOT_APPLICABLE')
    return x


def load(role):
    y = prep(pd.read_parquet(DATA / f'{role}_yield.parquet'), True)
    b = prep(pd.read_parquet(DATA / f'{role}_dry_biomass.parquet'), False)
    return y, b


Y, B = load('train')


def load_test():
    """TEST tables are read only by the TEST step (v5_04) and by the descriptive figures, never during selection/fitting."""
    ty, tb = load('test')
    ty = ty.reindex(columns=list(dict.fromkeys(list(ty.columns) + list(Y.columns))))
    tb = tb.reindex(columns=list(dict.fromkeys(list(tb.columns) + list(B.columns))))
    return ty, tb


def set_train(y, b):
    cv.Y, cv.B = y, b
    cv.ALL = pd.concat([y[['study_id', 'dependency_cluster_id']], b[['study_id', 'dependency_cluster_id']]]).drop_duplicates()
    assert cv.ALL.groupby('study_id').dependency_cluster_id.nunique().max() == 1
    cv.STUDY2CLUSTER = cv.ALL.set_index('study_id').dependency_cluster_id
    cv.ROWS_PER_STUDY = pd.concat([y.study_id, b.study_id]).value_counts()


set_train(Y, B)

# ------------------------------------------------------------------ duplicate-feature removal (learnt on training rows)
DUP_AUDIT = []
_Base = r5.V3Featurizer


class V5Featurizer(_Base):
    CONTEXT = ''

    def fit(self, df):
        super().fit(df)
        X, cols = _Base.transform(self, df, 'imputed')
        Xd = pd.DataFrame(X, columns=cols)
        const = Xd.nunique() <= 1
        dup = Xd.T.duplicated()
        self.keep = [i for i, c in enumerate(cols) if not (const.iloc[i] or dup.iloc[i])]
        self.dropped = [(c, 'CONSTANT' if const.iloc[i] else 'EXACT_DUPLICATE') for i, c in enumerate(cols) if i not in set(self.keep)]
        DUP_AUDIT.append(dict(context=V5Featurizer.CONTEXT, n_columns=len(cols), n_kept=len(self.keep),
                              dropped_duplicates=';'.join(c for c, k in self.dropped if k == 'EXACT_DUPLICATE'),
                              n_constant=sum(k == 'CONSTANT' for _, k in self.dropped)))
        return self

    def transform(self, df, kind):
        X, cols = super().transform(df, kind)
        return X[:, self.keep], [cols[i] for i in self.keep]


cv.Featurizer = V5Featurizer

# ------------------------------------------------------------------ feature sets
H3_NUM, H3_CAT, TE_KEYS = r5.H3_NUM, r5.H3_CAT, r5.TE_KEYS


def fsets(ep):
    """REF = round-3/4 a-priori set (du Jardin v2); V3TE / V3TETF = round-5 numeric recoding (+ in-fold TE / TF-IDF)."""
    cat_ref, num_ref = r3.feats(ep, 'V2_DUJARDIN_FIX')
    # v5: the harmonised stress class now includes COMBINED / CHEMICAL_TOXICITY; h3_stress_combined follows it
    fs = r5.fsets(ep)
    return {'REF': (cat_ref, num_ref, [], False), 'V3TE': fs['V3_NORAW_TE'], 'V3TETF': fs['V3_NORAW_TE_TFIDF']}


def with_dj2(df):
    d = df.copy(); d['h_dujardin'] = d['h2_dujardin']; return d


SEEDS = [11, 22, 33]
SCHEME = 'cluster'          # outer and inner folds grouped by dependency_cluster_id
