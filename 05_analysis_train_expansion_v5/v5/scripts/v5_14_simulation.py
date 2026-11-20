"""Block 4: simulation with known truth for the V5 procedure (CV-bar variance imputation + 3-level REML with
shared-control covariance, cluster-robust CI).

Data-generating process (mirrors the TRAIN structure):
  K = 60 studies; 1-2 experiments per study; per experiment one control + 1-4 treatment arms sharing it; n per arm 3-6.
  study CV_s ~ lognormal(log 0.25, 0.4); control mean 10.
  true lnRR theta_ij = mu + b * x_ij + u_i + w_ij,  u_i ~ N(0, tau_b^2), w_ij ~ N(0, (0.7 tau_b)^2), x_ij ~ Bernoulli(0.5)
  (mu = 0.30, b = 0.15 -> population mean effect E[theta] = 0.375). Observed arm means ~ N(mean, (CV_s mean)^2 / n).
  SDs missing for whole studies with probability p_miss: MCAR, or MNAR (probability rises with the study's true effect:
  logit p = logit p_miss + 2 * z(u_i), i.e. studies with large effects more often omit SDs).
Estimands / metrics (R replications per cell):
  pooled mean effect: bias, RMSE, 95 % CI coverage and width for
     CC      complete-case (studies with SDs only), shared-control covariance
     V5      CV-bar imputation for missing SDs (n-weighted mean study CV of reporting studies) + shared-control covariance
     V5_DIAG same imputation, covariance ignored
     UNW     unweighted mean of study means, t-CI
  new-study prediction (20 new studies per replication): RMSE and 95 % PI coverage for observed new contrasts, for the
     pooled mean (V5) vs the meta-regression with the design moderator x (V5_MR).
"""
import itertools, time, pathlib
import numpy as np
import pandas as pd
from scipy import optimize, linalg, stats
from joblib import Parallel, delayed

V5 = pathlib.Path(__file__).resolve().parents[1]
OUT = V5 / 'results/simulation'; OUT.mkdir(parents=True, exist_ok=True)
MU, B, K, R = 0.30, 0.15, 60, 200
TRUE_MEAN = MU + 0.5 * B


class SCMeta:
    def fit(self, y, blocks, X):
        self.y, self.X, self.blocks = y, X, blocks
        r = optimize.minimize(self._nll, np.log([0.05, 0.02]), method='L-BFGS-B', bounds=[(-12, 2)] * 2)
        self.s2 = np.exp(r.x); self._fin(); return self

    def _M(self, V, s2):
        return V + s2[0] + s2[1] * np.eye(len(V))

    def _nll(self, th):
        s2 = np.exp(th); p = self.X.shape[1]; A = np.zeros((p, p)); bv = np.zeros(p); ld = 0; yWy = 0
        for idx, V in self.blocks:
            try:
                c = linalg.cho_factor(self._M(V, s2), lower=True)
            except linalg.LinAlgError:
                return 1e10
            ld += 2 * np.log(np.diag(c[0])).sum(); Xi, yi = self.X[idx], self.y[idx]
            A += Xi.T @ linalg.cho_solve(c, Xi); Wy = linalg.cho_solve(c, yi); bv += Xi.T @ Wy; yWy += yi @ Wy
        cb = linalg.cho_factor(A); b = linalg.cho_solve(cb, bv)
        return 0.5 * (ld + yWy - bv @ b + 2 * np.log(np.diag(cb[0])).sum())

    def _fin(self):
        p = self.X.shape[1]; A = np.zeros((p, p)); bv = np.zeros(p); Ws = []
        for idx, V in self.blocks:
            W = linalg.inv(self._M(V, self.s2)); Ws.append(W); A += self.X[idx].T @ W @ self.X[idx]; bv += self.X[idx].T @ W @ self.y[idx]
        Ai = linalg.pinvh(A); self.b = Ai @ bv; meat = np.zeros((p, p))
        for (idx, _), W in zip(self.blocks, Ws):
            u = self.X[idx].T @ W @ (self.y[idx] - self.X[idx] @ self.b); meat += np.outer(u, u)
        self.k = len(self.blocks); self.vcov = self.k / max(self.k - p, 1) * Ai @ meat @ Ai


def simulate(rng, k, tau_b, p_miss, mech):
    rows = []
    u = rng.normal(0, tau_b, k)
    z = (u - u.mean()) / (u.std() + 1e-9)
    pm = np.full(k, p_miss) if mech == 'MCAR' else 1 / (1 + np.exp(-(np.log(max(p_miss, 1e-6) / max(1 - p_miss, 1e-6)) + 2 * z)))
    if p_miss == 0:
        pm[:] = 0
    miss = rng.uniform(size=k) < pm
    for i in range(k):
        cvs = np.exp(rng.normal(np.log(0.25), 0.4))
        for e in range(rng.integers(1, 3)):
            nc = rng.integers(3, 7); mc = 10.0; obs_c = rng.normal(mc, cvs * mc / np.sqrt(nc)); sdc = cvs * mc * np.sqrt(rng.chisquare(nc - 1) / (nc - 1))
            for a in range(rng.integers(1, 5)):
                x = rng.integers(0, 2); th = MU + B * x + u[i] + rng.normal(0, 0.7 * tau_b)
                nt = rng.integers(3, 7); mt = mc * np.exp(th); obs_t = rng.normal(mt, cvs * mt / np.sqrt(nt))
                sdt = cvs * mt * np.sqrt(rng.chisquare(nt - 1) / (nt - 1))
                if obs_t <= 0 or obs_c <= 0:
                    continue
                rows.append(dict(study=i, exp=f'{i}_{e}', ctrl=f'{i}_{e}', x=x, theta=th, y=np.log(obs_t / obs_c), mt=obs_t, mc=obs_c,
                                 sdt=sdt, sdc=sdc, nt=nt, nc=nc, missing=miss[i]))
    return pd.DataFrame(rows)


def blocks(d, cvt, cvc, cov=True):
    out = []
    for s, idx in d.groupby('study').indices.items():
        v = cvt[idx] ** 2 / d.nt.values[idx] + cvc[idx] ** 2 / d.nc.values[idx]
        V = np.diag(v)
        if cov:
            ctrl = d.ctrl.values[idx]; cc = cvc[idx] ** 2 / d.nc.values[idx]
            same = ctrl[:, None] == ctrl[None, :]
            V = np.where(same & ~np.eye(len(idx), dtype=bool), np.minimum(cc[:, None], cc[None, :]), V)
        out.append((idx, V))
    return out


def est(m):
    se = np.sqrt(m.vcov[0, 0]); t = stats.t.ppf(0.975, max(m.k - 1, 1)); return m.b[0], m.b[0] - t * se, m.b[0] + t * se


def one(seed, tau_b, p_miss, mech):
    rng = np.random.default_rng(seed)
    d = simulate(rng, K, tau_b, p_miss, mech).reset_index(drop=True)
    cvt_own, cvc_own = d.sdt / d.mt, d.sdc / d.mc
    rep = d[~d.missing]
    st = rep.assign(cv=cvt_own[~d.missing]).groupby('study').agg(cv=('cv', 'mean'), n=('nt', 'mean'))
    cvbar = np.average(st.cv, weights=st.n) if len(st) else 0.25
    cvt = np.where(d.missing, cvbar, cvt_own); cvc = np.where(d.missing, cvbar, cvc_own)
    out = []
    X1 = np.ones((len(d), 1))
    for name in ['CC', 'V5', 'V5_DIAG', 'UNW']:
        try:
            if name == 'CC':
                dd = d[~d.missing].reset_index(drop=True)
                if dd.study.nunique() < 3:
                    continue
                m = SCMeta().fit(dd.y.values, blocks(dd, (dd.sdt / dd.mt).values, (dd.sdc / dd.mc).values), np.ones((len(dd), 1))); mu, lo, hi = est(m)
            elif name in ('V5', 'V5_DIAG'):
                m = SCMeta().fit(d.y.values, blocks(d, cvt, cvc, name == 'V5'), X1); mu, lo, hi = est(m)
                if name == 'V5':
                    m5 = m
            else:
                sm = d.groupby('study').y.mean(); mu = sm.mean(); se = sm.std() / np.sqrt(len(sm)); t = stats.t.ppf(0.975, len(sm) - 1)
                lo, hi = mu - t * se, mu + t * se
            out.append(dict(seed=seed, tau_b=tau_b, p_miss=p_miss, mech=mech, method=name, est=mu, lo=lo, hi=hi,
                            err=mu - TRUE_MEAN, cover=int(lo <= TRUE_MEAN <= hi), width=hi - lo))
        except Exception:
            continue
    # new-study prediction: pooled mean vs meta-regression with the moderator
    new = simulate(np.random.default_rng(seed + 10 ** 6), 20, tau_b, 0.0, 'MCAR')
    mr = SCMeta().fit(d.y.values, blocks(d, cvt, cvc, True), np.column_stack([np.ones(len(d)), d.x.values]))
    vnew = (new.sdt / new.mt) ** 2 / new.nt + (new.sdc / new.mc) ** 2 / new.nc
    for name, mdl, Xn in [('V5_pooled', m5, np.ones((len(new), 1))), ('V5_MR_moderator', mr, np.column_stack([np.ones(len(new)), new.x.values]))]:
        p = Xn @ mdl.b; sfit = np.sqrt(np.einsum('ij,jk,ik->i', Xn, mdl.vcov, Xn)); sd = np.sqrt(mdl.s2.sum() + sfit ** 2 + vnew)
        out.append(dict(seed=seed, tau_b=tau_b, p_miss=p_miss, mech=mech, method=name, est=np.nan, lo=np.nan, hi=np.nan,
                        err=float(np.sqrt(np.mean((p - new.y) ** 2))), cover=float(np.mean(np.abs(new.y - p) <= 1.96 * sd)), width=float(np.mean(2 * 1.96 * sd))))
    return out


if __name__ == '__main__':
    t0 = time.time()
    grid = list(itertools.product([0.1, 0.3, 0.5], [0.0, 0.3, 0.6, 0.8], ['MCAR', 'MNAR']))
    grid = [g for g in grid if not (g[1] == 0 and g[2] == 'MNAR')]
    jobs = [(1000 * gi + r, *g) for gi, g in enumerate(grid) for r in range(R)]
    res = Parallel(n_jobs=4, verbose=0)(delayed(one)(*j) for j in jobs)
    D = pd.DataFrame([r for rr in res for r in rr]); D.to_csv(OUT / 'simulation_reps.csv', index=False)
    A = D.groupby(['tau_b', 'p_miss', 'mech', 'method']).agg(reps=('seed', 'nunique'), bias=('err', 'mean'), rmse=('err', lambda e: float(np.sqrt(np.mean(e ** 2)))),
                                                            coverage=('cover', 'mean'), width=('width', 'mean')).reset_index()
    pred = D.method.str.startswith('V5_') & D.method.isin(['V5_pooled', 'V5_MR_moderator'])
    P = D[pred].groupby(['tau_b', 'p_miss', 'mech', 'method']).agg(rmse_new=('err', 'mean'), pi_coverage=('cover', 'mean'), pi_width=('width', 'mean')).reset_index()
    A = A[~A.method.isin(['V5_pooled', 'V5_MR_moderator'])]
    A.to_csv(OUT / 'simulation_summary_pooled.csv', index=False); P.to_csv(OUT / 'simulation_summary_prediction.csv', index=False)
    pd.set_option('display.width', 220)
    print(A.round(3).to_string()); print(P.round(3).to_string()); print(f'{time.time() - t0:.0f}s')
