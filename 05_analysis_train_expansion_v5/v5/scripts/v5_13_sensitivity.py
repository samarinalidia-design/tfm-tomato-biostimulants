"""Block 3: sensitivity of results to data-preparation decisions (TRAIN only; TEST not read).

Each scenario changes ONE decision. Within a scenario all methods use the same rows (same study composition).
  Meta   : 3-level REML (study / experiment / contrast) WITH shared-control covariance (cov = min(CV_c^2/n_c) for contrasts
           sharing shared_control_id), CR1 cluster-robust CI (study), PI for a new study.
  CV     : nested CV grouped by dependency cluster (seeds 11, 22): BASELINE_mean, MR0, RIDGE_REF (weights 1/(v + tau2)).
Scenarios
  MAIN                 V5 default (author SD, else study CV%/LSD, else CV-bar; median n; shared-control covariance)
  VAR_CVBAR_ALL        CV-bar for every group (Nakagawa method 1), same rows
  VAR_IMPUTED_x0.5     imputed CVs halved, same rows                  VAR_IMPUTED_x1.5   imputed CVs x1.5, same rows
  N_IMPUTED_3          missing n set to 3 instead of the median 4, same rows
  SC_NO_COVARIANCE     shared-control covariance ignored (meta only; ML identical by construction), same rows
  SC_ONE_PER_CONTROL   one contrast per shared control (first), subset
  AUTHOR_SD_ONLY       contrasts with author SD/SE and n for both arms, subset
  DEF_KNOWN            yield: tiers STRICT/ASSUMED (scope/window known or assumed); biomass: dry basis confirmed, subset
  DEF_NO_UNSPECIFIED   yield: yield_scope != UNSPECIFIED; biomass: all timepoints instead of the last, rows change
  WITH_BOXPLOTS        box-plot centres included as means, rows change
"""
import numpy as np
import pandas as pd
from scipy import optimize, linalg, stats
from v5_common import cv, fsets, SCHEME, RES, V5Featurizer
import v5_02_cv_select as S

OUT = RES / 'sensitivity'; OUT.mkdir(exist_ok=True)
SEEDS2 = [11]   # seed 22 only for the first two scenarios (compute time)


class SCMeta:
    """y = mu + u_study + u_exp + e + sampling;  Var(sampling) = V with shared-control covariance."""

    def fit(self, y, V_blocks, study, exp, X):
        self.y, self.X = np.asarray(y, float), np.asarray(X, float)
        self.blocks = []
        for s in np.unique(study):
            idx = np.where(study == s)[0]
            e = exp[idx]; Z = (e[:, None] == e[None, :]).astype(float)
            self.blocks.append((idx, Z, V_blocks[s]))
        r = optimize.minimize(self._nll, np.log([0.05, 0.02, 0.02]), method='L-BFGS-B', bounds=[(-14, 3)] * 3)
        self.s2 = np.exp(r.x); self._fin(); return self

    def _M(self, Z, V, s2):
        return V + s2[0] + s2[1] * Z + s2[2] * np.eye(len(Z))

    def _nll(self, th):
        s2 = np.exp(th); p = self.X.shape[1]; A = np.zeros((p, p)); bvec = np.zeros(p); ld = 0; yWy = 0
        for idx, Z, V in self.blocks:
            try:
                c = linalg.cho_factor(self._M(Z, V, s2), lower=True)
            except linalg.LinAlgError:
                return 1e10
            ld += 2 * np.log(np.diag(c[0])).sum(); Xi, yi = self.X[idx], self.y[idx]
            WX, Wy = linalg.cho_solve(c, Xi), linalg.cho_solve(c, yi)
            A += Xi.T @ WX; bvec += Xi.T @ Wy; yWy += yi @ Wy
        cb = linalg.cho_factor(A); b = linalg.cho_solve(cb, bvec)
        return 0.5 * (ld + yWy - bvec @ b + 2 * np.log(np.diag(cb[0])).sum())

    def _fin(self):
        p = self.X.shape[1]; A = np.zeros((p, p)); bvec = np.zeros(p); Ws = []
        for idx, Z, V in self.blocks:
            W = linalg.inv(self._M(Z, V, self.s2)); Ws.append(W)
            A += self.X[idx].T @ W @ self.X[idx]; bvec += self.X[idx].T @ W @ self.y[idx]
        Ai = linalg.pinvh(A); self.b = Ai @ bvec
        meat = np.zeros((p, p))
        for (idx, _, _), W in zip(self.blocks, Ws):
            u = self.X[idx].T @ W @ (self.y[idx] - self.X[idx] @ self.b); meat += np.outer(u, u)
        k = len(self.blocks); self.k = k
        self.vcov = k / max(k - p, 1) * Ai @ meat @ Ai


def v_blocks(df, cov=True):
    out = {}
    cc = (df.cv_c ** 2 / df.n_c).values
    for s, idx in df.groupby('study_id').indices.items():
        V = np.diag(df.v.values[idx]).astype(float)
        if cov:
            sc = df.shared_control_id.values[idx]
            for a in range(len(idx)):
                for b in range(a + 1, len(idx)):
                    if isinstance(sc[a], str) and sc[a] and sc[a] == sc[b]:
                        V[a, b] = V[b, a] = min(cc[idx[a]], cc[idx[b]])
        out[s] = V
    return out


def scenario(ep, name):
    x = cv.table(ep).copy()
    x['cv_t'], x['cv_c'], x['n_t'], x['n_c'] = x.cv_used_t, x.cv_used_c, x.n_imp_t, x.n_imp_c
    keep = x.is_boxplot == 0
    if ep == 'biomass':
        keep &= x.is_last_timepoint == 1
    cov = True
    if name == 'VAR_CVBAR_ALL':
        cvb = float(pd.read_csv(RES / 'variance_imputation_v5.csv').set_index('table').loc[ep, 'CV_bar'])
        x['cv_t'] = cvb; x['cv_c'] = cvb
    elif name.startswith('VAR_IMPUTED_x'):
        f = float(name.split('x')[1])
        x.loc[x.cv_source_t == 'IMPUTED_MEAN_CV', 'cv_t'] *= f; x.loc[x.cv_source_c == 'IMPUTED_MEAN_CV', 'cv_c'] *= f
    elif name == 'N_IMPUTED_3':
        x.loc[x.n_imputed_t == 1, 'n_t'] = 3; x.loc[x.n_imputed_c == 1, 'n_c'] = 3
    elif name == 'SC_NO_COVARIANCE':
        cov = False
    elif name == 'SC_ONE_PER_CONTROL':
        keep &= ~x.duplicated('shared_control_id') | x.shared_control_id.isna()
    elif name == 'AUTHOR_SD_ONLY':
        keep &= x.variance_from_author_sd == 1
    elif name == 'DEF_KNOWN':
        keep &= x.yield_tier.isin(['STRICT', 'ASSUMED']) if ep == 'yield' else (x.dry_basis_confirmed == 1)
    elif name == 'DEF_NO_UNSPECIFIED':
        if ep == 'yield':
            keep &= x.yield_scope != 'UNSPECIFIED'
        else:
            keep = x.is_boxplot == 0
    elif name == 'WITH_BOXPLOTS':
        keep = (x.is_last_timepoint == 1) if ep == 'biomass' else pd.Series(True, index=x.index)
    x = x[keep].reset_index(drop=True)
    x['v'] = x.cv_t ** 2 / x.n_t + x.cv_c ** 2 / x.n_c
    x['target'] = x.effect
    return x, cov


def meta(x, cov):
    m = SCMeta().fit(x.target.values, v_blocks(x, cov), x.study_id.values, x.exp_uid.values, np.ones((len(x), 1)))
    se = np.sqrt(m.vcov[0, 0]); t = stats.t.ppf(0.975, max(m.k - 1, 1)); mu = m.b[0]; tau2 = m.s2.sum()
    return dict(mu=mu, ci_lo=mu - t * se, ci_hi=mu + t * se, pi_lo=mu - t * np.sqrt(tau2 + se ** 2), pi_hi=mu + t * np.sqrt(tau2 + se ** 2),
                tau2_study=m.s2[0], tau2_total=tau2, k_studies=m.k, k=len(x))


def cv_run(x, ep, seed):
    folds = cv.make_folds(SCHEME, seed); cat, num, _, _ = fsets(ep)['REF']
    P = []
    for f in range(cv.N_OUTER):
        tr = x[x.study_id.map(folds) != f].reset_index(drop=True); te = x[x.study_id.map(folds) == f].reset_index(drop=True)
        if len(te) == 0 or tr.study_id.nunique() < 5:
            continue
        mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
        c = tr.target.mean(); hw = np.quantile(np.abs(tr.target - c), 0.95)
        V5Featurizer.CONTEXT = f'SENS|{ep}'
        p, plo, phi, _, _ = cv.fit_predict_ml('RIDGE', tr, te, cat, num, 'ivw_re', tau2, SCHEME, seed + f)
        for nm, (a, l, h) in {'BASELINE_mean': (np.full(len(te), c), np.full(len(te), c - hw), np.full(len(te), c + hw)),
                              'MR0': (mu, lo, hi), 'RIDGE_REF': (p, plo, phi)}.items():
            P.append(pd.DataFrame(dict(model=nm, study_id=te.study_id, y=te.target, pred=a, lo=l, hi=h)))
    P = pd.concat(P)
    return [dict(model=m, RMSE=float(np.sqrt(np.mean((g.pred - g.y) ** 2))), coverage95=float(np.mean((g.y >= g.lo) & (g.y <= g.hi))),
                 width=float(np.mean(g.hi - g.lo))) for m, g in P.groupby('model')]


SCEN = ['MAIN', 'VAR_CVBAR_ALL', 'VAR_IMPUTED_x0.5', 'VAR_IMPUTED_x1.5', 'N_IMPUTED_3', 'SC_NO_COVARIANCE', 'SC_ONE_PER_CONTROL',
        'AUTHOR_SD_ONLY', 'DEF_KNOWN', 'DEF_NO_UNSPECIFIED', 'WITH_BOXPLOTS']

if __name__ == '__main__':
    rows = []
    part = OUT / 'sensitivity_rows.csv'
    done = set(map(tuple, pd.read_csv(part)[['endpoint', 'scenario']].drop_duplicates().values)) if part.exists() else set()
    rows = pd.read_csv(part).to_dict('records') if part.exists() else []
    for ep in ('yield', 'biomass'):
        for sc in SCEN:
            if (ep, sc) in done:
                continue
            x, cov = scenario(ep, sc)
            mm = meta(x, cov)
            if sc == 'SC_NO_COVARIANCE':
                cvr = [dict(r, seed=s) for s in SEEDS2 for r in [dict(rr) for rr in pd.read_csv(part).query("endpoint == @ep and scenario == 'MAIN'")[['model', 'RMSE', 'coverage95', 'width']].to_dict('records')]] \
                    if part.exists() else []
            else:
                cvr = [dict(r, seed=s) for s in SEEDS2 for r in cv_run(x, ep, s)]
            for r in cvr:
                rows.append(dict(endpoint=ep, scenario=sc, studies=x.study_id.nunique(), contrasts=len(x), **mm, **r))
            pd.DataFrame(rows).to_csv(part, index=False)
            print(ep, sc, len(x), x.study_id.nunique(), f'mu={100 * (np.exp(mm["mu"]) - 1):.1f}%', flush=True)
    R = pd.DataFrame(rows)
    A = R.groupby(['endpoint', 'scenario', 'model']).mean(numeric_only=True).reset_index()
    base = A[A.model == 'BASELINE_mean'][['endpoint', 'scenario', 'RMSE']].rename(columns={'RMSE': 'RMSE_mean'})
    A = A.merge(base, on=['endpoint', 'scenario']); A['ridge_gain_pct'] = 100 * (A.RMSE - A.RMSE_mean) / A.RMSE_mean
    A.to_csv(OUT / 'sensitivity_summary.csv', index=False)
    pd.set_option('display.width', 250)
    print(A[A.model == 'RIDGE_REF'][['endpoint', 'scenario', 'studies', 'contrasts', 'mu', 'ci_lo', 'ci_hi', 'tau2_total', 'RMSE', 'RMSE_mean', 'ridge_gain_pct', 'coverage95']].round(4).to_string())
