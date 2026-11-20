"""Compact A4 figure panels for the TFM: what V1 was, what V2 changed, what the result is.
Reads stored results only (no model is re-fitted). Output: outputs/figures_TFM_A4/ (PNG 300 dpi, PDF, SVG)."""
from __future__ import annotations
import json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from v2_common import OUT

F = OUT / "figures_TFM_A4"
F.mkdir(parents=True, exist_ok=True)
D, ML, UNC, META = OUT / "data", OUT / "ml", OUT / "uncertainty", OUT / "meta"
XR, XI, PR = OUT / "exploratory" / "stress_recovery", OUT / "exploratory" / "stress_intensity", OUT / "preregistration"
V1C, V2C, ACC, GREY, RED, GRN = "#9aa5b1", "#2a6f97", "#e07a2f", "#c9ced6", "#c0392b", "#2e8b57"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.5, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})
W = 7.0     # inches: A4 text width (~17.8 cm)
BASE = ["row_mean", "row_median", "study_mean", "study_median"]


def rj(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(fig, name, caption):
    import textwrap
    fig.text(0.01, 0.004, textwrap.fill(caption, 140), fontsize=6.2, color="#333", ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"{name}.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


def lab(ax, s):
    ax.set_title(s, fontsize=8.5)


# ------------------------------------------------------------------ Figure 1: data V1 -> V2
def fig1():
    rep = rj(D / "dataset_build_report.json")["sets"]
    v1, v2 = rep["V1_EQUIVALENT"], rep["PRIMARY_EXPANDED"]
    c = pd.read_csv(D / "v1_v2_comparison.csv", low_memory=False)
    p1 = pd.read_csv(D / "V1_EQUIVALENT.csv", low_memory=False)
    p2 = pd.read_csv(XI / "PRIMARY_EXPANDED_with_intensity.csv", low_memory=False)
    fig = plt.figure(figsize=(W, 6.9))
    gs = fig.add_gridspec(2, 2, hspace=0.55, wspace=0.42, left=0.08, right=0.98, top=0.95, bottom=0.15)

    ax = fig.add_subplot(gs[0, 0])
    tiers = ["STRICT", "ASSUMED_DEFINITION", "BROAD_DEFINITION", "RELATIVE_SHARED_UNIT"]
    cols = ["#1d4e6f", "#2a6f97", "#7fb3d5", "#c5dbe9"]
    for i, (name, s) in enumerate([("V1", v1), ("V2", v2)]):
        bottom = 0
        for t, col in zip(tiers, cols):
            n = s["by_tier"].get(t, 0)
            ax.bar(i, n, bottom=bottom, color=col, width=0.6, label=t.replace("_", " ").lower() if i == 1 else None)
            if n > 12:
                ax.text(i, bottom + n / 2, str(n), ha="center", va="center", fontsize=6.3, color="w" if col != "#c5dbe9" else "k")
            bottom += n
        ax.text(i, bottom + 6, f"{s['rows']} contrasts\n{s['studies']} studies", ha="center", va="bottom", fontsize=6.8)
    ax.set_xticks([0, 1], ["V1 training", "V2 primary"])
    ax.set_xlim(-0.5, 2.9)
    ax.set_ylim(0, 480)
    ax.set_ylabel("yield contrasts (SB vs S)")
    ax.legend(title="yield-definition tier", title_fontsize=6.3, loc="center right", frameon=False)
    lab(ax, "a  Training set size")

    ax = fig.add_subplot(gs[0, 1])
    rem = c[c.change == "REMOVED_FROM_PRIMARY"].status_reason.str.split(":").str[0].value_counts()
    add = c[c.change == "ADDED_TO_PRIMARY"].yield_tier.value_counts()
    items = [("added: broad yield definitions (marketable / single harvest)", add.get("BROAD_DEFINITION", 0), GRN),
             ("added: shared-unit relative yields (incl. 1 biotic study)", add.get("RELATIVE_SHARED_UNIT", 0), GRN),
             ("removed: duplicate arm pairs (same cell / timepoints)", -rem.get("DUPLICATE_ARM_PAIR_kept", 0), RED),
             ("removed: synthetic PGRs (NAA, thidiazuron)", -rem.get("V2-M003", 0), RED),
             ("removed: not a matched stress (study 199)", -rem.get("V2-X001", 0), RED),
             ("corrected: re-digitised means (lnRR unchanged)", (c.change == "MEANS_CHANGED_LNRR_SAME").sum(), ACC),
             ("corrected: biostimulant class assigned", (c.change == "CLASS_CHANGED").sum(), ACC)]
    items = [(t.replace(" (", "\n("), v, k) for t, v, k in items]
    y = np.arange(len(items))[::-1]
    ax.barh(y, [abs(v) for _, v, _ in items], color=[k for _, _, k in items], height=0.7)
    for yy, (t, v, _) in zip(y, items):
        sign = "+" if (v > 0 and t.startswith("added")) else ("−" if v < 0 else "")
        ax.text(abs(v) + 1.5, yy, f"{sign}{abs(v)}  {t}", va="center", fontsize=5.9, linespacing=0.95)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("contrasts")
    ax.set_xlim(0, 190)
    lab(ax, "b  What V2 changed (158 contrasts)")

    ax = fig.add_subplot(gs[1, 0])
    fam = ["SALINITY", "DROUGHT", "BIOTIC", "HEAT", "COLD", "NUTRIENT_LIMITATION", "COMBINED_MULTI_STRESS", "TOXICITY_CONTAMINANT"]
    a1 = p1.groupby("stress_family").study_id.nunique().reindex(fam).fillna(0)
    a2 = p2.groupby("stress_family").study_id.nunique().reindex(fam).fillna(0)
    x = np.arange(len(fam))
    ax.bar(x - 0.2, a1, 0.4, color=V1C, label="V1")
    ax.bar(x + 0.2, a2, 0.4, color=V2C, label="V2")
    for xx, v in zip(x, a2):
        ax.text(xx + 0.2, v + 0.4, int(v), ha="center", fontsize=6)
    ax.set_xticks(x, ["salinity", "drought", "biotic", "heat", "cold", "nutrient", "combined", "toxicity"], rotation=35, ha="right")
    ax.set_ylabel("independent studies")
    ax.legend(frameon=False)
    lab(ax, "c  Studies per stress type")

    ax = fig.add_subplot(gs[1, 1])
    n2 = p2.study_id.nunique()
    cov = lambda d, col: d[d[col].notna() & ~d[col].astype(str).isin(["nan", "UNSPECIFIED", "OTHER_OR_UNSPECIFIED"])].study_id.nunique()
    sal = p2[p2.stress_family == "SALINITY"]
    dro = p2[p2.stress_family == "DROUGHT"]
    rows = [("application count", cov(p2, "application_count") / n2, cov(p2, "application_count_v2") / n2),
            ("stress timing", 0, cov(p2, "stress_timing") / n2),
            ("substrate type", 0, cov(p2, "substrate_type") / n2),
            ("salinity intensity (of salinity studies)", cov(sal, "salinity_dSm_equiv") / sal.study_id.nunique(),
             cov(sal, "ece_equiv_dSm") / sal.study_id.nunique()),
            ("drought intensity (of drought studies)", cov(dro, "drought_supply_pct") / dro.study_id.nunique(),
             dro[dro.water_supply_rel_ET.notna() | dro.soil_water_rel_FC.notna()].study_id.nunique() / dro.study_id.nunique()),
            ("stress duration", cov(p2, "stress_duration_days") / n2, cov(p2, "stress_duration_days") / n2)]
    y = np.arange(len(rows))[::-1]
    ax.barh(y + 0.18, [r[1] * 100 for r in rows], 0.36, color=V1C, label="V1 / frozen V2 parser")
    ax.barh(y - 0.18, [r[2] * 100 for r in rows], 0.36, color=V2C, label="V2 + re-extraction (X2)")
    ax.axvline(20, color="k", lw=0.6, ls=":")
    ax.text(21, y.max() + 0.55, "20 % rule", fontsize=6)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=6.5)
    ax.set_xlabel("% of studies with the feature")
    ax.set_xlim(0, 105)
    ax.legend(frameon=False, loc="lower right")
    lab(ax, "d  Feature completeness")
    save(fig, "Fig1_data_V1_to_V2",
         "Figure 1. Yield training data before (V1) and after (V2) the source-verified audit. (a) contrasts by yield-definition "
         "tier; one contrast per SB/S arm pair in V2. (b) contrast-level changes, each backed by an original-source decision "
         "(audit/corrections_register.json). (c) independent studies per stress type. (d) share of studies reporting each "
         "pre-treatment feature. No error bars.")


# ------------------------------------------------------------------ Figure 2: model performance
def fig2():
    m = pd.read_csv(ML / "model_comparison.csv")
    sel = rj(ML / "selection_report.json")
    fig = plt.figure(figsize=(W, 6.6))
    gs = fig.add_gridspec(2, 2, hspace=0.55, wspace=0.38, left=0.09, right=0.98, top=0.95, bottom=0.17)

    ax = fig.add_subplot(gs[0, 0])
    v = m[m.dataset == "V1_EQUIVALENT"].set_index("candidate")
    best_ml = v[~v.family.isin(BASE)].sort_values("group_mae").iloc[0]
    bars = [("V1\nreported\n(other CV)", 0.4334, np.nan, GREY),
            ("study\nmean\n(≈V1)", v.loc["study_mean|B", "group_mae"], v.loc["study_mean|B", "group_mae_sd_seeds"], V1C),
            ("row\nmean", v.loc["row_mean|B", "group_mae"], v.loc["row_mean|B", "group_mae_sd_seeds"], V1C),
            ("row\nmedian", v.loc["row_median|B", "group_mae"], v.loc["row_median|B", "group_mae_sd_seeds"], V2C),
            ("best\nML", best_ml.group_mae, best_ml.group_mae_sd_seeds, ACC)]
    x = np.arange(len(bars))
    ax.bar(x, [b[1] for b in bars], yerr=[b[2] for b in bars], color=[b[3] for b in bars], capsize=2, ecolor="k")
    for xx, b in zip(x, bars):
        ax.text(xx, b[1] + 0.012, f"{b[1]:.3f}", ha="center", fontsize=6.3)
    ax.set_xticks(x, [b[0] for b in bars], fontsize=6.2)
    ax.set_ylim(0, 0.5)
    ax.set_ylabel("group-balanced MAE (lnRR)")
    lab(ax, "a  Same V1 data, same splits")

    ax = fig.add_subplot(gs[0, 1])
    p = m[m.dataset == "PRIMARY_EXPANDED"].copy()
    best = p.sort_values("group_mae").groupby("family").head(1).sort_values("group_mae")
    names = {"row_median": "row median", "study_median": "study median", "row_mean": "row mean",
             "study_mean": "study mean", "quantile_l1": "median regression", "catboost": "CatBoost", "hgb": "hist. GBM",
             "mixed_ri": "mixed model", "elasticnet": "ElasticNet", "ridge": "Ridge", "huber": "Huber"}
    ax.barh(np.arange(len(best))[::-1], best.group_mae, xerr=best.group_mae_sd_seeds, capsize=1.5,
            color=[GRN if f in BASE else V2C for f in best.family], ecolor="k")
    ax.set_yticks(np.arange(len(best))[::-1], [f"{names[f]} ({fs})" if f not in BASE else names[f]
                                              for f, fs in zip(best.family, best.fs)], fontsize=6.3)
    ax.axvline(best[best.family.isin(BASE)].group_mae.min(), color=GRN, ls="--", lw=0.7)
    ax.set_xlabel("group-balanced MAE (lnRR)")
    ax.set_xlim(0.3, max(0.5, best.group_mae.max() + 0.03))
    lab(ax, "b  V2 PRIMARY: best of each family")

    ax = fig.add_subplot(gs[1, 0])
    a = pd.read_csv(ML / "ablation_F0_F4.csv")
    a = a[a.dataset == "PRIMARY_EXPANDED"]
    fsn = ["F0", "F1", "F2", "F3", "F4"]
    for _, r in a.iterrows():
        ax.plot(fsn, r[fsn].astype(float), marker="o", ms=3, lw=1, label=names[r.family])
    ax.axhline(sel["selection"]["PRIMARY_EXPANDED"]["best_baseline_group_mae"], color=GRN, ls="--", lw=0.8, label="median (baseline)")
    ax.set_xticks(range(5), ["F0\nV1 feat.", "F1\n+fixes", "F2\n+stress/\ndose", "F3\n+yield\ndefinition", "F4\nhierarch."], fontsize=6)
    ax.set_ylabel("group-balanced MAE")
    ax.legend(frameon=False, ncol=2)
    lab(ax, "c  Adding features does not help")

    ax = fig.add_subplot(gs[1, 1])
    vd = sel["variance_decomposition"]["PRIMARY_EXPANDED"]
    tot, w = vd["total_var"], vd["pooled_within_study_var"]
    ax.bar(0, tot - w, color=V2C, width=0.5, label=f"between studies {100*(1-w/tot):.0f} %")
    ax.bar(0, w, bottom=tot - w, color="#7fb3d5", width=0.5, label=f"within studies {100*w/tot:.0f} %")
    ax.set_xlim(-0.6, 2.4)
    ax.set_xticks([0], ["variance of lnRR"])
    ax.set_ylabel("variance (lnRR²)")
    ax.legend(frameon=False, loc="upper right")
    floor = 0.8 * np.sqrt(w)
    ax2 = ax.inset_axes([0.5, 0.08, 0.45, 0.55])
    ax2.bar([0, 1], [sel["selection"]["PRIMARY_EXPANDED"]["best_baseline_group_mae"], floor], color=[GRN, GREY])
    ax2.set_xticks([0, 1], ["median", "floor*"], fontsize=6)
    ax2.set_title("MAE", fontsize=6.5, loc="center")
    ax2.tick_params(labelsize=6)
    lab(ax, "d  Where the error comes from")
    save(fig, "Fig2_model_performance",
         "Figure 2. Prediction from pre-treatment study descriptors, grouped 5-fold × 5-seed nested CV (studies held out). "
         "(a) on the exact V1 contrasts the median beats the mean used by V1 by 9 % (bootstrap CI includes 0). (b) no ML family beats "
         "the median on V2 data. (c) F0-F4 feature-set ablation. (d) variance decomposition; *floor = MAE left if every study mean "
         "were predicted perfectly (0.8·within-study SD). Error bars (a, b) = Type A: SD of the group-MAE across the 5 CV seeds.")


# ------------------------------------------------------------------ Figure 3: uncertainty
def fig3():
    dep = rj(UNC / "deployment_intervals.json")
    s = pd.read_csv(UNC / "interval_methods_comparison.csv")
    s = s[s.model.str.startswith("chosen")]
    pr = rj(PR / "PREREG_TEST_V2.json")["conditional_models"]["conformal_90"]
    meta = [x for x in rj(META / "meta_summary.json")["overall"] if "mu_lnRR" in x]
    fig = plt.figure(figsize=(W, 6.4))
    gs = fig.add_gridspec(2, 2, hspace=0.55, wspace=0.4, left=0.15, right=0.98, top=0.95, bottom=0.16)

    ax = fig.add_subplot(gs[0, 0])
    b = [("V1\nsplit-max\n(13 studies)", dep["v1_half_width"], GREY), ("V2\nall contrasts\nof a study", dep["simultaneous_q"], ACC),
         ("V2\none new\ncontrast", dep["single_contrast_q"], V2C), ("conditional C1\none contrast\n(pre-registered)", pr["C1"]["single_contrast_q"], GRN)]
    ax.bar(range(4), [x[1] for x in b], color=[x[2] for x in b])
    for i, x in enumerate(b):
        ax.text(i, x[1] + 0.05, f"±{x[1]:.2f}", ha="center", fontsize=6.5)
    ax.set_xticks(range(4), [x[0] for x in b], fontsize=6)
    ax.set_ylabel("90 % half-width (lnRR)")
    lab(ax, "a  Prediction interval width")

    ax = fig.add_subplot(gs[0, 1])
    nm = {"group_cvplus_contrast": "group CV+ (one contrast)", "subsample_one_per_study": "subsample 1/study",
          "group_cvplus_simultaneous": "group CV+ (whole study)", "v1_split_max_25pct": "V1 split-max",
          "adaptive_stress_family": "adaptive by stress"}
    for _, r in s.iterrows():
        cv = r.coverage_all_contrasts_of_study if "simultaneous" in r.target else r.coverage_contrast_study_balanced
        col = RED if cv < 0.9 else (GREY if r.method.startswith("v1") else V2C)
        ax.scatter(r.half_width_mean, cv * 100, s=22, color=col, zorder=3)
        off = {"group_cvplus_contrast": (4, -9), "subsample_one_per_study": (4, 3), "group_cvplus_simultaneous": (4, 4),
               "v1_split_max_25pct": (-62, -9), "adaptive_stress_family": (5, -2)}[r.method]
        ax.annotate(nm[r.method], (r.half_width_mean, cv * 100), fontsize=5.8, xytext=off, textcoords="offset points")
    ax.axhline(90, color=RED, ls="--", lw=0.7)
    ax.text(1.75, 90.15, "nominal 90 %", fontsize=6, color=RED)
    ax.set_xlabel("mean half-width (lnRR)")
    ax.set_ylabel("coverage on held-out studies (%)")
    ax.set_xlim(0.8, 2.25)
    lab(ax, "b  Coverage is verified, not assumed")

    ax = fig.add_subplot(gs[1, :])
    for i, x in enumerate(meta):
        ax.plot(x["D_pi95_new_study_mean"], [i, i], color=GREY, lw=7, solid_capstyle="butt",
                label="D: 95 % prediction interval of a new study's true mean" if i == 0 else None)
        ax.plot(x["C_ci95_cluster_robust"], [i, i], color=V2C, lw=3, label="C: 95 % CI of the pooled mean" if i == 0 else None)
        ax.plot(x["mu_lnRR"], i, "o", color="k", ms=3.5)
        ax.text(1.95, i, f"{x['pct_effect']:+.0f} %  (k={x['k_studies']})", va="center", fontsize=6.3)
    ax.axvline(0, color="k", lw=0.6)
    short = {"PRIMARY_EXPANDED": "V2 primary", "STRICT_SENSITIVITY": "strict only", "REPORTED_VARIANCE_ONLY": "reported variance",
             "QUALITY_CORE": "quality core", "V1_EQUIVALENT": "V1 contrasts"}
    ax.set_yticks(range(len(meta)), [short.get(x["set"], x["set"]) for x in meta])
    ax.set_xlim(-0.8, 2.5)
    ax.set_xlabel("pooled lnRR (three-level REML, studies with sampling variance)")
    ax.set_ylim(-0.6, len(meta) + 0.6)
    ax.legend(frameon=False, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0))
    lab(ax, "c  Meta-analysis: the mean is clear, individual studies vary widely")
    save(fig, "Fig3_uncertainty",
         "Figure 3. Four kinds of uncertainty kept apart. (a, b) Type B conformal prediction intervals (90 %) for a future "
         "experiment; coverage measured on studies never used for calibration (red = below nominal). (c) Type C (CI of the pooled "
         "mean) and Type D (meta-analytic prediction interval). Type A (CV error bars) is shown in Fig. 2. Python REML; "
         "confirmatory R metafor/CR2 pending.")


# ------------------------------------------------------------------ Figure 4: stress gradient
def fig4():
    q = pd.read_csv(XR / "quadruples.csv", low_memory=False)
    rep = rj(XR / "stress_recovery_report.json")
    cvr = pd.read_csv(XR / "predictive_cv.csv").set_index("model")
    cvi = pd.read_csv(XI / "predictive_cv_PRIMARY_all_69.csv").set_index("model")
    p2 = pd.read_csv(XI / "PRIMARY_EXPANDED_with_intensity.csv", low_memory=False)
    q2 = q.merge(p2[["contrast_id", "D_exp"]], on="contrast_id", how="left")
    fig = plt.figure(figsize=(W, 6.6))
    gs = fig.add_gridspec(2, 2, hspace=0.55, wspace=0.38, left=0.09, right=0.98, top=0.95, bottom=0.17)

    ax = fig.add_subplot(gs[0, 0])
    sm = q.groupby("study_id")[["D", "y"]].mean()
    ax.scatter(q.D, q.y, s=5, color=GREY, lw=0, alpha=.8)
    ax.scatter(sm.D, sm.y, s=16, color=V2C, edgecolor="w", lw=.3, zorder=3)
    b = rep["slopes_observed"]["D"]["between_studies"]
    ci = rep["slopes_ci95_study_bootstrap"]["D"]["between_studies"]
    nb = rep["slope_D_null_artifact_q025_q50_q975"]["between_studies"][1]
    xs = np.linspace(q.D.min(), 0.4, 20)
    ax.plot(xs, sm.y.mean() + b * (xs - sm.D.mean()), color=V2C, lw=1.2, label=f"observed slope {b:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]")
    ax.plot(xs, sm.y.mean() + nb * (xs - sm.D.mean()), color=RED, ls="--", lw=1, label=f"artefact only {nb:.2f}")
    ax.set_xlabel("realised stress damage D = ln(S/C)")
    ax.set_ylabel("biostimulant effect ln(SB/S)")
    ax.legend(frameon=False, loc="upper right")
    ax.text(0.02, 0.03, f"R² (study means) = {rep['between_study_variance']['R2_studymean_y_on_D']:.2f}", transform=ax.transAxes, fontsize=6.5)
    lab(ax, "a  Larger damage → larger benefit (42 studies)")

    ax = fig.add_subplot(gs[0, 1])
    rl = q.RL.dropna().clip(-1, 3)
    ax.hist(rl, bins=np.arange(-1, 3.01, 0.2), color=V2C, edgecolor="w")
    med = rep["descriptives"]["RL"]["median"]
    ax.axvline(med, color="k", lw=1)
    ax.axvline(1, color=RED, ls=":", lw=1)
    ax.text(med + 0.05, ax.get_ylim()[1] * 0.9, f"median {med:.2f}\n(≈⅔ of the loss recovered)", fontsize=6.3)
    ax.text(1.05, ax.get_ylim()[1] * 0.55, "full\nrecovery", fontsize=6, color=RED)
    ax.set_xlabel("recovered share of the stress loss  ln(SB/S) / −ln(S/C)")
    ax.set_ylabel("contrasts")
    lab(ax, "b  How much of the loss is recovered")

    ax = fig.add_subplot(gs[1, 0])
    g = q2.dropna(subset=["D_exp"]).groupby("study_id")[["D_exp", "D"]].mean()
    ax.scatter(g.D_exp, g.D, s=16, color=ACC, edgecolor="w", lw=.3)
    lim = [-3.2, 0.6]
    ax.plot(lim, lim, color="k", lw=0.6, ls=":")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    v = rj(XI / "stress_intensity_report.json")["validation"]["D_exp_vs_observed_D"]
    ax.text(0.03, 0.92, f"Spearman ρ = {v['spearman_with_observed_D']:.2f} (p = {v['p']:.2f}, {v['studies']} studies)",
            transform=ax.transAxes, fontsize=6.5)
    ax.set_xlabel("expected damage from printed stress dose\n(Maas–Hoffman / FAO-33)")
    ax.set_ylabel("realised damage ln(S/C)")
    lab(ax, "c  Printed stress dose does not predict damage")

    ax = fig.add_subplot(gs[1, 1])
    bars = [("median", cvi.loc["median", "mean"], V2C, "all 69 studies"),
            ("dose:\nexternal\nmodel", cvi.loc["external_damage", "mean"], ACC, "all 69"),
            ("dose:\nintensity\nscales", cvi.loc["intensity", "mean"], ACC, "all 69"),
            ("median", cvr.loc["median", "group_mae"], V2C, "42 factorial"),
            ("C1:\ndamage", cvr.loc["damage_linear", "group_mae"], GRN, "42 factorial"),
            ("C3: +\nln(B/C)", cvr.loc["damage+unstressed", "group_mae"], GRN, "42 factorial")]
    x = np.array([0, 1, 2, 3.6, 4.6, 5.6])
    ax.bar(x, [b[1] for b in bars], color=[b[2] for b in bars], width=0.8)
    for xx, b in zip(x, bars):
        ax.text(xx, b[1] / 2, f"{b[1]:.3f}", ha="center", va="center", fontsize=6, color="w", rotation=90)
    nulls = [np.nan, np.nan, np.nan, cvr.loc["median", "null_world_group_mae"], cvr.loc["damage_linear", "null_world_group_mae"],
             cvr.loc["damage+unstressed", "null_world_group_mae"]]
    ax.scatter(x, nulls, marker="_", s=160, color=RED, zorder=4)
    ax.set_xticks(x, [b[0] for b in bars], fontsize=5.8)
    ax.text(1, 0.455, "69 studies:\nknown before the experiment", ha="center", fontsize=6.2)
    ax.text(4.6, 0.455, "42 factorial studies:\nneeds the expected loss", ha="center", fontsize=6.2)
    ax.set_ylim(0, 0.53)
    ax.set_ylabel("group-balanced MAE (grouped 5×5 CV)")
    lab(ax, "d  What improves the prediction")
    save(fig, "Fig4_stress_gradient",
         "Figure 4. Exploratory analyses after the V2 freeze (pre-registered for TEST). (a) studies with stronger realised stress "
         "damage show larger biostimulant effects; red = slope produced by the shared-S artefact alone (null simulation). "
         "(b) the biostimulant recovers about two thirds of the log-loss. (c) printed stress doses do not predict the realised "
         "damage across studies. (d) prediction error: only knowledge of the expected loss improves on the median; red marks = the "
         "same CV in simulated worlds without a gradient (artefact only). No error bars.")


def summary_table():
    sel = rj(ML / "selection_report.json")
    dep = rj(UNC / "deployment_intervals.json")
    m = pd.read_csv(ML / "model_comparison.csv").set_index(["dataset", "candidate"])
    cvr = pd.read_csv(XR / "predictive_cv.csv").set_index("model")
    pr = rj(PR / "PREREG_TEST_V2.json")["conditional_models"]["conformal_90"]
    rows = [("Training contrasts", "371", "404", "one per arm pair; definitions coded, not filtered"),
            ("Independent studies", "52", "69", "+17"),
            ("Biotic studies with yield", "3", "4", "corpus contains no more"),
            ("Selected predictor", "mean (V1 rule)", "median", "no ML model passed the pre-specified rule"),
            ("Group-MAE on V1 contrasts (same splits)", f"{m.loc[('V1_EQUIVALENT','study_mean|B'),'group_mae']:.3f}",
             f"{m.loc[('V1_EQUIVALENT','row_median|B'),'group_mae']:.3f}", "−9 %; bootstrap CI includes 0"),
            ("Group-MAE on V2 data", "—", f"{sel['selection']['PRIMARY_EXPANDED']['best_baseline_group_mae']:.3f}", "different sample: not a model gain"),
            ("90 % interval, one new contrast", f"±{dep['v1_half_width']:.2f}", f"±{dep['single_contrast_q']:.2f}", "coverage verified 90.8 %"),
            ("90 % interval, whole new study", f"±{dep['v1_half_width']:.2f}", f"±{dep['simultaneous_q']:.2f}", "coverage verified 90.7 %"),
            ("Conditional model (known expected loss)", "—", f"MAE {cvr.loc['damage_linear','group_mae']:.3f}; ±{pr['C1']['single_contrast_q']:.2f}",
             "42 factorial studies; exploratory, pre-registered for TEST")]
    t = pd.DataFrame(rows, columns=["quantity", "V1", "V2", "note"])
    t.to_csv(F / "Table1_V1_vs_V2.csv", index=False, encoding="utf-8-sig")
    return t


def main():
    fig1(); fig2(); fig3(); fig4()
    t = summary_table()
    (F / "README.md").write_text(
        "# Current TFM figures (SynerPlant Yield V2)\n\n"
        "These four figures and Table 1 are the CURRENT figures for the thesis (fruit-yield target).\n\n"
        "| File | Content |\n|---|---|\n"
        "| Fig1_data_V1_to_V2 | data before/after: size, changes, stress types, feature completeness |\n"
        "| Fig2_model_performance | V1 vs V2 on the same data, all model families, ablation, error sources |\n"
        "| Fig3_uncertainty | prediction intervals before/after, verified coverage, meta-analysis CI vs PI |\n"
        "| Fig4_stress_gradient | stress-damage gradient, recovered share, printed dose vs damage, what improves prediction |\n"
        "| Table1_V1_vs_V2.csv | before -> after summary |\n\n"
        "Obsolete for the yield target: everything in `SynerPlant_Local_ML_Starter/.../outputs/yield*/figures_TFM` and "
        "`outputs/statistics/yield` (V1 data and V1 intervals). `outputs/figures/` here = earlier single-panel V2 drafts. "
        "Biomass (secondary target) figures in the Starter package are still the V1 analysis.\n", encoding="utf-8")
    return t


if __name__ == "__main__":
    print(main().to_string())
