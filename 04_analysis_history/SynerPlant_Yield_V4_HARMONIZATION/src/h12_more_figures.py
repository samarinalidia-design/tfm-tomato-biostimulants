"""H12 - remaining TFM results figures (same style, English, A4 width).
Fig16_PRISMA_flow             4.1   current two-branch flow (TRAIN_DEV <= 2023, external TEST 2024-2026)
Fig17_learning_curves         4.9   grouped learning curves (data-limited vs signal-limited), TFM 3.13
Fig18_applicability_domain    4.12  kNN applicability domain / OOD, TFM 3.14
Fig19_interactions            4.6/4.7  strict S x B and A x B interaction syntheses (exploratory)
Fig20_moderators              4.5/4.12  permutation importance and single-moderator meta-regressions
Counts for Fig16 come from the methods text (records, screening) and from the databases (studies, contrasts)."""
from __future__ import annotations
import json, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from h00_common import OUT, V2

F = OUT / "figures_TFM_A4_V4"
O2 = V2 / "outputs"
LA, IA = OUT / "learning_ad", OUT / "interactions"
BLUE, GREEN, ORANGE, GREY, INK, RED = "#2a6f97", "#2e8b57", "#e07a2f", "#c9ced6", "#333333", "#c0392b"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.5, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})
W = 7.0


def save(fig, name, cap):
    fig.text(0.01, 0.004, textwrap.fill(cap, 140), fontsize=6.2, color=INK, ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"{name}.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


def lab(ax, s):
    ax.set_title(s, fontsize=8.5)


def pct(x):
    return 100 * (np.exp(x) - 1)


# ------------------------------------------------------------------ Fig16 PRISMA
def box(ax, x, y, w, h, txt, fc="#eef3f7", ec=BLUE, bold=False, fs=6.3):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                fc=fc, ec=ec, lw=0.9))
    ax.text(x, y, txt, ha="center", va="center", fontsize=fs, color=INK, weight="bold" if bold else None,
            linespacing=1.25)


def arrow(ax, x0, y0, x1, y1):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", lw=0.8, color="#555",
                                                                  shrinkA=0, shrinkB=0, mutation_scale=7))


def fig16():
    fig = plt.figure(figsize=(W, 8.0))
    ax = fig.add_axes([0.01, 0.07, 0.98, 0.92])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for y, s in [(0.955, "Identification"), (0.74, "Screening"), (0.46, "Eligibility"), (0.16, "Included")]:
        ax.text(0.005, y, s, rotation=90, fontsize=7, weight="bold", color=BLUE, va="center")
    X, XE = 0.25, 0.585
    bw, bh = 0.36, 0.055
    # TRAIN_DEV branch
    box(ax, X, 0.955, bw, bh, "Records: Crossref, Europe PMC, OpenAlex\npass 1 19 910 + precision expansion 19 717 = 39 627")
    arrow(ax, X, 0.927, X, 0.885)
    box(ax, X, 0.857, bw, bh, "Unique records after DOI / title de-duplication\n12 141")
    box(ax, XE, 0.857, 0.27, bh, "Duplicates removed: 27 486", fc="#f6f6f6", ec="#999")
    arrow(ax, X + bw / 2, 0.857, XE - 0.135, 0.857)
    arrow(ax, X, 0.829, X, 0.79)
    box(ax, X, 0.762, bw, bh, "Records published ≤ 2023 screened\n(title / abstract)  7 331")
    box(ax, XE, 0.762, 0.27, bh, "≥ 2024 records set aside: 4 810\n(never used for development)", fc="#f6f6f6", ec="#999")
    arrow(ax, X + bw / 2, 0.762, XE - 0.135, 0.762)
    arrow(ax, X, 0.734, X, 0.695)
    box(ax, X, 0.667, bw, bh, "Advanced to full-text assessment  1 732")
    box(ax, XE, 0.667, 0.27, 0.075, "Excluded 5 599: wrong stress 2 365, wrong\ncrop 1 762, not a primary experiment 837,\nwrong / no biostimulant 635",
        fc="#f6f6f6", ec="#999")
    arrow(ax, X + bw / 2, 0.70, XE - 0.135, 0.70)
    arrow(ax, X, 0.639, X, 0.60)
    box(ax, X, 0.572, bw, bh, "Full-text candidates after second screening  1 192")
    arrow(ax, X, 0.544, X, 0.505)
    box(ax, X, 0.477, bw, bh, "Full text obtained and interpretable  766\n(+ 100 supplements)")
    box(ax, XE, 0.572, 0.27, bh, "Not retrieved / not interpretable: 426", fc="#f6f6f6", ec="#999")
    arrow(ax, X + bw / 2, 0.545, XE - 0.135, 0.565)
    arrow(ax, X, 0.449, X, 0.41)
    box(ax, X, 0.375, bw, 0.065, "Full-text classification\nA 399 · B 158 · C 29 · D 53 · E 42 · X 85")
    arrow(ax, X, 0.342, X, 0.303)
    box(ax, X, 0.275, bw, bh, "Class A (stress + biostimulant, quantitative)\nentered the relational database  399")
    box(ax, XE, 0.275, 0.27, bh, "Out of scope 17 · no yield / biomass\ntarget confirmed 104", fc="#f6f6f6", ec="#999")
    arrow(ax, X + bw / 2, 0.275, XE - 0.135, 0.275)
    arrow(ax, X - 0.09, 0.247, X - 0.09, 0.205)
    arrow(ax, X + 0.09, 0.247, X + 0.09, 0.205)
    box(ax, X - 0.095, 0.155, 0.17, 0.09, "Fruit yield TRAIN\n69 studies · 403 contrasts\n(31 studies with\nsampling variances)",
        fc="#dbe8f1", ec=BLUE, bold=False)
    box(ax, X + 0.095, 0.155, 0.17, 0.09, "Dry biomass TRAIN\n153 studies · 766 contrasts\n(78 studies with\nsampling variances)",
        fc="#dcefe3", ec=GREEN)
    # TEST branch
    XT = 0.875
    ax.text(XT, 0.985, "External TEST 2024–2026", ha="center", fontsize=7, weight="bold", color=ORANGE)
    box(ax, XT, 0.50, 0.2, 0.07, "New search after the\nmodel freeze; registry\n108 records", ec=ORANGE, fc="#fbefe5")
    arrow(ax, XT, 0.465, XT, 0.425)
    box(ax, XT, 0.395, 0.2, bh, "Full texts available 80\n(no full text 28)", ec=ORANGE, fc="#fbefe5")
    arrow(ax, XT, 0.367, XT, 0.328)
    box(ax, XT, 0.295, 0.2, 0.06, "Out of scope 6 · no target 16\n→ 58 studies closed", ec=ORANGE, fc="#fbefe5")
    arrow(ax, XT, 0.265, XT, 0.215)
    box(ax, XT, 0.155, 0.2, 0.11, "Yield TEST 12 studies ·\n36 contrasts (9 with var.)\nBiomass TEST 28 studies ·\n144 contrasts (21 with var.)",
        ec=ORANGE, fc="#fbefe5")
    ax.plot([0.752, 0.752], [0.08, 0.99], color="#bbb", lw=0.8, ls=":")
    save(fig, "Fig16_PRISMA_flow",
         "Figure 16. PRISMA-style flow of the current corpus. Left: development corpus (TRAIN_DEV, publications up to "
         "2023). Record and screening counts are the historical ledger (Methods 3.2-3.3); study and contrast counts are "
         "recomputed from the verified databases. One contrast per SB/S arm pair; 'with sampling variances' = studies "
         "entering the weighted meta-analyses. Right: the external TEST, searched and extracted only after the model "
         "freeze with the same protocol; each TEST was evaluated once. Records >= 2024 found by the historical search "
         "were never opened for development. Classes B-E are kept for other analyses and do not count for the yield model.")


# ------------------------------------------------------------------ Fig17 learning curves
MCOL = {"median (V2)": BLUE, "multilevel mean (V4)": ORANGE, "quantile L1, harmonized features": "#7a5195",
        "weighted forest, harmonized features": "#6c757d"}


def fig17():
    S = pd.read_csv(LA / "learning_curves_summary.csv")
    G = pd.read_csv(LA / "learning_curves_gain.csv")
    fig = plt.figure(figsize=(W, 4.4))
    gs = fig.add_gridspec(1, 2, left=0.08, right=0.98, top=0.90, bottom=0.30, wspace=0.32)
    ax = fig.add_subplot(gs[0, 0])
    for m, c in MCOL.items():
        s = S[S.model == m].sort_values("n_train_studies")
        se = s.sd / np.sqrt(s.n)
        ax.fill_between(s.n_train_studies, s.mae - 1.96 * se, s.mae + 1.96 * se, color=c, alpha=0.12, lw=0)
        ax.plot(s.n_train_studies, s.mae, "-o", color=c, ms=3.5, lw=1.8, label=m)
    ax.set_xlabel("independent training studies")
    ax.set_ylabel("group-MAE on held-out studies (lnRR)")
    ax.legend(frameon=False, loc="upper right")
    lab(ax, "a  Error vs amount of training evidence")
    ax = fig.add_subplot(gs[0, 1])
    nmap = S[S.model == "median (V2)"].set_index("frac").n_train_studies
    for m, c in MCOL.items():
        if m == "median (V2)":
            continue
        g = G[G.model == m].sort_values("frac")
        x = g.frac.map(nmap)
        ax.fill_between(x, g.gain_lo, g.gain_hi, color=c, alpha=0.12, lw=0)
        ax.plot(x, g.gain_mean, "-o", color=c, ms=3.5, lw=1.8, label=m)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xlabel("independent training studies")
    ax.set_ylabel("gain over the median (lnRR; >0 = better)")
    ax.legend(frameon=False, loc="lower right")
    lab(ax, "b  Gain over the median")
    save(fig, "Fig17_learning_curves",
         "Figure 17. Grouped learning curves on TRAIN (V3.1, 69 studies). Inside each of the 25 outer folds (5 study folds x "
         "5 seeds, identical to the model comparison) 20-100 % of the training studies were kept (3 random draws) and the "
         "models were scored on the untouched held-out studies. (a) Mean group-MAE with 95 % band. (b) Paired gain over "
         "the median (band = 10th-90th percentile over folds and draws). Feature models use the harmonized "
         "representation (composition flags, physical stress and dose measures) without tuning to a constant. A curve "
         "that stays at or below zero while the number of studies grows indicates limited signal in the reported "
         "pre-experiment features rather than a pure lack of data.")


# ------------------------------------------------------------------ Fig18 applicability domain
def fig18():
    A = pd.read_csv(LA / "ad_cv_rows.csv.gz")
    T = pd.read_csv(LA / "ad_test_rows.csv")
    s = json.loads((LA / "ad_summary.json").read_text(encoding="utf-8"))
    fig = plt.figure(figsize=(W, 6.6))
    gs = fig.add_gridspec(2, 2, left=0.09, right=0.96, top=0.95, bottom=0.21, hspace=0.6, wspace=0.55)
    # a distances
    ax = fig.add_subplot(gs[0, 0])
    rel = A.dist / A.thr
    bins = np.linspace(0, max(2.5, rel.max()), 40)
    ax.hist(rel, bins=bins, color=BLUE, alpha=0.85, density=True, label="TRAIN, held-out rows (CV)")
    ax.hist(T.dist / T.thr, bins=bins, color=ORANGE, alpha=0.75, density=True, label="TEST 2024–2026 rows")
    ax.axvline(1, color=RED, lw=1, ls="--")
    ax.text(1.04, ax.get_ylim()[1] * 0.45, "OOD threshold\n(95th pct. of TRAIN)", fontsize=5.9, color=RED, va="top")
    ax.set_xlabel("distance to 5 nearest TRAIN contrasts / threshold")
    ax.set_ylabel("density")
    ax.legend(frameon=False, loc="upper right", fontsize=6, bbox_to_anchor=(1.0, 1.0))
    lab(ax, f"a  Distance to the evidence ({100 * A.ood.mean():.1f} % of CV rows OOD)")
    # b error vs distance
    ax = fig.add_subplot(gs[0, 1])
    A["bin"] = pd.qcut(rel, 8, duplicates="drop")
    g = A.groupby("bin", observed=True).agg(x=("dist", lambda v: float(np.median(v / A.loc[v.index, "thr"]))),
                                            e=("err_v4", "mean"), se=("err_v4", lambda v: v.std() / np.sqrt(len(v))),
                                            c=("covered_v4", "mean"))
    ax.errorbar(g.x, g.e, yerr=1.96 * g.se, fmt="o-", color=ORANGE, ms=4, lw=1.5, capsize=2)
    ax.axvline(1, color=RED, lw=1, ls="--")
    ax.set_xlabel("relative distance (octile bins)")
    ax.set_ylabel("mean absolute error (lnRR)")
    lab(ax, "b  Error by distance bin")
    # c in vs out
    ax = fig.add_subplot(gs[1, 0])
    cv = s["cv"]
    labels = ["in domain", "out of domain"]
    mae = [cv["in_domain"]["group_mae_v4"], cv["out_of_domain"]["group_mae_v4"]]
    cov = [cv["in_domain"]["coverage_v4"], cv["out_of_domain"]["coverage_v4"]]
    x = np.arange(2)
    for j, (vals, nm) in enumerate([(mae, "group-MAE (lnRR)"), (cov, "coverage of 90 % interval")]):
        xs = x * 1.0 + j * 2.6
        ax.bar(xs, vals, width=0.7, color=[BLUE, RED], alpha=1 if j == 0 else 0.55)
        for xx, v in zip(xs, vals):
            ax.text(xx, v + 0.02, f"{v:.2f}", ha="center", fontsize=6.3)
        ax.text(xs.mean(), 1.08, nm, ha="center", fontsize=6.4, weight="bold")
    ax.plot([2.2, 4.0], [0.9, 0.9], color=INK, lw=0.7, ls=":")
    ax.text(4.05, 0.9, "0.90", fontsize=5.8, va="center")
    ax.set_xticks([0, 1, 2.6, 3.6], ["in", "out", "in", "out"])
    ax.set_ylim(0, 1.16)
    ax.set_xlim(-0.6, 4.4)
    ax.set_ylabel("value")
    lab(ax, f"c  In vs out of domain ({cv['in_domain']['n_rows']} / {cv['out_of_domain']['n_rows']} CV rows)")
    # d OOD share by stress family
    ax = fig.add_subplot(gs[1, 1])
    o = A.groupby("stress_family").agg(ood=("ood", "mean"), n=("group_id", "nunique")).sort_values("ood")
    o = o[o.n >= 2]
    ax.barh(range(len(o)), 100 * o.ood, color=[RED if v > 0.15 else BLUE for v in o.ood], height=0.6)
    for i, (v, n) in enumerate(zip(o.ood, o.n)):
        ax.text(100 * v + 0.8, i, f"{100 * v:.0f} %", va="center", fontsize=6.1)
    ax.set_yticks(range(len(o)), [f.lower().replace("_", " ") for f in o.index], fontsize=6.4)
    ax.set_xlim(0, 100 * o.ood.max() * 1.2 + 2)
    ax.set_xlabel("share of held-out rows flagged OOD (%)")
    lab(ax, "d  Where the evidence is thin")
    tt = s["test"]
    tin = tt.get("in_domain", {}).get("n_rows", 0)
    save(fig, "Fig18_applicability_domain",
         f"Figure 18. Applicability domain (Methods 3.14). Distance = mean Euclidean distance of a contrast to its 5 nearest "
         f"TRAIN contrasts from other studies in the harmonized, robust-scaled feature space, fitted inside each CV "
         f"training part; threshold = 95th percentile of leave-study-out TRAIN distances. (a) Distances of held-out CV "
         f"rows and of TEST rows (full-TRAIN fit): {tin} of {len(T)} TEST contrasts fall inside the domain. (b) Mean "
         f"absolute error of the V4 multilevel mean by distance octile (95 % CI): the relation is not monotone (the "
         f"densest region also holds heterogeneous studies), but the bin beyond the threshold is above the core of the "
         f"domain. (c) Out-of-domain rows have a higher "
         f"error and lower coverage of the frozen 90 % interval (half-width 0.806); an abstention or wider-interval "
         f"warning for OOD queries is therefore justified. (d) OOD share by stress family.")


# ------------------------------------------------------------------ Fig19 interactions
def fig19():
    P = pd.read_csv(IA / "interaction_pooled.csv").set_index("set")
    ax_ = pd.read_csv(IA / "axb_by_study.csv")
    sx = pd.read_csv(IA / "sxb_by_study.csv")
    axb = pd.read_csv(V2.parent / "SynerPlant_Yield_V4_HARMONIZATION" / "data" / "A_strict_AxB.csv")
    fig = plt.figure(figsize=(W, 8.4))
    g1 = fig.add_gridspec(1, 2, left=0.11, right=0.98, top=0.95, bottom=0.71, wspace=0.45, width_ratios=[1.25, 1])
    g2 = fig.add_gridspec(1, 1, left=0.42, right=0.97, top=0.60, bottom=0.14)
    # a  S x B distribution of study means
    ax = fig.add_subplot(g1[0, 0])
    for i, (ep, c, nm) in enumerate([("DRY_BIOMASS", GREEN, "dry biomass"), ("FRUIT_YIELD", BLUE, "fruit yield")]):
        v = sx[sx.endpoint == ep].effect.to_numpy()
        jit = np.random.default_rng(1).uniform(-0.18, 0.18, len(v))
        ax.scatter(v, i + jit, s=8, color=c, alpha=0.45, lw=0)
        r = P.loc["SxB_biomass" if ep == "DRY_BIOMASS" else "SxB_yield"]
        ax.plot([r.unw_lo, r.unw_hi], [i + 0.34, i + 0.34], color=c, lw=3, solid_capstyle="round")
        ax.plot(r.unw_mu, i + 0.34, "D", color=c, ms=5.5, mec="white")
        ax.text(1.55, i + 0.34, f"{pct(r.unw_mu):+.0f} % [{pct(r.unw_lo):+.0f}, {pct(r.unw_hi):+.0f}]\nk = {int(r.k_studies)} studies",
                fontsize=6, va="center")
    ax.axvline(0, color=RED, lw=0.8)
    ax.set_yticks([0, 1], ["dry biomass", "fruit yield"])
    ax.set_xlim(-1.6, 2.6)
    ax.set_xlabel("S × B interaction  ln(SB/S) − ln(B/C), study means")
    lab(ax, "a  Is the biostimulant effect larger under stress?")
    # b  A x B forest by study
    ax = fig.add_subplot(g2[0, 0])
    a = ax_.copy()
    a["se"] = np.sqrt(a.var_effect)
    a = a.sort_values(["endpoint", "effect"])
    first = axb.groupby("study_id").agg(c=("f_biostimulant_class", "first"), b=("bio_code", "first"))
    cls = {s: (r.c if isinstance(r.c, str) and r.c.strip() and r.c != "None" else f"components {r.b}").replace("AMF_COMPOST", "AMF + compost")
           for s, r in first.iterrows()}
    for i, (_, r) in enumerate(a.iterrows()):
        c = GREEN if r.endpoint == "DRY_BIOMASS" else BLUE
        if np.isfinite(r.se):
            ax.plot([r.effect - 1.96 * r.se, r.effect + 1.96 * r.se], [i, i], color=c, lw=1.4)
        ax.plot(r.effect, i, "s", color=c, ms=3 + min(r.n, 16) / 3, mec="white", mew=0.6)
    names = [textwrap.shorten(str(cls.get(s, s)), 58, placeholder="…") + f"  ({n})" for s, n in zip(a.study_id, a.n)]
    ax.set_yticks(range(len(a)), names, fontsize=5.8)
    y0 = len(a) + 0.8
    for j, (key, c, nm) in enumerate([("AxB_biomass", GREEN, "pooled, biomass"), ("AxB_all", INK, "pooled, all")]):
        r = P.loc[key]
        yy = y0 + j
        ax.plot([r.unw_lo, r.unw_hi], [yy, yy], color=c, lw=3, solid_capstyle="round")
        ax.plot(r.unw_mu, yy, "D", color=c, ms=6, mec="white")
        if np.isfinite(r.w_mu):
            ax.plot([r.w_lo, r.w_hi], [yy + 0.35, yy + 0.35], color=c, lw=1.2, alpha=0.6)
            ax.plot(r.w_mu, yy + 0.35, "o", color="white", mec=c, ms=4)
    ax.set_yticks(list(range(len(a))) + [y0, y0 + 1],
                  names + [f"pooled, biomass (k={int(P.loc['AxB_biomass'].k_studies)})", f"pooled, all (k={int(P.loc['AxB_all'].k_studies)})"],
                  fontsize=5.8)
    ax.axvline(0, color=RED, lw=0.8)
    ax.text(0.03, -1.4, "synergy →", fontsize=6, color=INK)
    ax.text(-0.03, -1.4, "← antagonism", fontsize=6, color=INK, ha="right")
    ax.set_ylim(-2, y0 + 1.8)
    ax.set_xlabel("A × B interaction  ln[(AB·C)/(A·B)] (study mean, 95 % CI)")
    ax.plot([], [], "s", color=GREEN, label="dry biomass")
    ax.plot([], [], "s", color=BLUE, label="fruit yield")
    ax.legend(frameon=False, loc="lower left", fontsize=6)
    lab(ax, "c  Combining two biostimulants: A × B by study (12 studies)")
    # b  A x B classification of contrasts
    ax = fig.add_subplot(g1[0, 1])
    z = axb[np.isfinite(axb.var_effect) & (axb.var_effect > 0)].copy()
    lo, hi = z.effect - 1.96 * np.sqrt(z.var_effect), z.effect + 1.96 * np.sqrt(z.var_effect)
    z["cls"] = np.where(lo > 0, "synergy", np.where(hi < 0, "antagonism", "additive (CI includes 0)"))
    cnt = z.groupby(["endpoint", "cls"]).size().unstack(fill_value=0)
    order = ["antagonism", "additive (CI includes 0)", "synergy"]
    cols = {"antagonism": RED, "additive (CI includes 0)": GREY, "synergy": GREEN}
    for i, ep in enumerate(cnt.index):
        left = 0
        for k in order:
            v = int(cnt.loc[ep].get(k, 0))
            if v:
                ax.barh(i, v, left=left, color=cols[k], height=0.55, edgecolor="white", label=k if i == 0 else None)
                ax.text(left + v / 2, i, str(v), ha="center", va="center", fontsize=6.2,
                        color="white" if k != "additive (CI includes 0)" else INK)
                left += v
    ax.set_yticks(range(len(cnt)), [e.lower().replace("_", " ") for e in cnt.index])
    ax.set_xlabel("A × B contrasts with a sampling variance")
    ax.set_ylim(-0.6, len(cnt) + 0.6)
    ax.legend(frameon=False, loc="upper right", fontsize=5.8, ncol=1)
    lab(ax, "b  A × B: synergy is rare")
    save(fig, "Fig19_interactions",
         "Figure 19. Interaction syntheses (exploratory, TRAIN_DEV). (a) Strict stress x biostimulant interaction "
         "ln(SB/S) - ln(B/C) per study (dots) and the mean of study means with a t-based 95 % CI (diamond): positive = the "
         "biostimulant helps more under stress than without it; yield rests on 6 studies only. (b) A x B contrasts with a "
         "sampling variance classified by their 95 % CI. (c) A x B interaction ln[(AB*C)/(A*B)] per study (square size = "
         "contrasts, label = declared combination); diamond = mean of study means (t 95 % CI), open circle = weighted "
         "three-level REML estimate with CR2 CI on contrasts with variances. Pre-specified rule: >= 5 independent studies allow exploratory synthesis only; A x B is not a "
         "confirmatory TFM objective.")


# ------------------------------------------------------------------ Fig20 moderators
NICE = {"comp_bacteria": "contains bacteria", "comp_amf": "contains AMF", "comp_fungi_other": "contains other fungi",
        "comp_seaweed": "contains seaweed", "comp_chitosan": "contains chitosan", "comp_silicon": "contains silicon",
        "comp_organic_amend": "organic amendment", "comp_living_microbe": "living microbe", "n_components": "number of components",
        "relative_stress_level": "relative stress level", "log_dose_within_family_v3": "log dose (within unit family)",
        "log_application_count": "log number of applications", "salinity_dSm_equiv_v3": "salinity, dS/m equivalent",
        "drought_supply_pct_v3": "water supply, % of control", "is_field": "open field", "stress_is_ambient": "ambient (not imposed) stress"}
PNICE = {"drought_supply_pct": "water supply %", "relative_stress_level": "relative stress level",
         "log_application_count": "log applications", "cultivation_system": "cultivation system",
         "harvest_window_v2": "harvest window", "application_timing": "application timing",
         "biostimulant_class": "biostimulant class", "application_route": "application route",
         "stress_family": "stress family", "stress_duration_days": "stress duration", "yield_scope_v2": "yield scope",
         "stress_timing": "stress timing", "substrate_type": "substrate", "salinity_dSm_equiv": "salinity dS/m",
         "relative_dose": "relative dose", "denominator_v2": "yield denominator", "genotype_type": "genotype type"}


def fig20():
    R = pd.read_csv(IA / "moderator_metaregression_yield.csv")
    I = pd.read_csv(O2 / "ml" / "permutation_importance.csv")
    fig = plt.figure(figsize=(W, 5.6))
    gs = fig.add_gridspec(1, 2, left=0.18, right=0.97, top=0.93, bottom=0.22, wspace=0.85, width_ratios=[0.8, 1.2])
    ax = fig.add_subplot(gs[0, 0])
    I = I.sort_values("importance_mean")
    I = I[I.share_folds_used > 0]
    y = np.arange(len(I))
    ax.barh(y, 1000 * I.importance_mean, xerr=1000 * I.importance_sd, color=BLUE, height=0.6,
            error_kw=dict(lw=0.7, capsize=1.5, ecolor="#777"))
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(y, [PNICE.get(f, f.replace("_", " ")) for f in I.feature], fontsize=6.2)
    ax.set_xlabel("increase in group-MAE when permuted\n(×10⁻³ lnRR; mean ± SD)")
    lab(ax, "a  Permutation importance ≈ 0")
    ax = fig.add_subplot(gs[0, 1])
    R = R.sort_values("beta")
    y = np.arange(len(R))
    for i, (_, r) in enumerate(R.iterrows()):
        c = BLUE if r.type.startswith("binary") else "#7a5195"
        ax.plot([r.lo, r.hi], [i, i], color=c, lw=1.8, solid_capstyle="round")
        ax.plot(r.beta, i, "o", color=c, ms=4.5, mec="white")
        ax.text(0.6, i, f"k={int(r.k_studies)}" + (f" ({int(r.k_with)})" if np.isfinite(r.k_with) else "") +
                f"  p={r.p_CR2:.2f}", fontsize=5.8, va="center")
    ax.axvline(0, color=RED, lw=0.8)
    ax.set_yticks(y, [NICE.get(m, m) for m in R.moderator], fontsize=6.3)
    ax.set_xlim(-0.6, 1.05)
    ax.set_xticks([-0.5, -0.25, 0, 0.25, 0.5])
    ax.set_xlabel("Δ lnRR (binary: present − absent;\nnumeric: per 1 SD), 95 % CI (CR2)")
    ax.plot([], [], "o", color=BLUE, label="binary")
    ax.plot([], [], "o", color="#7a5195", label="numeric (per SD)")
    ax.legend(frameon=False, loc="upper left", fontsize=6, bbox_to_anchor=(0, 1.0))
    lab(ax, "b  Single-moderator meta-regressions (yield)")
    save(fig, "Fig20_moderators",
         "Figure 20. What explains the yield effect? (a) Grouped held-out permutation importance of the best feature "
         "model in V2 (quantile L1, F4; 5 repeats x 25 folds): no feature increases the error when permuted. (b) One "
         "moderator at a time in the three-level meta-regression on the V3.1 TRAIN (403 contrasts, 69 studies; imputed "
         "sampling variances, shared-control covariance; CR2 small-sample tests); k = studies with the moderator observed "
         "(in brackets: studies where the component is present). No moderator is significant after Holm correction "
         "(smallest raw p: bacteria 0.05, living microbe 0.06).")


if __name__ == "__main__":
    import sys
    which = sys.argv[1:] or ["16", "17", "18", "19", "20"]
    for w in which:
        globals()[f"fig{w}"]()
    print("written", which)
