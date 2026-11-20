"""SynerPlant Yield V4 HARMONIZATION - shared paths, splits, metrics and selection rule.

Exploratory TRAIN-only project. Reads the V3.1 ML file (read-only snapshot in input/). The external 2024-2026
TEST is never read here. Splits, group-MAE, paired study bootstrap and the selection rule are copied unchanged from
SynerPlant_Yield_V2/src (s04_train.outer_splits, s05_evaluate.paired_bootstrap/wins, GAIN_MIN/WINS_MIN/N_BOOT) and
the conformal helpers from s06_uncertainty, so that every number is comparable to V2/V3.1.
"""
from __future__ import annotations
import hashlib, json, math, shutil, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd

V4 = Path(__file__).resolve().parents[1]
V2 = V4.parent / "SynerPlant_Yield_V2"
SRC_FILE = V2 / "outputs" / "v31" / "yield" / "data" / "PRIMARY_EXPANDED.csv"
INPUT = V4 / "input"
DATA = V4 / "data"
OUT = V4 / "outputs"
for p in (INPUT, DATA, OUT):
    p.mkdir(exist_ok=True)
SNAPSHOT = INPUT / "PRIMARY_EXPANDED_V31.csv"

SEEDS = [20261111, 20261112, 20261113, 20261114, 20261115]
K = 5
GAIN_MIN, WINS_MIN, N_BOOT = 0.02, 3, 4000
ALPHA = 0.10


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def snapshot_input() -> dict:
    """Copy the V3.1 ML file once; afterwards verify it is byte-identical to the source."""
    if not SNAPSHOT.exists():
        shutil.copy2(SRC_FILE, SNAPSHOT)
    rec = {"source": str(SRC_FILE), "source_sha256": sha256(SRC_FILE), "snapshot": str(SNAPSHOT),
           "snapshot_sha256": sha256(SNAPSHOT), "checked_at": now()}
    rec["identical"] = rec["source_sha256"] == rec["snapshot_sha256"]
    write_json(INPUT / "input_manifest.json", rec)
    if not rec["identical"]:
        raise RuntimeError("V3.1 source changed after the snapshot was taken - stop and re-decide")
    return rec


# ------------------------------------------------------------------ splits (identical to V2 s04_train)
def outer_splits(groups: pd.Series, seed: int, k: int = K):
    ug = np.array(sorted(groups.unique()))
    perm = np.random.default_rng(seed).permutation(ug)
    return [set(perm[i::k]) for i in range(k)]


def inner_splits(groups: pd.Series, seed: int, k: int = 3):
    ug = np.array(sorted(groups.unique()))
    perm = np.random.default_rng(seed).permutation(ug)
    return [set(perm[i::k]) for i in range(k)]


# ------------------------------------------------------------------ metrics (identical to V2 s05_evaluate)
def group_mae(y, p, g) -> float:
    return float(pd.Series(np.abs(np.asarray(y) - np.asarray(p))).groupby(np.asarray(g)).mean().mean())


def study_level_errors(p):
    return p.assign(ae=(p.lnRR - p.pred).abs()).groupby(["group_id", "seed"]).ae.mean().groupby("group_id").mean()


def paired_bootstrap(pa, pb, seed=1):
    ea, eb = study_level_errors(pa), study_level_errors(pb)
    idx = ea.index.intersection(eb.index)
    diff = (ea[idx] - eb[idx]).to_numpy()
    rng = np.random.default_rng(seed)
    bs = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(N_BOOT)])
    return float(diff.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), float((bs >= 0).mean())


def fold_wins(ma, mb):
    a = ma.set_index(["seed", "fold"]).group_mae
    b = mb.set_index(["seed", "fold"]).group_mae
    w = (a < b).groupby(level=0).sum()
    return int(w.median()), float((w >= WINS_MIN).mean())


# ------------------------------------------------------------------ conformal helpers (identical to V2 s06)
def q_order(scores, alpha=ALPHA):
    s = np.sort(np.asarray(scores))
    k = math.ceil((1 - alpha) * (len(s) + 1))
    return np.inf if k > len(s) else float(s[k - 1])


def q_group_weighted(r, g, alpha=ALPHA):
    df = pd.DataFrame({"r": np.abs(np.asarray(r)), "g": np.asarray(g)})
    df["w"] = 1 / df.g.map(df.g.value_counts())
    df = df.sort_values("r")
    Kc = df.g.nunique()
    lev = min((1 - alpha) * (1 + 1 / Kc), 1.0)
    c = df.w.cumsum() / Kc
    i = np.searchsorted(c.to_numpy(), lev - 1e-12)
    return np.inf if i >= len(df) else float(df.r.iloc[i])


def load_harmonized() -> pd.DataFrame:
    d = pd.read_csv(DATA / "TRAIN_HARMONIZED.csv", low_memory=False)
    d["group_id"] = d["study_id"].astype(str)
    return d.reset_index(drop=True)
