"""Three-level random-effects meta-regression (study / experiment / contrast) fitted by REML,
cluster-robust variance estimation (CR1 with small-sample factor), heterogeneity (I^2) and
influence diagnostics. Pure numpy/scipy implementation (no R available on this machine).
"""
import numpy as np
from scipy import optimize, linalg, stats


class ThreeLevelMeta:
    def __init__(self, ridge=1e-8):
        self.ridge = ridge

    # -------------------------------------------------------------- fitting
    def fit(self, y, v, X, study, exp, init=None):
        y = np.asarray(y, float); v = np.asarray(v, float); X = np.asarray(X, float)
        study = np.asarray(study); exp = np.asarray(exp)
        self.p = X.shape[1]
        blocks = []
        for s in np.unique(study):
            idx = np.where(study == s)[0]
            e = exp[idx]
            Z = (e[:, None] == np.unique(e)[None, :]).astype(float)
            blocks.append((idx, Z @ Z.T))
        self._blocks, self._y, self._v, self._X = blocks, y, v, X
        x0 = np.log(np.maximum(init, 1e-5)) if init is not None else np.log([0.02, 0.01, 0.02])
        res = optimize.minimize(self._nll, x0, method='L-BFGS-B', bounds=[(-14, 3)] * 3,
                                options=dict(maxiter=200))
        self.sigma2 = np.exp(res.x)
        self.converged = bool(res.success)
        self._finalize()
        return self

    def _M(self, idx, ZZ, s2):
        n = len(idx)
        return np.diag(self._v[idx] + s2[2]) + s2[0] + s2[1] * ZZ

    def _nll(self, th, reml=True):
        s2 = np.exp(th)
        p = self.p
        XtWX = np.zeros((p, p)); XtWy = np.zeros(p); logdet = 0.0; cache = []
        for idx, ZZ in self._blocks:
            M = self._M(idx, ZZ, s2)
            try:
                c = linalg.cho_factor(M, lower=True, check_finite=False)
            except linalg.LinAlgError:
                return 1e10
            logdet += 2 * np.log(np.diag(c[0])).sum()
            Xi, yi = self._X[idx], self._y[idx]
            WX = linalg.cho_solve(c, Xi, check_finite=False); Wy = linalg.cho_solve(c, yi, check_finite=False)
            XtWX += Xi.T @ WX; XtWy += Xi.T @ Wy
            cache.append((yi, Wy, WX))
        XtWX += self.ridge * np.eye(p)
        try:
            cb = linalg.cho_factor(XtWX, check_finite=False)
        except linalg.LinAlgError:
            return 1e10
        b = linalg.cho_solve(cb, XtWy, check_finite=False)
        # r'M^-1 r with r = y - Xb and b the GLS solution equals y'M^-1 y - b'X'M^-1 y
        yWy = sum(yi @ Wy for yi, Wy, _ in cache)
        rWr = yWy - XtWy @ b
        ll = logdet + rWr
        if reml:
            ll += 2 * np.log(np.diag(cb[0])).sum()
        return 0.5 * ll

    def _finalize(self):
        s2, p = self.sigma2, self.p
        XtWX = np.zeros((p, p)); XtWy = np.zeros(p); self._W = []
        for idx, ZZ in self._blocks:
            W = linalg.inv(self._M(idx, ZZ, s2))
            self._W.append(W)
            XtWX += self._X[idx].T @ W @ self._X[idx]; XtWy += self._X[idx].T @ W @ self._y[idx]
        XtWX += self.ridge * np.eye(p)
        self.XtWX_inv = linalg.pinvh(XtWX)
        self.b = self.XtWX_inv @ XtWy
        self.vcov_model = self.XtWX_inv
        # cluster-robust (study-clustered) sandwich, CR1 small-sample factor
        meat = np.zeros((p, p))
        for (idx, _), W in zip(self._blocks, self._W):
            e = self._y[idx] - self._X[idx] @ self.b
            u = self._X[idx].T @ W @ e
            meat += np.outer(u, u)
        k = len(self._blocks)
        fac = k / max(k - p, 1)
        self.vcov_robust = fac * self.XtWX_inv @ meat @ self.XtWX_inv
        self.k_studies = k
        self.df_robust = max(k - p, 1)

    # -------------------------------------------------------------- outputs
    def predict(self, X, v=None):
        X = np.asarray(X, float)
        mu = X @ self.b
        se_fit = np.sqrt(np.maximum(np.einsum('ij,jk,ik->i', X, self.vcov_robust, X), 0))
        tau2 = self.sigma2.sum()
        pv = se_fit ** 2 + tau2 + (np.asarray(v, float) if v is not None else 0.0)
        return mu, np.sqrt(pv)

    def coef_table(self, names):
        se_r = np.sqrt(np.diag(self.vcov_robust)); se_m = np.sqrt(np.diag(self.vcov_model))
        t = self.b / se_r
        pval = 2 * stats.t.sf(np.abs(t), self.df_robust)
        return [dict(term=n, estimate=b, se_model=sm, se_robust_CR1=sr, t_robust=tt, df=self.df_robust, p_robust=pp)
                for n, b, sm, sr, tt, pp in zip(names, self.b, se_m, se_r, t, pval)]

    def heterogeneity(self):
        v = self._v; w = 1 / v; k = len(v)
        v_typ = (k - 1) * w.sum() / (w.sum() ** 2 - (w ** 2).sum())
        s = self.sigma2; tot = s.sum() + v_typ
        # Cochran Q (fixed-effect, about the weighted model fit)
        Xw = self._X * w[:, None]
        bfe = linalg.lstsq(self._X.T @ Xw, Xw.T @ self._y)[0]
        Q = float((w * (self._y - self._X @ bfe) ** 2).sum())
        return dict(tau2_study=s[0], tau2_experiment=s[1], tau2_contrast=s[2], tau2_total=s.sum(),
                    v_typical=v_typ, I2_total=s.sum() / tot, I2_study=s[0] / tot,
                    I2_experiment=s[1] / tot, I2_contrast=s[2] / tot, Q=Q, Q_df=k - self.p,
                    Q_p=float(stats.chi2.sf(Q, k - self.p)), k=k, n_studies=self.k_studies)
