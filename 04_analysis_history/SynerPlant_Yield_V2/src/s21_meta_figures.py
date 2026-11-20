"""A4 meta-analysis figures (stored R results only, outputs/v3_meta_extra/):
  Fig9_forest_yield      study-level forest plot + subgroup forest (CR2), yield
  Fig10_forest_biomass   the same for dry biomass
  Fig11_publication_bias funnel plots, Egger / PET-PEESE / trim-and-fill, moderator tests
"""
from __future__ import annotations
import json, subprocess, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from v2_common import OUT

F, ME = OUT / "figures_TFM_A4", OUT / "v3_meta_extra"
COL = {"yield": "#2a6f97", "biomass": "#2e8b57"}
plt.rcParams.update({"font.size": 7, "axes.titlesize": 8.5, "axes.labelsize": 7.2, "xtick.labelsize": 6.5,
                     "ytick.labelsize": 6, "axes.spines.top": False, "axes.spines.right": False,
                     "font.family": "DejaVu Sans", "axes.titleweight": "bold", "axes.titlelocation": "left"})
PRETTY = {"stress_family": "Stress", "biostimulant_class": "Biostimulant class", "application_route": "Route",
          "cultivation_system": "System"}


def rj(p):
    return json.loads(p.read_text(encoding="utf-8"))


def pct(x):
    return f"{100 * np.expm1(x):+.0f} %"


def save(fig, name, cap):
    fig.text(0.01, 0.004, textwrap.fill(cap, 140), fontsize=6.2, color="#333", ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"{name}.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


def forest_fig(t, name, title, height):
    j = rj(ME / t / "meta_extra.json")
    s = pd.read_csv(ME / t / "forest_studies.csv").sort_values("yi").reset_index(drop=True)
    sub = pd.read_csv(ME / t / "subgroups_CR2.csv")
    mu, ci = j["overall"]["mu"], j["overall"]["ci"]
    c = COL[t]
    fig = plt.figure(figsize=(7.0, height))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 0.95], wspace=0.82, left=0.155, right=0.985, top=0.95, bottom=0.11)
    ax = fig.add_subplot(gs[0, 0])
    y = np.arange(len(s))
    sz = 6 + 60 * s.weight_pct / s.weight_pct.max()
    ax.hlines(y, s.ci_lo.clip(-2.5, 4), s.ci_hi.clip(-2.5, 4), color="#8d99ae", lw=0.7)
    ax.scatter(s.yi, y, s=sz, marker="s", color=c, zorder=3, lw=0)
    yd = -1.6
    ax.fill([ci[0], mu, ci[1], mu], [yd, yd + 0.7, yd, yd - 0.7], color="k")
    ax.axvline(mu, color="k", lw=0.6, ls="--")
    ax.axvline(0, color="#c0392b", lw=0.6)
    lab = [f"{sid[:12]} ({n})" for sid, n in zip(s.study_id, s.n_contrasts)]
    ax.set_yticks(list(y) + [yd], lab + [f"pooled {pct(mu)}"], fontsize=5.2 if len(s) > 40 else 6)
    ax.set_ylim(yd - 1.5, len(s))
    ax.set_xlim(-1.5, 3.5 if t == "yield" else 2.0)
    ax.set_xlabel("lnRR (study aggregate, 95 % CI)")
    ax.set_title(f"A  Studies (k = {len(s)}; n contrasts)")

    ax = fig.add_subplot(gs[0, 1])
    rows, ylab, ypos, yy = [], [], [], 0
    for mo in ["stress_family", "biostimulant_class", "application_route", "cultivation_system"]:
        g = sub[sub.moderator == mo].sort_values("mu")
        if g.empty:
            continue
        test = next((m for m in j["moderator_tests"] if m["moderator"] == mo), None)
        ylab.append(f"{PRETTY[mo]}   (p = {test['p_HTZ']:.2f})" if test and test["p_HTZ"] is not None else PRETTY[mo])
        ypos.append(yy)
        yy -= 1
        for r in g.itertuples():
            ax.hlines(yy, r.ci_lo, r.ci_hi, color=c, lw=1.4)
            ax.plot(r.mu, yy, "o", color=c, ms=3.5)
            ylab.append(f"{str(r.level).replace('_', ' ').lower()[:26]}  (k={r.k_studies})")
            ypos.append(yy)
            yy -= 1
        yy -= 0.6
    ax.axvline(mu, color="k", lw=0.6, ls="--")
    ax.axvline(0, color="#c0392b", lw=0.6)
    ax.set_yticks(ypos, ylab)
    for tl, lb in zip(ax.get_yticklabels(), ylab):
        if "(p =" in lb or lb in PRETTY.values():
            tl.set_fontweight("bold")
            tl.set_fontsize(6.4)
    ax.set_xlabel("pooled lnRR per level (95 % CI, CR2)")
    ax.set_title("B  Subgroups (CR2-HTZ test)")
    save(fig, name, title)


def fig11():
    fig = plt.figure(figsize=(7.0, 6.6))
    gs = fig.add_gridspec(2, 2, hspace=0.5, wspace=0.35, left=0.17, right=0.98, top=0.95, bottom=0.17)
    for i, t in enumerate(["yield", "biomass"]):
        j = rj(ME / t / "meta_extra.json")
        f = pd.read_csv(ME / t / "funnel_studies.csv")
        sl = j["study_level"]
        ax = fig.add_subplot(gs[0, i])
        se = np.linspace(0, f.sei.max() * 1.05, 50)
        ax.plot(sl["mu"] - 1.96 * se, se, color="#999", lw=0.6, ls="--")
        ax.plot(sl["mu"] + 1.96 * se, se, color="#999", lw=0.6, ls="--")
        ax.axvline(sl["mu"], color="k", lw=0.7)
        o = f[~f.filled]
        ax.scatter(o.yi, o.sei, s=12, color=COL[t], edgecolor="w", lw=0.3, label=f"studies ({len(o)})")
        if f.filled.any():
            ax.scatter(f[f.filled].yi, f[f.filled].sei, s=12, facecolor="none", edgecolor="#c0392b", lw=0.7,
                       label=f"trim-and-fill imputed ({int(f.filled.sum())})")
        ax.invert_yaxis()
        ax.set_xlabel("study lnRR")
        ax.set_ylabel("standard error")
        ax.legend(frameon=False, fontsize=5.8, loc="lower right")
        ax.set_title(f"{'AB'[i]}  Funnel plot: {t}")
    ax = fig.add_subplot(gs[1, 0])
    labs, ests = [], []
    for t in ["yield", "biomass"]:
        j = rj(ME / t / "meta_extra.json")
        e, sl = j["egger_multilevel"], j["study_level"]
        for nm, m, c in [("REML 3-level", j["overall"]["mu"], j["overall"]["ci"]),
                         ("PET-PEESE", e["PET_PEESE_estimate"], e["PEESE_ci"] if e["PET_p"] < 0.05 else e["PET_ci"]),
                         ("trim-and-fill", sl["trimfill_mu"], sl["trimfill_ci"])]:
            labs.append(f"{t}: {nm}")
            ests.append((m, c, COL[t]))
    yy = np.arange(len(ests))[::-1]
    for y, (m, c, col) in zip(yy, ests):
        ax.hlines(y, c[0], c[1], color=col, lw=1.6)
        ax.plot(m, y, "D", color=col, ms=4)
        ax.text(c[1] + 0.03, y, pct(m), va="center", fontsize=6)
    ax.axvline(0, color="#c0392b", lw=0.6)
    ax.set_yticks(yy, labs, fontsize=6.3)
    ax.set_xlim(-0.05, 1.05)
    ax.set_xlabel("pooled lnRR (95 % CI)")
    ax.set_title("C  Bias-adjusted estimates")
    ax = fig.add_subplot(gs[1, 1])
    rows = []
    for t in ["yield", "biomass"]:
        j = rj(ME / t / "meta_extra.json")
        e, sl = j["egger_multilevel"], j["study_level"]
        rows.append([t, f"{e['slope_p_CR2']:.2f}", f"{sl['egger_p']:.2f}", f"{sl['begg_p']:.2f}", str(sl["trimfill_k0"]),
                     f"{sl['I2']:.0f} %"])
    ax.axis("off")
    tb = ax.table(cellText=rows, colLabels=["target", "Egger\n3-level p", "Egger\nstudy p", "Begg\np",
                                            "trim-fill\nk0", "I²"], loc="upper center", cellLoc="center")
    tb.auto_set_font_size(False)
    tb.set_fontsize(6.5)
    tb.scale(1, 2.4)
    ax.set_title("D  Small-study tests", pad=2)
    save(fig, "Fig11_publication_bias",
         "Figure 11. Small-study effects and publication bias (exploratory). A, B: funnel plots of study-aggregated "
         "lnRR (contrasts aggregated within study, rho = 0.5); dashed = 95 % pseudo-confidence region; red = studies "
         "imputed by trim-and-fill. C: the primary three-level estimate is compared with PET-PEESE (multilevel, CR2) and "
         "trim-and-fill; all bias-adjusted estimates remain clearly positive. D: no test reaches p < 0.05; I² is "
         "very high, which limits funnel-based diagnostics.")


def main():
    forest_fig("yield", "Fig9_forest_yield",
               "Figure 9. Yield meta-analysis (31 studies with sampling variances; three-level REML, CR2). A: each study's "
               "aggregated lnRR (marker size = model weight); diamond = pooled effect with its CR2 95 % CI. B: pooled "
               "effect per moderator level (levels with < 4 studies pooled as 'other'); no moderator explains the "
               "between-study variance (CR2-HTZ tests p >= 0.20).", 7.2)
    forest_fig("biomass", "Fig10_forest_biomass",
               "Figure 10. Dry-biomass meta-analysis (78 studies with sampling variances; three-level REML, CR2). A: "
               "study aggregates; B: moderator levels. No moderator is significant (CR2-HTZ p >= 0.13).", 9.6)
    fig11()
    rd = F / "README.md"
    t = rd.read_text(encoding="utf-8")
    add = ("| Fig9_forest_yield | yield meta-analysis: study forest plot and subgroups |\n"
           "| Fig10_forest_biomass | biomass meta-analysis: study forest plot and subgroups |\n"
           "| Fig11_publication_bias | funnel plots, Egger, PET-PEESE, trim-and-fill |\n")
    if "Fig9_forest" not in t:
        t = t.replace("These eight figures", "These eleven figures").replace("| Table1_V1_vs_V2.csv", add + "| Table1_V1_vs_V2.csv")
        rd.write_text(t, encoding="utf-8")
    print("Fig9-11 written")


if __name__ == "__main__":
    main()
