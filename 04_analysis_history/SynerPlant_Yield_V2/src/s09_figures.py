"""Publication figures (PNG 300 dpi + SVG + PDF). Every caption states what the error bars are."""
from __future__ import annotations
import json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from v2_common import OUT

FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
DATA, ML, UNC, META = OUT / "data", OUT / "ml", OUT / "uncertainty", OUT / "meta"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 100,
                     "font.family": "DejaVu Sans"})
BLUE, GREY, ORANGE, RED, GREEN = "#2a6f97", "#8d99ae", "#e07a2f", "#c0392b", "#2e8b57"


def save(fig, name, caption):
    fig.text(0.01, 0.005, caption, fontsize=7, color="#444", ha="left", va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=300 if ext == "png" else None)
    plt.close(fig)


def fig_dataset():
    rep = json.loads((DATA / "dataset_build_report.json").read_text())["sets"]
    names = ["V1_EQUIVALENT", "PRIMARY_EXPANDED", "SENSITIVITY_STRICT_PLUS_ASSUMED", "QUALITY_CORE", "STRICT_SENSITIVITY"]
    lab = ["V1 train\n(371 ids)", "V2 PRIMARY\nEXPANDED", "V2 strict+\nassumed", "V2 QUALITY\nCORE", "V2 STRICT"]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    ax[0].bar(lab, [rep[n]["rows"] for n in names], color=[GREY] + [BLUE] * 4)
    ax[0].set_ylabel("contrasts (rows)")
    ax[1].bar(lab, [rep[n]["studies"] for n in names], color=[GREY] + [BLUE] * 4)
    ax[1].set_ylabel("independent studies")
    for a, key in zip(ax, ["rows", "studies"]):
        for i, n in enumerate(names):
            a.text(i, rep[n][key], str(rep[n][key]), ha="center", va="bottom", fontsize=8)
        a.tick_params(axis="x", labelsize=7)
    save(fig, "F1_dataset_size", "Fig. 1. Yield analysis sets, V1 vs V2. No error bars. Studies (not contrasts) are the "
         "independent units; V2 keeps one contrast per SB/S arm pair.")


def fig_lnrr():
    d = pd.read_csv(DATA / "PRIMARY_EXPANDED.csv", low_memory=False)
    sm = d.groupby(["study_id", "stress_family"]).lnRR.mean().reset_index()
    fams = sm.groupby("stress_family").size().sort_values(ascending=False).index.tolist()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    rng = np.random.default_rng(1)
    for i, f in enumerate(fams):
        r = d[d.stress_family == f].lnRR
        ax.scatter(i + rng.uniform(-0.25, 0.25, len(r)), r, s=6, color=GREY, alpha=0.5, lw=0)
        s = sm[sm.stress_family == f].lnRR
        ax.scatter(i + rng.uniform(-0.12, 0.12, len(s)), s, s=22, color=BLUE, edgecolor="white", lw=0.4, zorder=3)
        ax.text(i, ax.get_ylim()[1] if i == 0 else d.lnRR.max() + 0.15, f"k={len(s)}", ha="center", fontsize=7)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(range(len(fams)), [f.replace("_", "\n") for f in fams], fontsize=7)
    ax.set_ylabel("lnRR = ln(Yield SB / Yield S)")
    save(fig, "F2_lnRR_by_stress", "Fig. 2. Observed yield lnRR (grey: contrasts; blue: study means) by stress family, "
         "PRIMARY_EXPANDED. No error bars; k = independent studies.")


def fig_models():
    s = pd.read_csv(ML / "model_comparison.csv")
    p = s[(s.dataset == "PRIMARY_EXPANDED")].sort_values("group_mae").head(22)
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    col = [GREEN if f in ("row_mean", "row_median", "study_mean", "study_median") else BLUE for f in p.family]
    ax.barh(p.candidate, p.group_mae, xerr=p.group_mae_sd_seeds, color=col, ecolor="k", capsize=2)
    ax.invert_yaxis()
    ax.set_xlabel("group-balanced MAE (lnRR), mean of 5 seeds")
    ax.axvline(p[p.family.isin(["row_mean", "row_median", "study_mean", "study_median"])].group_mae.min(),
               color=GREEN, ls="--", lw=0.8)
    ax.tick_params(axis="y", labelsize=7)
    save(fig, "F3_model_comparison", "Fig. 3. Grouped 5x5 repeated nested CV on PRIMARY_EXPANDED (identical study splits). "
         "Error bars = Type A: SD of the group-MAE across the 5 CV seeds (not a prediction interval). Green = baselines.")


def fig_ablation():
    a = pd.read_csv(ML / "ablation_F0_F4.csv")
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.3), sharey=False)
    for i, ds in enumerate(["V1_EQUIVALENT", "PRIMARY_EXPANDED"]):
        x = a[a.dataset == ds]
        for _, r in x.iterrows():
            ax[i].plot(["F0", "F1", "F2", "F3", "F4"], r[["F0", "F1", "F2", "F3", "F4"]].astype(float), marker="o",
                       label=r.family)
        b = pd.read_csv(ML / "model_comparison.csv")
        bb = b[(b.dataset == ds) & b.family.isin(["row_mean", "row_median", "study_mean", "study_median"])].group_mae.min()
        ax[i].axhline(bb, color=GREEN, ls="--", lw=0.8, label="best baseline")
        ax[i].set_title(ds, fontsize=9)
        ax[i].set_ylabel("group-balanced MAE")
    ax[1].legend(fontsize=7)
    save(fig, "F4_ablation", "Fig. 4. Feature-set ablation F0 (V1 features) -> F4 (hierarchical encodings). Points = mean "
         "of 25 outer folds; no error bars.")


def fig_intervals():
    s = pd.read_csv(UNC / "interval_methods_comparison.csv")
    s = s[s.model.str.startswith("chosen")]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    for _, r in s.iterrows():
        cov = r.coverage_all_contrasts_of_study if "simultaneous" in r.target else r.coverage_contrast_study_balanced
        ax[0].scatter(r.half_width_mean, cov, s=40)
        ax[0].annotate(r.method.replace("_", " "), (r.half_width_mean, cov), fontsize=6, xytext=(3, 3),
                       textcoords="offset points")
    ax[0].axhline(0.9, color=RED, ls="--", lw=0.8)
    ax[0].set_xlabel("mean half-width (lnRR)")
    ax[0].set_ylabel("empirical coverage (held-out studies)")
    dep = json.loads((UNC / "deployment_intervals.json").read_text())
    labs = ["V1 split-max\n(13 studies)", "V2 simultaneous\n(all contrasts)", "V2 single\ncontrast"]
    vals = [dep["v1_half_width"], dep["simultaneous_q"], dep["single_contrast_q"]]
    ax[1].bar(labs, vals, color=[GREY, ORANGE, BLUE])
    for i, v in enumerate(vals):
        ax[1].text(i, v, f"+/-{v:.2f}", ha="center", va="bottom", fontsize=8)
    ax[1].set_ylabel("90% interval half-width (lnRR)")
    save(fig, "F5_prediction_intervals", "Fig. 5. Type B conformal prediction intervals (90%). Left: coverage measured on "
         "studies not used for calibration vs width. Right: deployed half-widths. Not confidence intervals of a mean.")


def fig_meta():
    m = json.loads((META / "meta_summary.json").read_text())["overall"]
    m = [x for x in m if "mu_lnRR" in x]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    for i, x in enumerate(m):
        ax.plot(x["D_pi95_new_study_mean"], [i, i], color=GREY, lw=6, alpha=0.5, solid_capstyle="butt")
        ax.plot(x["C_ci95_cluster_robust"], [i, i], color=BLUE, lw=2.5)
        ax.plot(x["mu_lnRR"], i, "o", color="k", ms=4)
    ax.set_yticks(range(len(m)), [f"{x['set']} (k={x['k_studies']})" for x in m], fontsize=7)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("pooled lnRR")
    save(fig, "F6_meta_CI_vs_PI", "Fig. 6. Three-level REML meta-analysis (studies with sampling variance). Blue = Type C "
         "95% CI of the mean (cluster-robust); grey = Type D 95% prediction interval of a new study's true mean effect.")


def fig_studies():
    e = pd.read_csv(ML / "per_study_errors.csv")
    e = e[e.model == "chosen"].sort_values("mae")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.bar(range(len(e)), e.mae, color=[RED if s == "BIOTIC" else BLUE for s in e.stress])
    ax.set_xlabel("studies (sorted)")
    ax.set_ylabel("MAE within study (lnRR)")
    save(fig, "F7_per_study_error", "Fig. 7. Out-of-fold absolute error per study for the selected model, averaged over 5 "
         "seeds (red = biotic). No error bars.")


def main():
    for f in (fig_dataset, fig_lnrr, fig_models, fig_ablation, fig_intervals, fig_meta, fig_studies):
        f()
    return sorted(p.name for p in FIG.glob("*.png"))


if __name__ == "__main__":
    print(main())
