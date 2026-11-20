"""Figure 5 (A4): TRAIN (cross-validated) vs the independent 2024-2026 TEST (one-time, pre-registered evaluation).
Reads stored results only: outputs/test_evaluation/TEST_REPORT.json, TEST_meta.json, the TEST inputs and the frozen
pre-registration. Nothing is fitted or tuned here."""
from __future__ import annotations
import json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from v2_common import OUT

F, TST, PR = OUT / "figures_TFM_A4", OUT / "test_evaluation", OUT / "preregistration"
XR = OUT / "exploratory" / "stress_recovery"
TRN, TSC, GREY, RED, GRN = "#2a6f97", "#e07a2f", "#c9ced6", "#c0392b", "#2e8b57"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8.5, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.5, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})


def rj(p):
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    rep, meta, reg = rj(TST / "TEST_REPORT.json"), rj(TST / "TEST_meta.json"), rj(PR / "PREREG_TEST_V2.json")
    te = pd.read_csv(OUT / "test_inputs" / "TEST_PRIMARY.csv", low_memory=False)
    cv = pd.read_csv(XR / "predictive_cv.csv").set_index("model")["group_mae"]
    hp = reg["primary_hypothesis"]
    med, q1, qs = hp["frozen_median_lnRR"], hp["intervals_90"]["single_contrast_q"], hp["intervals_90"]["simultaneous_q"]
    P, C = rep["primary"], rep["conditional"]

    fig = plt.figure(figsize=(7.0, 7.7))
    gs = fig.add_gridspec(2, 2, hspace=0.52, wspace=0.40, left=0.09, right=0.98, top=0.955, bottom=0.175)

    # A: every TEST contrast against the frozen prediction and intervals
    ax = fig.add_subplot(gs[0, 0])
    order = te.groupby("study_id").lnRR.mean().sort_values().index
    pos = {s: i for i, s in enumerate(order)}
    ax.axhspan(med - qs, med + qs, color=GREY, alpha=0.45, lw=0, label=f"simultaneous 90 % (±{qs:.2f})")
    ax.axhspan(med - q1, med + q1, color=TRN, alpha=0.18, lw=0, label=f"single-contrast 90 % (±{q1:.2f})")
    ax.axhline(med, color=TRN, lw=1.2, label=f"frozen median {med:.2f}")
    x = te.study_id.map(pos) + np.random.default_rng(1).uniform(-0.15, 0.15, len(te))
    out = (te.lnRR - med).abs() > q1
    ax.scatter(x[~out], te.lnRR[~out], s=11, color=TSC, edgecolor="k", lw=0.3, zorder=3, label="TEST contrast")
    ax.scatter(x[out], te.lnRR[out], s=13, color=RED, marker="D", edgecolor="k", lw=0.3, zorder=3,
               label="outside single interval")
    ax.set_xticks(range(len(order)), [f"S{i + 1}" for i in range(len(order))])
    ax.set_xlabel(f"TEST study (sorted by mean; {P['n_studies']} studies, {P['n_contrasts']} contrasts)")
    ax.set_ylabel("observed lnRR = ln(SB/S)")
    ax.set_title("A  Frozen V2 prediction on unseen studies")
    ax.legend(loc="upper left", frameon=False, fontsize=5.8)
    ax.set_ylim(min(-1.2, te.lnRR.min() - 0.2), max(2.6, te.lnRR.max() + 0.9))

    # B: pre-registered primary criteria, TRAIN-CV vs TEST
    ax = fig.add_subplot(gs[0, 1])
    m = [("group-MAE\n(lnRR)", 0.361, P["group_mae"], 0.587, "max"),
         ("coverage\nsingle", 0.908, P["coverage_single"], 0.85, "min"),
         ("coverage\nsimultaneous", 0.907, P["coverage_simultaneous"], 0.85, "min")]
    for i, (n, a, b, thr, kind) in enumerate(m):
        ax.bar(i - 0.18, a, 0.34, color=TRN, label="TRAIN (grouped CV)" if i == 0 else None)
        ok = b <= thr if kind == "max" else b >= thr
        ax.bar(i + 0.18, b, 0.34, color=TSC, edgecolor=GRN if ok else RED, lw=1.4,
               label="TEST 2024-2026" if i == 0 else None)
        ax.plot([i - 0.4, i + 0.4], [thr, thr], color="k", ls="--", lw=0.8,
                label="pre-registered threshold" if i == 0 else None)
        ax.text(i - 0.18, a + 0.02, f"{a:.3f}", ha="center", fontsize=6)
        ax.text(i + 0.18, b + 0.02, f"{b:.3f}\n{'PASS' if ok else 'FAIL'}", ha="center", fontsize=6,
                color=GRN if ok else RED, fontweight="bold")
    ax.set_xticks(range(3), [x[0] for x in m])
    ax.set_ylim(0, 1.25)
    ax.set_title("B  Pre-registered primary criteria")
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=5.8)

    # C: conditional (stress-damage) models, TRAIN-CV vs TEST
    ax = fig.add_subplot(gs[1, 0])
    rows = [("median", cv["median"], C["median_group_mae"]), ("C1 damage", cv["damage_linear"], C["C1"]["group_mae"]),
            ("C2 recovery\nshare", cv["recovery_share"], C["C2"]["group_mae"]),
            ("C3 damage +\nunstressed", cv["damage+unstressed"], C["C3"]["group_mae"])]
    for i, (n, a, b) in enumerate(rows):
        ax.bar(i - 0.18, a, 0.34, color=TRN, label="TRAIN CV (42 studies)" if i == 0 else None)
        ax.bar(i + 0.18, b, 0.34, color=TSC, label=f"TEST ({C['n_studies']} studies)" if i == 0 else None)
        ax.text(i - 0.18, a + 0.008, f"{a:.2f}", ha="center", fontsize=6)
        ax.text(i + 0.18, b + 0.008, f"{b:.2f}", ha="center", fontsize=6)
    ax.axhline(C["median_group_mae"], color=TSC, ls=":", lw=0.9)
    ax.set_xticks(range(4), [r[0] for r in rows], fontsize=6.3)
    ax.set_ylabel("group-MAE (lnRR), lower = better")
    ax.set_ylim(0, 0.46)
    s = C["between_slope"]
    ax.text(0.98, 0.97, f"verdict: {C['verdict'].replace('_', ' ')}\nTEST slope on damage {s['observed']:+.2f}\n"
            f"(95 % CI {s['ci95'][0]:.1f} to {s['ci95'][1]:.1f}; TRAIN −0.59)", transform=ax.transAxes,
            ha="right", va="top", fontsize=6.2, color=RED)
    ax.set_title("C  Conditional models: TRAIN gain not reproduced")
    ax.legend(loc="upper left", frameon=False, fontsize=5.8)

    # D: confirmatory / secondary meta-analysis
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
    ax.set_xlim(-1.0, 2.2)
    ax.set_ylim(-0.5, 3.6)
    ax.set_xticks([-0.5, 0, 0.5, 1, 1.5, 2])
    ax.set_xlabel("pooled lnRR (thick: 95 % CI CR2; thin: 95 % PI)")
    ax.set_title("D  Meta-analysis: effect replicates")

    import textwrap
    cap = ("Figure 5. Independent TEST (studies published 2024-2026, extracted after the model freeze; one-time "
           "pre-registered evaluation, no re-fitting). A: TEST contrasts against the frozen V2 median and its 90 % "
           "intervals. B: pre-registered primary criteria (dashed: thresholds); accuracy and simultaneous coverage "
           "pass, single-contrast coverage (study-balanced) misses 0.85 by 0.003; all contrasts outside it come from the two studies with the largest effects. C: conditional stress-damage models improve on the "
           "median in TRAIN cross-validation but not on TEST (verdict NOT CONFIRMED). D: three-level REML meta-analysis "
           "with CR2 robust CI; the TEST effect is consistent with TRAIN (difference CI includes 0).")
    fig.text(0.01, 0.004, textwrap.fill(cap, 140), fontsize=6.2, color="#333", ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"Fig5_TRAIN_vs_TEST.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)

    rd = F / "README.md"
    t = rd.read_text(encoding="utf-8")
    row = "| Fig5_TRAIN_vs_TEST | independent 2024-2026 TEST: frozen prediction, primary criteria, conditional models, meta-analysis |\n"
    if "Fig5_TRAIN_vs_TEST" not in t:
        t = t.replace("These four figures", "These five figures").replace("| Table1_V1_vs_V2.csv", row + "| Table1_V1_vs_V2.csv")
        rd.write_text(t, encoding="utf-8")
    print("Fig5 written;", int(out.sum()), "TEST contrasts outside the single interval")


if __name__ == "__main__":
    main()
