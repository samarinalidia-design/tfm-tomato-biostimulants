"""Feature sets, in-fold preprocessing and model families for SynerPlant Yield V2.

Everything learned from data (imputation medians, scaling, rare-level pooling, coverage filter, target encodings,
variance components, hyper-parameters) is fitted on the training part of a split only.
"""
from __future__ import annotations
import warnings
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge, ElasticNet, HuberRegressor, QuantileRegressor
from sklearn.ensemble import HistGradientBoostingRegressor

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ feature sets
F0 = {"num": ["application_count", "relative_dose", "relative_stress_level"],
      "cat": ["stress_family", "biostimulant_class_v1", "application_route", "cultivation_system",
              "application_timing", "genotype_type"], "missing_ind": False}
F1 = {"num": ["log_application_count", "relative_dose", "relative_stress_level"],
      "cat": ["stress_family", "biostimulant_class", "application_route", "cultivation_system",
              "application_timing", "genotype_type"], "missing_ind": True}
F2 = {"num": F1["num"] + ["salinity_dSm_equiv", "drought_supply_pct", "stress_duration_days"],
      "cat": F1["cat"] + ["stress_timing", "substrate_type"], "missing_ind": True}
F3 = {"num": F2["num"], "cat": F2["cat"] + ["yield_scope_v2", "harvest_window_v2", "denominator_v2"],
      "missing_ind": True}
F4 = {**F3, "eb_encode": ["stress_family", "biostimulant_class", "application_route"]}
FEATURE_SETS = {"F0": F0, "F1": F1, "F2": F2, "F3": F3, "F4": F4}
MIN_GROUP_COVERAGE = 0.20     # V1 decision D4, kept
RARE_LEVEL_MIN_GROUPS = 5     # V1 decision D5, kept


def group_weights(groups: pd.Series) -> np.ndarray:
    n = groups.map(groups.value_counts())
    return (1.0 / n).to_numpy()


def weighted_median(x, w):
    o = np.argsort(x)
    x, w = np.asarray(x)[o], np.asarray(w)[o]
    c = np.cumsum(w) / w.sum()
    return float(x[np.searchsorted(c, 0.5)])


# ------------------------------------------------------------------ preprocessing
class Prep:
    """In-fold design-matrix builder."""

    def __init__(self, fs: dict):
        self.fs = fs

    def fit(self, df: pd.DataFrame, y: np.ndarray, groups: pd.Series):
        fs, self.num, self.cat = self.fs, [], []
        ng = groups.nunique()
        for c in fs["num"]:
            obs = df[c].notna()
            if groups[obs].nunique() / ng >= MIN_GROUP_COVERAGE:
                self.num.append(c)
        for c in fs["cat"]:
            obs = df[c].notna() & ~df[c].astype(str).isin(["UNMAPPED", "NOT_REPORTED", "nan"])
            if groups[obs].nunique() / ng >= MIN_GROUP_COVERAGE:
                self.cat.append(c)
        self.med = {c: float(np.nanmedian(df[c])) for c in self.num}
        xs = pd.DataFrame({c: df[c].fillna(self.med[c]) for c in self.num})
        self.mu = xs.mean() if len(self.num) else pd.Series(dtype=float)
        self.sd = xs.std().replace(0, 1) if len(self.num) else pd.Series(dtype=float)
        self.levels = {}
        for c in self.cat:
            v = self._clean(df[c])
            gcount = pd.Series(groups.values, index=v.index).groupby(v).nunique()
            keep = [lv for lv, n in gcount.items() if n >= RARE_LEVEL_MIN_GROUPS and lv != "MISSING"]
            self.levels[c] = sorted(keep)
        # empirical-Bayes (study-level) target encodings with inner out-of-fold values for training rows
        self.eb = {}
        for c in self.fs.get("eb_encode", []):
            if c in self.cat:
                self.eb[c] = self._eb_table(self._clean(df[c]), y, groups)
        self.columns = self._design(df, train=(y, groups)).columns.tolist()
        return self

    @staticmethod
    def _clean(s):
        return s.astype(object).where(s.notna() & ~s.astype(str).isin(["UNMAPPED", "NOT_REPORTED", "nan"]),
                                      "MISSING").astype(str)

    @staticmethod
    def _eb_table(v, y, groups):
        """Shrunken level means estimated on STUDY means (each study one vote)."""
        d = pd.DataFrame({"v": v.values, "y": y, "g": groups.values})
        sm = d.groupby(["v", "g"]).y.mean().reset_index()
        grand = sm.groupby("g").y.mean().mean()
        tau2 = max(sm.y.var() - 0.0, 1e-6)
        lev = sm.groupby("v").y.agg(["mean", "count", "var"])
        within = np.nanmean(lev["var"]) if lev["var"].notna().any() else tau2
        between = max(np.var(lev["mean"]) - within / max(lev["count"].mean(), 1), 1e-4)
        k = within / between
        shrunk = grand + (lev["mean"] - grand) * lev["count"] / (lev["count"] + k)
        return {"grand": grand, "map": shrunk.to_dict()}

    def _design(self, df, train=None):
        out = {}
        for c in self.num:
            x = df[c]
            out[c] = ((x.fillna(self.med[c]) - self.mu[c]) / self.sd[c]).to_numpy()
            if self.fs.get("missing_ind"):
                out[c + "__missing"] = x.isna().astype(float).to_numpy()
        for c in self.cat:
            v = self._clean(df[c])
            if c in self.eb:
                if train is not None:   # inner OOF encoding for training rows (no self-leakage)
                    y, groups = train
                    enc = np.empty(len(v))
                    ug = groups.unique()
                    rng = np.random.default_rng(0)
                    fold = dict(zip(ug, rng.permutation(len(ug)) % 5))
                    fid = groups.map(fold).to_numpy()
                    for f in range(5):
                        tr = fid != f
                        t = self._eb_table(v[tr], y[tr], groups[tr])
                        enc[~tr] = v[~tr].map(t["map"]).fillna(t["grand"]).to_numpy()
                    out[c + "__eb"] = enc
                else:
                    t = self.eb[c]
                    out[c + "__eb"] = v.map(t["map"]).fillna(t["grand"]).to_numpy()
                continue
            lv = self.levels[c]
            v2 = v.where(v.isin(lv) | (v == "MISSING"), "OTHER_RARE")
            for l in lv + ["OTHER_RARE", "MISSING"]:
                out[f"{c}={l}"] = (v2 == l).astype(float).to_numpy()
        X = pd.DataFrame(out, index=df.index)
        if hasattr(self, "columns"):
            X = X.reindex(columns=self.columns, fill_value=0.0)
        return X

    def transform(self, df):
        return self._design(df)

    def fit_transform(self, df, y, groups):
        self.fit(df, y, groups)
        return self._design(df, train=(y, groups))


# ------------------------------------------------------------------ models
class Baseline:
    def __init__(self, kind):
        self.kind = kind

    def fit(self, X, y, groups, w=None):
        y = np.asarray(y)
        if self.kind == "row_mean":
            self.c = float(np.mean(y))
        elif self.kind == "row_median":
            self.c = float(np.median(y))
        elif self.kind == "study_mean":
            self.c = float(pd.Series(y).groupby(groups.values).mean().mean())
        elif self.kind == "study_median":
            self.c = weighted_median(y, group_weights(groups))
        return self

    def predict(self, X):
        return np.full(len(X), self.c)


class RandomInterceptRidge:
    """Linear mixed model y = Xb + u_study + e, estimated by feasible GLS (Fuller-Battese quasi-demeaning)
    with a ridge penalty. Variance components from ANOVA moments of the ridge residuals. A new study is
    predicted with u = 0 (population-level prediction): its own random effect is never used."""

    def __init__(self, alpha=1.0, n_iter=3):
        self.alpha, self.n_iter = alpha, n_iter

    def fit(self, X, y, groups, w=None):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        g = np.asarray(groups)
        Xc = np.column_stack([np.ones(len(y)), X])
        theta = np.zeros(len(y))
        for _ in range(self.n_iter):
            Xs, ys = Xc.copy(), y.copy()
            for gg in np.unique(g):
                m = g == gg
                Xs[m] -= theta[m][:, None] * Xc[m].mean(0)
                ys[m] -= theta[m] * y[m].mean()
            pen = self.alpha * np.eye(Xc.shape[1])
            pen[0, 0] = 0
            self.beta = np.linalg.solve(Xs.T @ Xs + pen, Xs.T @ ys)
            r = y - Xc @ self.beta
            df = pd.DataFrame({"r": r, "g": g})
            sw = df.groupby("g").r.var(ddof=1).dropna()
            ni = df.groupby("g").size()
            s2 = float(np.average(sw, weights=ni[sw.index] - 1)) if len(sw) else float(np.var(r))
            gm = df.groupby("g").r.mean()
            t2 = max(float(gm.var(ddof=1) - np.mean(s2 / ni)), 1e-6)
            self.sigma2, self.tau2 = s2, t2
            nmap = pd.Series(g).map(ni).to_numpy()
            theta = 1 - np.sqrt(s2 / (s2 + nmap * t2))
        return self

    def predict(self, X):
        return np.column_stack([np.ones(len(X)), np.asarray(X, float)]) @ self.beta


def make_model(family: str, p: dict):
    if family == "ridge":
        return Ridge(alpha=p["alpha"])
    if family == "elasticnet":
        return ElasticNet(alpha=p["alpha"], l1_ratio=p["l1_ratio"], max_iter=20000)
    if family == "huber":
        return HuberRegressor(epsilon=p["epsilon"], alpha=p["alpha"], max_iter=2000)
    if family == "quantile_l1":
        return QuantileRegressor(quantile=0.5, alpha=p["alpha"], solver="highs")
    if family == "hgb":
        return HistGradientBoostingRegressor(loss="absolute_error", max_depth=p["max_depth"],
                                             learning_rate=p["lr"], max_iter=p["n_iter"],
                                             min_samples_leaf=p["min_leaf"], l2_regularization=p["l2"],
                                             random_state=0)
    if family == "catboost":
        from catboost import CatBoostRegressor
        return CatBoostRegressor(depth=p["depth"], learning_rate=p["lr"], iterations=p["iterations"],
                                 l2_leaf_reg=p["l2"], loss_function=p["loss"], random_seed=0, verbose=0,
                                 thread_count=1, allow_writing_files=False)
    if family == "mixed_ri":
        return RandomInterceptRidge(alpha=p["alpha"])
    raise ValueError(family)


SPACES = {
    "ridge": lambda t: {"alpha": t.suggest_float("alpha", 0.1, 300, log=True)},
    "elasticnet": lambda t: {"alpha": t.suggest_float("alpha", 1e-3, 1.0, log=True),
                             "l1_ratio": t.suggest_float("l1_ratio", 0.05, 0.95)},
    "huber": lambda t: {"epsilon": t.suggest_float("epsilon", 1.1, 2.5), "alpha": t.suggest_float("alpha", 1e-3, 30, log=True)},
    "quantile_l1": lambda t: {"alpha": t.suggest_float("alpha", 1e-4, 0.3, log=True)},
    "hgb": lambda t: {"max_depth": t.suggest_int("max_depth", 2, 3), "lr": t.suggest_float("lr", 0.02, 0.2, log=True),
                      "n_iter": t.suggest_int("n_iter", 30, 200), "min_leaf": t.suggest_int("min_leaf", 10, 40),
                      "l2": t.suggest_float("l2", 0.0, 5.0)},
    "catboost": lambda t: {"depth": t.suggest_int("depth", 2, 4), "lr": t.suggest_float("lr", 0.02, 0.2, log=True),
                           "iterations": t.suggest_int("iterations", 50, 300), "l2": t.suggest_float("l2", 1, 30, log=True),
                           "loss": t.suggest_categorical("loss", ["MAE", "RMSE", "Huber:delta=0.5"])},
    "mixed_ri": lambda t: {"alpha": t.suggest_float("alpha", 0.1, 300, log=True)},
}
N_TRIALS = {"ridge": 12, "elasticnet": 15, "huber": 12, "quantile_l1": 10, "hgb": 15, "catboost": 18, "mixed_ri": 10}
USES_WEIGHTS = {"ridge", "elasticnet", "huber", "hgb", "catboost"}


def fit_model(family, p, X, y, groups):
    m = make_model(family, p)
    w = group_weights(groups)
    if family == "mixed_ri":
        return m.fit(X, y, groups)
    if family == "quantile_l1":
        return m.fit(X, y, sample_weight=w * len(w) / w.sum())
    if family == "catboost":
        return m.fit(np.asarray(X), y, sample_weight=w * len(w) / w.sum())
    return m.fit(X, y, sample_weight=w * len(w) / w.sum())


def group_mae(y, pred, groups) -> float:
    e = pd.Series(np.abs(np.asarray(y) - np.asarray(pred))).groupby(np.asarray(groups)).mean()
    return float(e.mean())


class V2YieldModel:
    def __init__(self, family, fs, params, prep, model, intervals):
        self.family, self.fs, self.params, self.prep, self.model, self.intervals = family, fs, params, prep, model, intervals

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if self.family in ("row_mean", "row_median", "study_mean", "study_median"):
            return self.model.predict(df)
        X = self.prep.transform(df)
        return self.model.predict(np.asarray(X) if self.family == "catboost" else X)

    def predict_interval(self, df: pd.DataFrame, kind="single_contrast"):
        p = self.predict(df)
        q = self.intervals["single_contrast_q" if kind == "single_contrast" else "simultaneous_q"]
        return pd.DataFrame({"lnRR_pred": p, "lo90": p - q, "hi90": p + q, "pct_pred": 100 * (np.exp(p) - 1),
                             "pct_lo90": 100 * (np.exp(p - q) - 1), "pct_hi90": 100 * (np.exp(p + q) - 1)})
