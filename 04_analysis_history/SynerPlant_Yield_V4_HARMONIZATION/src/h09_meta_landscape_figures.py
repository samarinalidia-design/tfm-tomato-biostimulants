"""H9 - two results figures that the TFM structure (sections 4.2-4.6) needs and the V2 set does not have.
Fig14_meta_summary          4.4/4.5: pooled effects (CI and PI) for both endpoints, sensitivity sets and TEST,
                            heterogeneity decomposition, moderator tests, probability that a new study benefits
Fig15_evidence_landscape    4.2/4.3/4.6: stress x biostimulant evidence map (studies), descriptive effect map,
                            publication years (TRAIN vs TEST), cultivation systems, countries
Reads stored V2/V3.1 results only (nothing re-fitted). Same style as the V2 TFM figures."""
from __future__ import annotations
import json, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from scipy.stats import norm
from h00_common import V2, OUT

F = OUT / "figures_TFM_A4_V4"
F.mkdir(parents=True, exist_ok=True)
O2 = V2 / "outputs"
COL = {"yield": "#2a6f97", "biomass": "#2e8b57"}
INK, GREY = "#333333", "#c9ced6"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.5, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})
W = 7.0


def rj(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(fig, name, cap):
    fig.text(0.01, 0.004, textwrap.fill(cap, 140), fontsize=6.2, color=INK, ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"{name}.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


def lab(ax, s):
    ax.set_title(s, fontsize=8.5)


def pct(x):
    return 100 * (np.exp(x) - 1)


SET_LABEL = {"PRIMARY_EXPANDED": "TRAIN primary", "STRICT_SENSITIVITY": "strict outcome definition",
             "REPORTED_VARIANCE_ONLY": "reported variances only", "QUALITY_CORE": "quality core (low RoB)",
             "V1_EQUIVALENT": "V1-equivalent rows"}


# ------------------------------------------------------------------ Figure 14
def fig14():
    rows = []
    for ep, mp, tp in [("yield", O2 / "meta" / "meta_summary.json", O2 / "test_evaluation" / "TEST_meta.json"),
                       ("biomass", O2 / "biomass_v2" / "meta" / "meta_summary.json",
                        O2 / "biomass_v2" / "test_evaluation" / "TEST_meta.json")]:
        m = rj(mp)["overall"]
        for r in m:
            rows.append({"ep": ep, "label": SET_LABEL[r["set"]], "k": r["k_studies"], "mu": r["mu_lnRR"],
                         "lo": r["C_ci95_cluster_robust"][0], "hi": r["C_ci95_cluster_robust"][1],
                         "plo": r["D_pi95_new_study_mean"][0], "phi": r["D_pi95_new_study_mean"][1],
                         "main": r["set"] == "PRIMARY_EXPANDED", "test": False})
        t = rj(tp)
        for key, nm in [("TEST", "TEST 2024–2026"), ("TRAIN_plus_TEST", "TRAIN + TEST")]:
            r = t[key]
            rows.append({"ep": ep, "label": nm, "k": r["k_studies"], "mu": r["mu_lnRR"], "lo": r["ci95_CR2"][0],
                         "hi": r["ci95_CR2"][1], "plo": r["pi95_new_study_mean"][0], "phi": r["pi95_new_study_mean"][1],
                         "main": False, "test": True})
    R = pd.DataFrame(rows)
    fig = plt.figure(figsize=(W, 8.4))
    g1 = fig.add_gridspec(1, 1, left=0.27, right=0.80, top=0.96, bottom=0.55)
    g2 = fig.add_gridspec(1, 3, left=0.09, right=0.98, top=0.45, bottom=0.17, wspace=0.75, width_ratios=[1, 1.2, 1])

    # a  pooled effects
    ax = fig.add_subplot(g1[0, 0])
    y, yt, ylab = 0, [], []
    for ep in ["yield", "biomass"]:
        sub = R[R.ep == ep]
        ax.text(-0.98, y + 0.15, "Fruit yield" if ep == "yield" else "Dry biomass (secondary)", fontsize=7.2,
                weight="bold", color=COL[ep], va="bottom")
        y -= 0.9
        for _, r in sub.iterrows():
            c = COL[ep]
            ax.plot([r.plo, r.phi], [y, y], color=c, lw=1, alpha=0.45, solid_capstyle="round")
            ax.plot([r.lo, r.hi], [y, y], color=c, lw=3.2, solid_capstyle="round")
            ax.plot(r.mu, y, "D" if r.main else "o", ms=6 if r.main else 4.5, color=c if not r.test else "white",
                    mec=c, mew=1.3, zorder=3)
            ax.text(2.02, y, f"{pct(r.mu):+.0f} %  [{pct(r.lo):+.0f}, {pct(r.hi):+.0f}]", va="center",
                    fontsize=6.2, color=INK)
            yt.append(y)
            ylab.append(f"{r.label}  (k={r.k})")
            y -= 1
        y -= 0.6
    ax.axvline(0, color="#c0392b", lw=0.8)
    ax.set_yticks(yt, ylab, fontsize=6.4)
    ax.set_xlim(-1.0, 2.0)
    ax.set_ylim(y + 0.6, 1.0)
    ax.set_xlabel("pooled lnRR  —  thick: 95 % CI (CR2)   thin: 95 % prediction interval for a new study")
    ax.text(2.02, 0.75, "effect [95 % CI]", fontsize=6.3, weight="bold", color=INK)
    sec = ax.secondary_xaxis("top", functions=(pct, lambda p: np.log1p(np.asarray(p) / 100)))
    sec.set_xticks([-50, 0, 50, 100, 200, 400])
    sec.set_xlabel("% change vs stressed control", fontsize=6.6)
    sec.tick_params(labelsize=6.3)
    ax.set_title("a  Pooled effect of biostimulants under stress: clear mean, wide spread between studies",
                 fontsize=8.5, pad=26)

    # b  heterogeneity decomposition
    ax = fig.add_subplot(g2[0, 0])
    for i, ep in enumerate(["yield", "biomass"]):
        r = [x for x in rj(O2 / ("meta" if ep == "yield" else "biomass_v2/meta") / "meta_summary.json")["overall"]
             if x["set"] == "PRIMARY_EXPANDED"][0]
        tb, tw, I2 = r["tau2_between"], r["tau2_within"], r["I2_total_approx"]
        vs = (tb + tw) * (1 - I2) / I2
        parts = np.array([tb, tw, vs]) / (tb + tw + vs) * 100
        left = 0
        for p_, a_, nm in zip(parts, (1.0, 0.55, 0.2), ("between studies", "within study", "sampling error")):
            ax.bar(i, p_, bottom=left, color=COL[ep], alpha=a_, width=0.62, edgecolor="white", lw=1)
            if p_ > 6:
                ax.text(i, left + p_ / 2, f"{p_:.0f} %", ha="center", va="center", fontsize=6.3,
                        color="white" if a_ > 0.5 else INK)
            left += p_
        ax.text(i, 102, f"τ = {np.sqrt(tb):.2f}\nI² = {100 * I2:.0f} %", ha="center", va="bottom", fontsize=6)
    ax.set_xticks([0, 1], ["yield", "biomass"])
    ax.set_ylim(0, 122)
    ax.set_ylabel("share of total variance of lnRR (%)")
    ax.text(1.42, 22, "between\nstudies", fontsize=5.8, va="center")
    ax.text(1.42, 60, "within\nstudy", fontsize=5.8, va="center")
    ax.text(1.42, 91, "sampling\nerror", fontsize=5.8, va="center")
    ax.set_xlim(-0.5, 2.0)
    lab(ax, "b  Where heterogeneity sits")

    # c  moderator tests
    ax = fig.add_subplot(g2[0, 1])
    mods = ["stress_family", "biostimulant_class", "application_route", "cultivation_system"]
    names = ["stress family", "biostimulant class", "application route", "cultivation system"]
    for j, ep in enumerate(["yield", "biomass"]):
        mt = {m["moderator"]: m for m in rj(O2 / "v3_meta_extra" / ep / "meta_extra.json")["moderator_tests"]}
        for i, m in enumerate(mods):
            v = 100 * mt[m]["pseudo_R2_tau2"]
            yy = i + (-0.19 if j == 0 else 0.19)
            ax.barh(yy, max(v, 0.15), height=0.36, color=COL[ep], label=ep if i == 0 else None)
            ax.text(max(v, 0.15) + 0.3, yy, f"p = {mt[m]['p_HTZ']:.2f}", va="center", fontsize=5.9, color=INK)
    ax.set_yticks(range(4), names, fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlim(0, 10)
    ax.set_xlabel("between-study τ² explained (pseudo-R², %)")
    ax.legend(frameon=False, loc="lower right")
    lab(ax, "c  Moderators explain ≈ 0 %")

    # d  probability that a NEW study shows at least a given benefit
    ax = fig.add_subplot(g2[0, 2])
    thr = [0, 10, 25, 50]
    for j, ep in enumerate(["yield", "biomass"]):
        t = rj(O2 / ("test_evaluation" if ep == "yield" else "biomass_v2/test_evaluation") / "TEST_meta.json")["TRAIN"]
        sd = np.sqrt(t["tau2_between"] + t["se_CR2"] ** 2)
        pr = [100 * (1 - norm.cdf((np.log1p(g / 100) - t["mu_lnRR"]) / sd)) for g in thr]
        xs = np.arange(len(thr)) + (-0.19 if j == 0 else 0.19)
        ax.bar(xs, pr, width=0.36, color=COL[ep], label=ep)
        for x_, p_ in zip(xs, pr):
            ax.text(x_, p_ + 1.5, f"{p_:.0f}", ha="center", fontsize=5.9, color=INK)
    ax.set_xticks(range(len(thr)), [f">{g}" for g in thr])
    ax.set_xlabel("gain in a new study, % (mean)")
    ax.set_ylabel("expected share of new studies (%)")
    ax.set_ylim(0, 105)
    ax.legend(frameon=False, loc="upper right")
    lab(ax, "d  Chance of a gain")
    save(fig, "Fig14_meta_summary",
         "Figure 14. Summary of the meta-analyses (three-level REML, study / contrast, CR2 cluster-robust inference; "
         "contrasts with sampling variances). (a) Pooled lnRR with 95 % CI (thick) and 95 % prediction interval for the "
         "mean effect of a new study (thin) for the primary set, the pre-specified sensitivity sets and the independent "
         "2024-2026 TEST (open circles); TEST - TRAIN: yield +0.08 (p = 0.71), biomass +0.01 (p = 0.87). (b) Share of the "
         "total variance between studies, between contrasts of one study and from sampling error (typical sampling "
         "variance derived from I²). (c) Share of between-study τ² explained by each moderator, CR2-HTZ test p. "
         "(d) Expected share of new studies whose mean effect exceeds a benefit threshold, from the TRAIN model "
         "(normal predictive distribution, τ²_between + SE²).")


# ------------------------------------------------------------------ Figure 15
STRESS = {"DROUGHT": "drought", "SALINITY": "salinity", "BIOTIC": "biotic", "HEAT": "heat", "COLD": "cold",
          "TOXICITY_CONTAMINANT": "toxicity", "COMBINED_MULTI_STRESS": "combined", "NUTRIENT_LIMITATION": "nutrient"}
CLASS = {"PGPR_BACTERIA": "PGPR bacteria", "SEAWEED_ALGAL_EXTRACT": "seaweed extract", "AMF": "AMF",
         "COMBINATION_MULTI_CLASS": "multi-class mix", "INORGANIC_BENEFICIAL_ELEMENTS": "Si / Se / beneficial el.",
         "CHITOSAN_BIOPOLYMERS": "chitosan", "ORGANIC_AMENDMENT": "organic amendment",
         "PROTEIN_HYDROLYSATE_AMINO_ACIDS": "protein hydrolysate", "PHYTOHORMONE_PGR": "phytohormone",
         "HUMIC_FULVIC": "humic / fulvic", "MICROBIAL_CONSORTIUM_MIXED": "microbial consortium",
         "CELL_FREE_MICROBIAL_DERIVED": "cell-free microbial", "SMALL_MOLECULE_OSMOLYTE_ANTIOXIDANT": "osmolyte / antiox.",
         "MICROBIAL_UNSPECIFIED": "microbial, unspecified", "BENEFICIAL_FUNGI_NON_AMF": "other beneficial fungi",
         "BOTANICAL_EXTRACT": "botanical extract"}
SYSTEM = {"PROTECTED_POT": "greenhouse, pots", "OPEN_FIELD": "open field", "PROTECTED_IN_GROUND": "greenhouse, soil",
          "HYDROPONIC_SOILLESS": "soilless / hydroponic", "GROWTH_CHAMBER": "growth chamber",
          "PROTECTED_UNSPECIFIED": "protected, unspecified", "OUTDOOR_POT": "outdoor pots",
          "POT_FACILITY_NOT_STATED": "pots, facility n.s."}


def fig15():
    tr = pd.read_csv(O2 / "v31" / "yield" / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    te = pd.read_csv(O2 / "v31" / "yield" / "test_inputs" / "TEST_PRIMARY.csv", low_memory=False)
    tr["study_id"], te["study_id"] = tr.study_id.astype(str), te.study_id.astype(str)
    sm = tr.groupby(["study_id", "stress_family", "biostimulant_class"]).lnRR.mean().reset_index()
    cnt = sm.groupby(["stress_family", "biostimulant_class"]).study_id.nunique().unstack(fill_value=0)
    eff = sm.groupby(["stress_family", "biostimulant_class"]).lnRR.median().unstack()
    srow = cnt.sum(1).sort_values(ascending=False).index
    scol = cnt.sum(0).sort_values(ascending=False).index
    scol = [c for c in scol if c in CLASS][:12]
    cnt, eff = cnt.loc[srow, scol], eff.reindex(index=srow, columns=scol)

    fig = plt.figure(figsize=(W, 9.4))
    g1 = fig.add_gridspec(1, 2, left=0.11, right=0.89, top=0.95, bottom=0.60, wspace=0.08)
    g2 = fig.add_gridspec(1, 3, left=0.07, right=0.95, top=0.47, bottom=0.16, wspace=0.85, width_ratios=[1.15, 1, 1])
    blues = LinearSegmentedColormap.from_list("b", ["#f4f7fa", "#2a6f97", "#163e57"])

    ax = fig.add_subplot(g1[0, 0])
    m = cnt.to_numpy().astype(float)
    ax.imshow(np.where(m > 0, m, np.nan), cmap=blues, vmin=0, vmax=max(8, m.max()), aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if m[i, j] > 0:
                ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=6.2,
                        color="white" if m[i, j] >= 5 else INK)
    ax.set_xticks(range(len(scol)), [CLASS[c] for c in scol], rotation=60, ha="right", fontsize=6.2)
    ax.set_yticks(range(len(srow)), [f"{STRESS.get(s, s)} ({tr[tr.stress_family == s].study_id.nunique()})" for s in srow],
                  fontsize=6.5)
    ax.set_xticks(np.arange(-0.5, len(scol)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(srow)), minor=True)
    ax.grid(which="minor", color="white", lw=1.5)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    lab(ax, "a  Evidence map (independent studies)")

    ax = fig.add_subplot(g1[0, 1])
    e = eff.to_numpy()
    norm_ = TwoSlopeNorm(vcenter=0, vmin=-0.6, vmax=1.2)
    im = ax.imshow(np.where(m >= 2, e, np.nan), cmap="RdBu", norm=norm_, aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if m[i, j] >= 2:
                ax.text(j, i, f"{pct(e[i, j]):+.0f}", ha="center", va="center", fontsize=5.8,
                        color="white" if abs(e[i, j]) > 0.7 else INK, weight="bold" if m[i, j] >= 5 else None)
            elif m[i, j] == 1:
                ax.text(j, i, "·", ha="center", va="center", fontsize=8, color="#888")
    ax.set_xticks(range(len(scol)), [CLASS[c] for c in scol], rotation=60, ha="right", fontsize=6.2)
    ax.set_yticks([])
    ax.set_xticks(np.arange(-0.5, len(scol)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(srow)), minor=True)
    ax.grid(which="minor", color="white", lw=1.5)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cax = fig.add_axes([0.905, 0.70, 0.012, 0.22])
    cb = fig.colorbar(im, cax=cax)
    cb.set_ticks(np.log1p(np.array([-40, 0, 50, 100, 200]) / 100))
    cb.set_ticklabels(["−40 %", "0", "+50 %", "+100 %", "+200 %"])
    cb.ax.tick_params(labelsize=5.8)
    cb.outline.set_visible(False)
    lab(ax, "b  Median effect per cell, %")

    # c  publication year
    ax = fig.add_subplot(g2[0, 0])
    yr_tr = tr.drop_duplicates("study_id").publication_year.dropna().astype(int)
    yr_te = te.drop_duplicates("study_id")
    yr_te = (yr_te.publication_year if "publication_year" in yr_te else yr_te.year).dropna().astype(int)
    bins = np.arange(min(yr_tr.min(), 2005), 2027)
    ax.hist(yr_tr, bins=bins, color=COL["yield"], rwidth=0.85, label=f"TRAIN ≤ 2023 ({len(yr_tr)} studies)")
    ax.hist(yr_te, bins=bins, color="#e07a2f", rwidth=0.85, label=f"TEST 2024–2026 ({len(yr_te)})")
    ax.set_xlabel("publication year")
    ax.set_ylabel("independent studies")
    ax.set_ylim(0, 30)
    ax.legend(frameon=False, loc="upper left", fontsize=6)
    lab(ax, "c  Publication years")

    # d  cultivation system
    ax = fig.add_subplot(g2[0, 1])
    s1 = tr.drop_duplicates("study_id").cultivation_system.map(SYSTEM).value_counts()
    ax.barh(range(len(s1)), s1.to_numpy(), color=COL["yield"], height=0.62)
    for i, v in enumerate(s1.to_numpy()):
        ax.text(v + 0.4, i, str(v), va="center", fontsize=6.2, color=INK)
    ax.set_yticks(range(len(s1)), s1.index, fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlabel("independent studies (TRAIN)")
    lab(ax, "d  Cultivation system")

    # e  countries
    ax = fig.add_subplot(g2[0, 2])
    c1 = tr.drop_duplicates("study_id").f_country.fillna("not reported").str.split(r"[;,/]").str[0].str.strip()
    c1 = c1.value_counts()
    top = c1.drop("not reported", errors="ignore").head(9)
    other = int(c1.drop(top.index).drop("not reported", errors="ignore").sum())
    vals = list(top.items()) + [("other countries", other), ("not reported", int(c1.get("not reported", 0)))]
    for i, (n, v) in enumerate(vals):
        ax.barh(i, v, color=COL["yield"] if n not in ("other countries", "not reported") else GREY, height=0.62)
        ax.text(v + 0.3, i, str(v), va="center", fontsize=6.2, color=INK)
    ax.set_yticks(range(len(vals)), [v[0] for v in vals], fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlabel("independent studies (TRAIN)")
    lab(ax, "e  Country")
    save(fig, "Fig15_evidence_landscape",
         f"Figure 15. Evidence base for the fruit-yield target (V3.1 TRAIN: {len(tr)} SB-vs-S contrasts, "
         f"{tr.study_id.nunique()} independent studies). (a) Independent studies per stress family x biostimulant class "
         "(row totals in brackets); most cells are empty or hold one study. (b) Median of study-mean effects per cell "
         "(% yield change vs the stressed control), shown only for cells with >= 2 studies (bold: >= 5 studies; dot: one "
         "study). Descriptive only (unweighted medians): only 5 cells reach the 5 independent studies required for "
         "confirmatory pooling (drought x AMF, organic amendment, PGPR; salinity x PGPR, seaweed). (c) Publication years of TRAIN and of the independent "
         "TEST. (d) Cultivation systems. (e) Countries (first country listed).")


if __name__ == "__main__":
    fig14(); fig15()
    print("written to", F)
