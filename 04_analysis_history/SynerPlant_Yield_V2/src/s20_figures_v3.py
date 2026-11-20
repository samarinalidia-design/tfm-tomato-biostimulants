"""A4 figures for the biomass V2 analysis and the V3 influence check (stored results only; nothing is fitted).
  Fig6_biomass_V1_to_V2   data, models, intervals, stress gradient (TRAIN)
  Fig7_biomass_TEST       one-time pre-registered biomass TEST
  Fig8_influence          leave-one-study-out influence (yield, biomass) and yield-component proxy
"""
from __future__ import annotations
import json, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from v2_common import OUT, V1_ML

F = OUT / "figures_TFM_A4"
B = OUT / "biomass_v2"
TRN, TSC, V1C, GREY, RED, GRN = "#2a6f97", "#e07a2f", "#9aa5b1", "#c9ced6", "#c0392b", "#2e8b57"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8.5, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.3, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})
rj = lambda p: json.loads(p.read_text(encoding="utf-8"))


def save(fig, name, cap):
    fig.text(0.01, 0.004, textwrap.fill(cap, 140), fontsize=6.2, color="#333", ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"{name}.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


def fig6():
    rep = rj(B / "data" / "dataset_build_report.json")["sets"]
    v1m = rj(V1_ML / "outputs" / "biomass" / "candidate_manifest.json")
    mc = pd.read_csv(B / "ml" / "model_comparison.csv")
    dep = rj(B / "uncertainty" / "deployment_intervals.json")
    ic = pd.read_csv(B / "uncertainty" / "interval_methods_comparison.csv")
    sr = rj(B / "stress_recovery" / "stress_recovery_report.json")
    q = pd.read_csv(B / "stress_recovery" / "quadruples.csv")
    cvt = pd.read_csv(B / "stress_recovery" / "predictive_cv.csv").set_index("model")
    fig = plt.figure(figsize=(7.0, 7.4))
    gs = fig.add_gridspec(2, 2, hspace=0.55, wspace=0.40, left=0.09, right=0.98, top=0.955, bottom=0.15)

    ax = fig.add_subplot(gs[0, 0])
    v1, v2 = rep["V1_EQUIVALENT"], rep["PRIMARY_EXPANDED"]
    tiers = [("STRICT", "#1d4e6f"), ("DRY_LATEST_TIME", "#2a6f97"), ("UNIT_UNSTATED", "#7fb3d5")]
    for i, s in enumerate([v1, v2]):
        bot = 0
        for t, col in tiers:
            n = s["by_tier"].get(t, 0)
            ax.bar(i, n, bottom=bot, color=col, width=0.6, label=t.replace("_", " ").lower() if i == 1 else None)
            bot += n
        ax.text(i, bot + 12, f"{s['rows']} contrasts\n{s['studies']} studies", ha="center", fontsize=6.6)
    ax.set_xticks([0, 1], ["V1", "V2"])
    ax.set_ylim(0, 1120)
    ax.set_ylabel("dry-biomass contrasts (SB vs S)")
    ax.legend(frameon=False, loc="upper left", fontsize=5.9)
    ax.set_title("A  Data: one contrast per arm pair, more studies")

    ax = fig.add_subplot(gs[0, 1])
    p = mc[mc.dataset == "PRIMARY_EXPANDED"].copy()
    p["fam"] = p.family
    best = p.sort_values("group_mae").groupby("fam").head(1).sort_values("group_mae", ascending=False)
    cols = [GRN if f in ("row_mean", "row_median", "study_mean", "study_median") else TRN for f in best.fam]
    ax.barh(range(len(best)), best.group_mae, color=cols, xerr=best.get("group_mae_sd_seeds"), error_kw={"lw": 0.6})
    ax.set_yticks(range(len(best)), [f"{f} ({s})" for f, s in zip(best.fam, best.fs)], fontsize=6.2)
    ax.axvline(v1m["selected_cv_group_MAE"], color=V1C, ls="--", lw=1, label=f"V1 selected (mean) {v1m['selected_cv_group_MAE']:.3f}")
    ax.set_xlim(0.2, 0.275)
    ax.set_xlabel("group-MAE (lnRR), grouped 5x5 CV")
    ax.legend(frameon=False, loc="upper right", fontsize=5.9)
    ax.set_title("B  Models: none qualifies over the mean")

    ax = fig.add_subplot(gs[1, 0])
    ch = ic[ic.model.str.startswith("chosen")]
    cs = ch[ch.method == "group_cvplus_contrast"].iloc[0]
    cm = ch[ch.method == "group_cvplus_simultaneous"].iloc[0]
    hw = [v1m["conformal_q_lnRR"], dep["single_contrast_q"], dep["simultaneous_q"]]
    cov = [np.nan, cs.coverage_contrast_study_balanced, cm.coverage_all_contrasts_of_study]
    lab = ["V1\n(36 calibration\nstudies)", f"V2 single\n({dep['calibration_studies']} studies)", "V2 all contrasts\nof a study"]
    ax.bar(range(3), hw, color=[V1C, TRN, "#1d4e6f"], width=0.6)
    for i, (h, c) in enumerate(zip(hw, cov)):
        ax.text(i, h + 0.03, f"±{h:.2f}" + ("" if np.isnan(c) else f"\ncoverage {c:.1%}"), ha="center", fontsize=6.5)
    ax.set_xticks(range(3), lab, fontsize=6.3)
    ax.set_ylim(0, 1.55)
    ax.set_ylabel("90 % half-width (lnRR)")
    ax.set_title("C  Prediction intervals: 2.3x narrower")

    ax = fig.add_subplot(gs[1, 1])
    s = q.groupby("group_id")[["D", "y"]].mean()
    ax.scatter(q.D, q.y, s=5, c=GREY, lw=0)
    ax.scatter(s.D, s.y, s=13, c=TRN, edgecolor="w", lw=0.3, label=f"study means ({len(s)})")
    b = sr["slopes_observed"]["D"]["between_studies"]
    ci = sr["slopes_ci95_study_bootstrap"]["D"]["between_studies"]
    nb = sr["slope_D_null_artifact_q025_q50_q975"]["between_studies"][1]
    xs = np.linspace(s.D.min(), s.D.max(), 10)
    ax.plot(xs, s.y.mean() + b * (xs - s.D.mean()), c=TRN, lw=1.2, label=f"slope {b:.2f} (CI {ci[0]:.2f} to {ci[1]:.2f})")
    ax.plot(xs, s.y.mean() + nb * (xs - s.D.mean()), c=RED, ls="--", lw=1, label=f"coupling artefact {nb:.2f}")
    ax.set_xlabel("stress damage D = ln(S/C)")
    ax.set_ylabel("ln(SB/S)")
    ax.set_ylim(-0.8, 1.9)
    g = cvt.gain_vs_median
    ax.text(0.98, 0.97, f"CV gain vs median:\nC1 damage {g['damage_linear']:.0%}\nC3 damage + unstressed {g['damage+unstressed']:.0%}",
            transform=ax.transAxes, ha="right", va="top", fontsize=6.2)
    ax.legend(frameon=False, loc="lower left", fontsize=5.8)
    ax.set_title("D  Stress gradient (109 factorial studies)")
    save(fig, "Fig6_biomass_V1_to_V2",
         "Figure 6. Secondary target: dry-biomass lnRR (shoot or whole plant). A: V2 keeps one contrast per SB/S arm pair "
         "and recovers studies whose terminal or unit-labelled values were missing. B: best configuration of every model "
         "family (green = constant baselines); the best descriptor model (ridge F2) is 2.7 % better but its bootstrap "
         "CI includes 0, so the mean is retained. C: 90 % intervals with coverage measured on held-out studies. "
         "D: factorial studies; the between-study slope on stress damage is far outside the shared-S coupling artefact.")


def fig7():
    rep, meta, reg = rj(B / "test_evaluation" / "TEST_REPORT.json"), rj(B / "test_evaluation" / "TEST_meta.json"), \
        rj(B / "preregistration" / "PREREG_TEST_BIOMASS.json")
    te = pd.read_csv(B / "test_inputs" / "TEST_PRIMARY.csv", low_memory=False)
    cvt = pd.read_csv(B / "stress_recovery" / "predictive_cv.csv").set_index("model")["group_mae"]
    h = reg["primary_hypothesis"]
    m0, q1, qs = h["frozen_point_lnRR"], h["intervals_90"]["single_contrast_q"], h["intervals_90"]["simultaneous_q"]
    P, C = rep["primary"], rep["conditional"]
    fig = plt.figure(figsize=(7.0, 7.7))
    gs = fig.add_gridspec(2, 2, hspace=0.52, wspace=0.40, left=0.09, right=0.98, top=0.955, bottom=0.175)

    ax = fig.add_subplot(gs[0, 0])
    order = te.groupby("study_id").lnRR.mean().sort_values().index
    pos = {s: i for i, s in enumerate(order)}
    ax.axhspan(m0 - qs, m0 + qs, color=GREY, alpha=0.45, lw=0, label=f"simultaneous 90 % (±{qs:.2f})")
    ax.axhspan(m0 - q1, m0 + q1, color=TRN, alpha=0.18, lw=0, label=f"single-contrast 90 % (±{q1:.2f})")
    ax.axhline(m0, color=TRN, lw=1.2, label=f"frozen mean {m0:.2f}")
    x = te.study_id.map(pos) + np.random.default_rng(1).uniform(-0.2, 0.2, len(te))
    out = (te.lnRR - m0).abs() > q1
    ax.scatter(x[~out], te.lnRR[~out], s=8, color=TSC, edgecolor="k", lw=0.25, zorder=3, label="TEST contrast")
    ax.scatter(x[out], te.lnRR[out], s=10, color=RED, marker="D", edgecolor="k", lw=0.25, zorder=3, label="outside single interval")
    ax.set_xticks([])
    ax.set_xlabel(f"TEST study, sorted by mean ({P['n_studies']} studies, {P['n_contrasts']} contrasts)")
    ax.set_ylabel("observed lnRR = ln(SB/S)")
    ax.legend(loc="upper left", frameon=False, fontsize=5.6)
    ax.set_ylim(min(-1.0, te.lnRR.min() - 0.1), max(2.2, te.lnRR.max() + 0.8))
    ax.set_title("A  Frozen V2 prediction on unseen studies")

    ax = fig.add_subplot(gs[0, 1])
    cvm, cvs = h["train_cv"]["group_mae_mean"], 0.907
    mm = [("group-MAE\n(lnRR)", cvm, P["group_mae"], h["accuracy_threshold"], "max"),
          ("coverage\nsingle", 0.907, P["coverage_single"], 0.85, "min"),
          ("coverage\nsimultaneous", 0.903, P["coverage_simultaneous"], 0.85, "min")]
    for i, (n, a, b, thr, kind) in enumerate(mm):
        ok = b <= thr if kind == "max" else b >= thr
        ax.bar(i - 0.18, a, 0.34, color=TRN, label="TRAIN (grouped CV)" if i == 0 else None)
        ax.bar(i + 0.18, b, 0.34, color=TSC, edgecolor=GRN if ok else RED, lw=1.4, label="TEST 2024-2026" if i == 0 else None)
        ax.plot([i - 0.4, i + 0.4], [thr, thr], color="k", ls="--", lw=0.8, label="pre-registered threshold" if i == 0 else None)
        ax.text(i - 0.18, a + 0.02, f"{a:.3f}", ha="center", fontsize=6)
        ax.text(i + 0.18, b + 0.02, f"{b:.3f}\n{'PASS' if ok else 'FAIL'}", ha="center", fontsize=6,
                color=GRN if ok else RED, fontweight="bold")
    ax.set_xticks(range(3), [x[0] for x in mm])
    ax.set_ylim(0, 1.25)
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=5.8)
    ax.set_title("B  Pre-registered primary criteria")

    ax = fig.add_subplot(gs[1, 0])
    rows = [("median", cvt["median"], C["median_group_mae"]), ("C1 damage", cvt["damage_linear"], C["C1"]["group_mae"]),
            ("C2 recovery\nshare", cvt["recovery_share"], C["C2"]["group_mae"]),
            ("C3 damage +\nunstressed", cvt["damage+unstressed"], C["C3"]["group_mae"])]
    for i, (n, a, b) in enumerate(rows):
        ax.bar(i - 0.18, a, 0.34, color=TRN, label="TRAIN CV (109 studies)" if i == 0 else None)
        ax.bar(i + 0.18, b, 0.34, color=TSC, label=f"TEST ({C['n_studies']} studies)" if i == 0 else None)
        ax.text(i - 0.18, a + 0.006, f"{a:.2f}", ha="center", fontsize=6)
        ax.text(i + 0.18, b + 0.006, f"{b:.2f}", ha="center", fontsize=6)
    ax.set_xticks(range(4), [r[0] for r in rows], fontsize=6.3)
    ax.set_ylabel("group-MAE (lnRR), lower = better")
    ax.set_ylim(0, 0.50)
    s, cr = C["between_slope"], C["criteria"]
    mark = lambda b: "✓" if b else "✗"
    ax.text(0.98, 0.98, f"C1: gain {C['C1']['gain_vs_median']:.0%} {mark(cr['1_gain'])}, beyond coupling {mark(cr['2_beyond_coupling'])}\n"
            f"slope {s['observed']:.2f} (CI {s['ci95'][0]:.2f} to {s['ci95'][1]:.2f}); null band to {s['null_band95'][0]:.2f} {mark(cr['3_slope'])}\n"
            f"verdict C1: {C['verdict'].replace('_', ' ')};  C3 secondary: {'PASS' if C['C3_secondary_pass'] else 'FAIL'} "
            f"(gain {C['C3']['gain_vs_median']:.0%})", transform=ax.transAxes, ha="right", va="top", fontsize=5.8, color="#333")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.83), frameon=False, fontsize=5.8, ncol=2)
    ax.set_title("C  Conditional models on TEST")

    ax = fig.add_subplot(gs[1, 1])
    lab = [("TRAIN", meta["TRAIN"], TRN), ("TEST", meta["TEST"], TSC), ("TRAIN + TEST", meta["TRAIN_plus_TEST"], "k")]
    for i, (n, r, col) in enumerate(lab):
        y = 3 - i
        ax.plot(r["pi95_new_study_mean"], [y, y], color=col, lw=0.8, alpha=0.45)
        ax.plot(r["ci95_CR2"], [y, y], color=col, lw=2.6)
        ax.plot(r["mu_lnRR"], y, "s", color=col, ms=6, mec="w")
        ax.text(r["mu_lnRR"], y + 0.24, f"+{100 * np.expm1(r['mu_lnRR']):.0f} %  (k = {r['k_studies']})", ha="center", fontsize=6.4, color=col)
    d = meta["TRAIN_vs_TEST"]
    ax.plot(d["ci95_CR2"], [0, 0], color="#555", lw=2.6)
    ax.plot(d["diff_TEST_minus_TRAIN"], 0, "D", color="#555", ms=5, mec="w")
    ax.text(d["diff_TEST_minus_TRAIN"], 0.24, f"Δ {d['diff_TEST_minus_TRAIN']:+.2f} (p = {d['p_CR2']:.2f})", ha="center", fontsize=6.4, color="#555")
    ax.axvline(0, color="k", lw=0.6)
    ax.set_yticks([3, 2, 1, 0], ["TRAIN", "TEST", "TRAIN + TEST", "TEST − TRAIN"])
    ax.set_xlim(-0.7, 1.2)
    ax.set_ylim(-0.5, 3.6)
    ax.set_xlabel("pooled lnRR (thick: 95 % CI CR2; thin: 95 % PI)")
    ax.set_title("D  Meta-analysis: effect replicates")
    save(fig, "Fig7_biomass_TEST",
         "Figure 7. Independent biomass TEST (2024-2026; one-time pre-registered evaluation, no re-fitting). A: TEST "
         "contrasts against the frozen V2 mean and its 90 % intervals. B: all three primary criteria pass. C: the damage "
         "model C1 beats the median by 18 % beyond the coupling artefact and the slope CI lies below 0, but the slope CI "
         "is not fully outside the null band, so the pre-registered C1 verdict is NOT CONFIRMED; the secondary C3 passes. "
         "D: three-level REML meta-analysis with CR2 CI; TEST and TRAIN effects agree.")


def fig8():
    ly = pd.read_csv(OUT / "v3_influence" / "yield_meta_loo.csv")
    lb = pd.read_csv(OUT / "v3_influence" / "biomass_meta_loo.csv")
    prim = pd.read_csv(OUT / "data" / "PRIMARY_EXPANDED.csv", low_memory=False)
    med = prim.lnRR.median()
    e = (prim.lnRR - med).abs().groupby(prim.study_id).mean().sort_values(ascending=False)
    pr = rj(OUT / "v3_yield" / "proxy_report.json")
    fig = plt.figure(figsize=(7.0, 3.9))
    gs = fig.add_gridspec(1, 3, wspace=0.45, left=0.08, right=0.98, top=0.9, bottom=0.3)
    for j, (lab, l, col) in enumerate([("A  Yield: leave one study out", ly, TRN), ("B  Biomass: leave one study out", lb, GRN)]):
        ax = fig.add_subplot(gs[0, j])
        f, r = l.iloc[0], l.iloc[1:].sort_values("mu").reset_index(drop=True)
        ax.fill_between(range(len(r)), r.lo, r.hi, color=col, alpha=0.18, lw=0, label="95 % CI (CR2)")
        ax.plot(range(len(r)), r.mu, ".", color=col, ms=3, label="pooled lnRR without study")
        ax.axhline(f.mu, color="k", lw=0.8, label=f"all studies {f.mu:.3f}")
        ax.axhline(0, color=RED, lw=0.6, ls=":")
        ax.set_xlabel(f"study left out (sorted; k = {int(f.k)})")
        ax.set_ylabel("pooled lnRR")
        ax.set_ylim(-0.05, max(0.85, r.hi.max() + 0.05))
        ax.text(0.02, 0.10, f"max shift {(r.mu - f.mu).abs().max():.3f}", transform=ax.transAxes, fontsize=6.3)
        ax.legend(frameon=False, fontsize=5.6, loc="upper left")
        ax.set_title(lab)
    ax = fig.add_subplot(gs[0, 2])
    vals = [e.mean(), e.iloc[1:].mean(), e.iloc[3:].mean()]
    ax.bar(range(3), vals, color=[TRN, "#7fb3d5", "#c5dbe9"])
    for i, v in enumerate(vals):
        ax.text(i, v + 0.008, f"{v:.3f}", ha="center", fontsize=6.4)
    ax.set_xticks(range(3), ["all 69\nstudies", "without\nlargest 1", "without\nlargest 3"], fontsize=6.3)
    ax.set_ylabel("group-MAE of the median (lnRR)")
    ax.set_ylim(0, 0.45)
    ax.set_title("C  Yield: extreme studies")
    save(fig, "Fig8_influence",
         "Figure 8. Robustness. A, B: removing any single study changes the pooled effect by at most "
         f"{(ly.mu.iloc[1:] - ly.mu.iloc[0]).abs().max():.3f} (yield) and {(lb.mu.iloc[1:] - lb.mu.iloc[0]).abs().max():.3f} "
         "(biomass) lnRR, and every CI excludes 0. C: three yield studies with very large effects (lnRR 1.5-3.3) carry a "
         "large share of the median's error; two match the source records, one figure-based value awaits a PDF check; none is removed. A yield-component proxy (fruit number x mean "
         f"fruit mass) would add {pr['proxy_studies']} studies ({pr['proxy_contrasts']} contrasts) as a sensitivity set only.")


if __name__ == "__main__":
    fig6(); fig7(); fig8()
    rd = F / "README.md"
    t = rd.read_text(encoding="utf-8")
    add = ("| Fig6_biomass_V1_to_V2 | biomass (secondary target): data, models, intervals, stress gradient |\n"
           "| Fig7_biomass_TEST | independent biomass TEST: prediction, criteria, conditional models, meta-analysis |\n"
           "| Fig8_influence | leave-one-study-out influence (yield, biomass) and extreme studies |\n")
    if "Fig6_biomass" not in t:
        t = t.replace("These five figures", "These eight figures").replace("| Table1_V1_vs_V2.csv", add + "| Table1_V1_vs_V2.csv")
        t = t.replace("Biomass (secondary target) figures in the Starter package are still the V1 analysis.",
                      "Biomass (secondary target): Fig6/Fig7 replace the V1 biomass figures of the Starter package.")
        rd.write_text(t, encoding="utf-8")
    print("Fig6-8 written")
