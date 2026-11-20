"""H8 - A4 figures for the TFM (same style as SynerPlant_Yield_V2/src/s15_tfm_figures.py).
Fig12_V4_harmonization_TRAIN  - what each advice changed on TRAIN grouped CV (point and interval)
Fig13_V4_TEST_posthoc         - the one post-hoc TEST evaluation, A (multilevel mean) vs B (V2/V3.1 median)
Table2_V4.csv                 - before -> after numbers
Reads stored results only. V2 figures are NOT modified (they document the primary, pre-registered analysis)."""
from __future__ import annotations
import json, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from h00_common import V4, OUT, load_harmonized
from h04_intervals import evaluate

F = OUT / "figures_TFM_A4_V4"
F.mkdir(parents=True, exist_ok=True)
B_COL, A_COL, GREY, INK = "#2a6f97", "#e07a2f", "#c9ced6", "#333333"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.5, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})
W = 7.0
REF = "row_median|B|none|z"


def save(fig, name, caption):
    fig.text(0.01, 0.004, textwrap.fill(caption, 140), fontsize=6.2, color=INK, ha="left", va="bottom")
    for e in ("png", "pdf", "svg"):
        fig.savefig(F / f"{name}.{e}", dpi=300 if e == "png" else None)
    plt.close(fig)


def lab(ax, s):
    ax.set_title(s, fontsize=8.5)


LABELS = {  # candidate -> (label, advice)
    "quantile_l1|FH|mlre|robust": ("composition flags + physical dose/stress\n+ precision weights + robust scaling", "1,3,4"),
    "quantile_l1|F2v3|study|z": ("V3.1 physical stress/dose measures", "1"),
    "quantile_l1|FH|study|z": ("composition flags + physical measures", "1"),
    "R:ls|loc1_scale_stress": ("location-scale meta-analysis", "5"),
    "pp_hier|B|none|z": ("partial pooling stress x class", "2"),
    "R:rma_mv|intercept": ("multilevel mean (rma.mv, precision,\nshared control)", "2,3"),
    "mixed_ri|FH|none|robust": ("mixed model, random study intercept", "2"),
    "rf_meta|FH|mlre|z": ("MetaForest-type weighted forest", "3"),
    "R:rma_mv|stress+comp": ("multilevel meta-regression\nstress + composition", "1,2"),
}


def fig12():
    c = pd.concat([pd.read_csv(OUT / "cv" / "comparison.csv"), pd.read_csv(OUT / "rma" / "rma_comparison.csv")])
    c = c.drop_duplicates("candidate").set_index("candidate")
    ref = c.loc[REF]
    fig = plt.figure(figsize=(W, 9.0))
    g1 = fig.add_gridspec(1, 1, left=0.36, right=0.90, top=0.96, bottom=0.66)
    g2 = fig.add_gridspec(1, 2, left=0.20, right=0.98, top=0.58, bottom=0.36, wspace=0.75)
    g3 = fig.add_gridspec(1, 1, left=0.36, right=0.98, top=0.29, bottom=0.17)

    # a  group-MAE difference vs median, with paired-bootstrap 95 % CI
    ax = fig.add_subplot(g1[0, 0])
    keys = [k for k in LABELS if k in c.index]
    y = np.arange(len(keys))[::-1]
    for yi, k in zip(y, keys):
        r = c.loc[k]
        col = A_COL if k == "R:rma_mv|intercept" else GREY if r.diff_vs_ref > 0.02 else B_COL
        ax.plot([r.diff_ci_lo, r.diff_ci_hi], [yi, yi], color=col, lw=2, solid_capstyle="round")
        ax.plot(r.diff_vs_ref, yi, "o", ms=5, color=col, mec="white", mew=1)
        ax.text(0.105, yi, f"{r.group_mae:.3f}", va="center", ha="left", fontsize=6.3, color=INK)
    ax.axvline(0, color=INK, lw=0.8)
    ax.axvspan(-0.2, -0.02 * ref.group_mae, color="#2e8b57", alpha=0.08, lw=0)
    ax.text(-0.012, len(keys) - 0.35, "≥2 % better\n(rule)", fontsize=5.8, color="#2e8b57", ha="right", va="top")
    ax.set_yticks(y, [f"{LABELS[k][0]}  [{LABELS[k][1]}]" for k in keys], fontsize=6.2)
    ax.set_xlim(-0.03, 0.10)
    ax.set_ylim(-0.6, len(keys) - 0.3)
    ax.set_xlabel("group-MAE minus median (lnRR); 95 % CI")
    ax.text(0.105, len(keys) - 0.45, "MAE", fontsize=6.3, ha="left", weight="bold")
    lab(ax, f"a  Point prediction: no strategy beats the median ({ref.group_mae:.3f})")

    # b  study-balanced bias in CV
    ax = fig.add_subplot(g2[0, 0])
    bias = [("median (V2)", ref.bias_study_balanced, B_COL),
            ("composition+precision", c.loc["quantile_l1|FH|mlre|robust"].bias_study_balanced, GREY),
            ("location-scale", c.loc["R:ls|loc1_scale_stress"].bias_study_balanced, GREY),
            ("multilevel mean (V4)", c.loc["R:rma_mv|intercept"].bias_study_balanced, A_COL)]
    for i, (n, v, col) in enumerate(bias):
        ax.barh(i, v, color=col, height=0.6)
        ax.text(v - 0.005, i, f"{v:+.3f}", va="center", ha="right", fontsize=6.3, color=INK)
    ax.set_yticks(range(len(bias)), [b[0] for b in bias], fontsize=6.4)
    ax.invert_yaxis()
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlim(-0.24, 0.02)
    ax.set_xlabel("mean (prediction − observed), lnRR")
    lab(ax, "b  Bias (CV)")

    # c/d intervals
    iv = pd.read_csv(OUT / "intervals" / "interval_comparison.csv")
    pick = [("V2: median + group CV+", REF, "group_cvplus_contrast", B_COL),
            ("V4: multilevel mean + group CV+", "R:rma_mv|intercept", "group_cvplus_contrast", A_COL),
            ("location-scale conformal (advice 5)", REF, "ls_conformal", GREY)]
    ax = fig.add_subplot(g3[0, 0])
    for i, (n, m, meth, col) in enumerate(pick):
        r = iv[(iv.model == m) & (iv.method == meth)].iloc[0]
        ax.barh(i, r.half_width_mean, color=col, height=0.6)
        ax.text(r.half_width_mean + 0.02, i, f"±{r.half_width_mean:.2f}  |  coverage {r.coverage_study_balanced:.3f}"
                f"  |  score {r.interval_score_study_balanced:.2f}", va="center", fontsize=6.2, color=INK)
    ax.set_yticks(range(len(pick)), [p[0] for p in pick], fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.6)
    ax.set_xlabel("mean half-width of the 90 % interval, one new contrast (lnRR)")
    lab(ax, "d  Prediction interval (CV, nominal 90 %)")

    ax = fig.add_subplot(g2[0, 1])
    d = load_harmonized()
    cv2 = float(np.nanmedian(pd.concat([d.cv2_t, d.cv2_c])))
    d["vi_hat"] = cv2 / d.n_t.where(d.n_t > 0).fillna(d.n_t.median()) + cv2 / d.n_c.where(d.n_c > 0).fillna(d.n_c.median())
    feat = d[["contrast_id", "stress_family", "cultivation_system", "yield_scope_v2", "comp_living_microbe", "vi_hat", "log_n_arm"]]
    py = pd.read_csv(OUT / "cv" / "cv_predictions.csv.gz")
    rp = pd.read_csv(OUT / "rma" / "rma_predictions.csv")
    evs = {}
    for name, p, col in [("V2", py[py.candidate == REF], B_COL), ("V4", rp[rp.candidate == "rma_mv|intercept"], A_COL)]:
        _, ev = evaluate(p, feat, name)
        e = ev[ev.method == "group_cvplus_contrast"]
        evs[name] = (e.groupby("stress_family").covered.mean(), e.groupby("stress_family").group_id.nunique(), col)
    fams = evs["V2"][0][evs["V2"][1] >= 5].sort_values().index.tolist()
    yy = np.arange(len(fams))
    for (name, (cov, n, col)), off in zip(evs.items(), (-0.13, 0.13)):
        ax.plot(cov[fams].to_numpy(), yy + off, "o", ms=5, color=col, mec="white", mew=1, label=name)
        for i, f_ in enumerate(fams):
            ax.text(cov[f_] + (-0.015 if name == "V2" else 0.015), i + off, f"{cov[f_]:.2f}", fontsize=5.8,
                    color=INK, va="center", ha="right" if name == "V2" else "left")
    ax.axvline(0.90, color=INK, lw=0.8, ls="--")
    ax.text(0.902, -0.6, "nominal 0.90", fontsize=5.8, color=INK)
    ax.set_yticks(yy, [f"{f_.lower().replace('_', ' ')} ({evs['V2'][1][f_]})" for f_ in fams], fontsize=6.3)
    ax.set_xlim(0.55, 1.02)
    ax.set_ylim(-0.75, len(fams) - 0.2)
    ax.set_xlabel("coverage of the one-contrast interval")
    ax.legend(frameon=False, loc="upper left", ncol=2, borderaxespad=0)
    lab(ax, "c  Coverage by stress family")
    save(fig, "Fig12_V4_harmonization_TRAIN",
         "Figure 12. V4 harmonization experiment on TRAIN (V3.1 file, 403 contrasts, 69 studies; grouped CV 5 folds x 5 "
         "seeds, identical to V2). (a) Group-MAE difference to the median with paired study-bootstrap 95 % CI; advice "
         "numbers in brackets; no candidate passed the pre-specified rule. (b) Study-balanced bias. (c) Coverage of the "
         "one-contrast interval by stress family (families with >= 5 studies). (d) 90 % interval for one new contrast: "
         "half-width, coverage and interval score (lower is better). The multilevel random-effects mean (rma.mv study/contrast, precision weights, "
         "shared-control covariance; new study predicted without its own effect) gives narrower intervals and less "
         "bias at a 5.6 % higher MAE (CI includes 0). Exploratory: the interval rule was set after the first run.")


def fig13():
    rep = json.loads((OUT / "test_posthoc" / "TEST_POSTHOC_REPORT.json").read_text(encoding="utf-8"))
    reg = json.loads((V4 / "prereg" / "PREREG_V4_TEST_POSTHOC.json").read_text(encoding="utf-8"))
    t = pd.read_csv(reg["test_file"]["path"], low_memory=False)
    t = t[np.isfinite(t.lnRR)]
    A, B = reg["model_A_new"], reg["model_B_comparator"]
    a, b = rep["A_new_multilevel_mean"], rep["B_V31_median"]
    fig = plt.figure(figsize=(W, 7.6))
    ga = fig.add_gridspec(1, 1, left=0.09, right=0.98, top=0.95, bottom=0.60)
    gb = fig.add_gridspec(1, 2, left=0.21, right=0.99, top=0.48, bottom=0.17, wspace=0.12, width_ratios=[1, 1.05])

    # a  TEST contrasts with both intervals
    ax = fig.add_subplot(ga[0, 0])
    order = t.groupby("study_id").lnRR.mean().sort_values().index.tolist()
    x = t.study_id.map({s: i for i, s in enumerate(order)})
    jit = t.groupby("study_id").cumcount().to_numpy()
    xs = x + (jit - t.groupby("study_id").lnRR.transform("size").to_numpy() / 2 + 0.5) * 0.08
    for m, col, nm, off in [(B, B_COL, "B: median (V2/V3.1)", -0.02), (A, A_COL, "A: multilevel mean (V4)", 0.02)]:
        p, q = m["point_lnRR"], m["intervals_90"]["single_contrast_q"]
        if col == A_COL:
            ax.axhspan(p - q, p + q, color=col, alpha=0.08, lw=0)
        ax.axhline(p, color=col, lw=2, label=f"{nm}: {p:+.2f}, 90 % ±{q:.2f}")
        ax.axhline(p - q, color=col, lw=0.8, ls="--")
        ax.axhline(p + q, color=col, lw=0.8, ls="--")
    inside = (t.lnRR - A["point_lnRR"]).abs() <= A["intervals_90"]["single_contrast_q"]
    ax.scatter(xs[inside], t.lnRR[inside], s=14, color=INK, zorder=3, label="TEST contrast (covered by A)")
    ax.scatter(xs[~inside], t.lnRR[~inside], s=16, facecolor="white", edgecolor=INK, zorder=3, label="not covered by A")
    ax.set_xticks(range(len(order)), order, fontsize=6.3)
    ax.set_xlabel("TEST study (sorted by mean effect)")
    ax.set_ylabel("observed lnRR")
    ax.legend(frameon=False, loc="upper left", ncol=2)
    lab(ax, f"a  TEST 2024–2026: {rep['n_contrasts']} contrasts, {rep['n_studies']} studies (post-hoc re-use)")

    # b  metrics A vs B
    ax = fig.add_subplot(gb[0, 0])
    mets =[("group-MAE", "group_mae"), ("RMSE", "rmse"), ("|bias|", "bias_study_balanced"),
            ("half-width, 1 contrast", "half_width_single_mean"), ("half-width, whole study", "half_width_simultaneous")]
    yy = np.arange(len(mets))
    for k, (n, key) in enumerate(mets):
        vb, va = abs(b[key]), abs(a[key])
        ax.barh(k - 0.19, vb, height=0.36, color=B_COL, label="B median" if k == 0 else None)
        ax.barh(k + 0.19, va, height=0.36, color=A_COL, label="A multilevel mean" if k == 0 else None)
        ax.text(vb + 0.02, k - 0.19, f"{vb:.3f}", va="center", fontsize=6, color=INK)
        ax.text(va + 0.02, k + 0.19, f"{va:.3f}", va="center", fontsize=6, color=INK)
    ax.set_yticks(yy, [m[0] for m in mets], fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.75)
    ax.set_xlabel("lnRR (lower is better)")
    ax.legend(frameon=False, loc="upper right")
    lab(ax, "b  TEST metrics")

    # c  criteria
    ax = fig.add_subplot(gb[0, 1])
    ax.axis("off")
    cr = rep["criteria"]
    bs = rep["paired_bootstrap_by_study"]
    rows = [("H1a interval score A < B", f"{a['interval_score_single']:.2f} vs {b['interval_score_single']:.2f}", True),
            ("H1b coverage A ≥ 0.85", f"{a['coverage_single']:.3f} (B {b['coverage_single']:.3f})", False),
            ("H1  primary (a and b)", "", cr["H1_primary_interval"]),
            ("H2  whole-study cov. ≥ 0.85", f"{a['coverage_simultaneous']:.2f} (B {b['coverage_simultaneous']:.2f})", cr["H2_simultaneous"]),
            ("H3  |bias| A < |bias| B", f"{a['bias_study_balanced']:+.3f} vs {b['bias_study_balanced']:+.3f}", cr["H3_bias"]),
            ("H4  MAE ≤ 0.587; A−B ≤ 0.05", f"{a['group_mae']:.3f} vs {b['group_mae']:.3f}", cr["H4_accuracy_noninferiority"])]
    for i, (n, v, ok) in enumerate(rows):
        yv = 0.93 - i * 0.105
        ax.text(0.0, yv, n, fontsize=6.5, color=INK, transform=ax.transAxes, weight="bold" if n.startswith("H1 ") else None)
        ax.text(0.56, yv, v, fontsize=6.3, color=INK, transform=ax.transAxes)
        ax.text(1.0, yv, "pass" if ok else "fail", fontsize=6.5, ha="right", weight="bold",
                color="#2e8b57" if ok else "#c0392b", transform=ax.transAxes)
    d1 = bs["interval_score_single_A_minus_B"]
    ax.text(0.0, 0.26, f"Interval score A − B: {d1['diff']:+.2f} (95 % CI {d1['ci95'][0]:+.2f} … {d1['ci95'][1]:+.2f})\n"
            f"Coverage 0.847: 10 of 12 studies fully covered;\nall misses in T077 and T096.", fontsize=6.3, color=INK,
            transform=ax.transAxes, va="top")
    ax.text(0.0, 0.02, f"Pre-registered verdict: {rep['verdict']}", fontsize=8, weight="bold", color=INK,
            transform=ax.transAxes)
    lab(ax, "c  Pre-registered criteria (H1 is primary)")
    save(fig, "Fig13_V4_TEST_posthoc",
         f"Figure 13. Second, post-hoc look at the 2024-2026 TEST (label POST_HOC_TEST_REUSE; the TEST had been "
         f"evaluated once by V2). Model A (multilevel random-effects mean, selected on TRAIN CV) and comparator B "
         f"(row median) were frozen and pre-registered at {reg['registered_at_utc'][11:19]} UTC with SHA-256 locks, "
         f"8 s before the single evaluation. (a) TEST contrasts and the two frozen 90 % one-contrast intervals. "
         f"(b) Accuracy and interval width. (c) Criteria: A gives a 12 % narrower interval, a better interval score and "
         f"less bias, but single-contrast coverage 0.847 is below the pre-registered 0.85 (same as B), so H1 fails and "
         f"the verdict is PARTIAL. Not an independent confirmation.")


def table2():
    rep = json.loads((OUT / "test_posthoc" / "TEST_POSTHOC_REPORT.json").read_text(encoding="utf-8"))
    iv = pd.read_csv(OUT / "intervals" / "interval_comparison.csv")
    c = pd.read_csv(OUT / "rma" / "rma_comparison.csv").set_index("candidate")
    g = lambda m, meth, col: float(iv[(iv.model == m) & (iv.method == meth)][col].iloc[0])
    a, b = rep["A_new_multilevel_mean"], rep["B_V31_median"]
    rows = [
        ("Point estimate (lnRR)", "0.285 (median)", "0.431 (rma.mv REML)", "TRAIN 403 contrasts / 69 studies"),
        ("CV group-MAE", f"{c.loc[REF].group_mae:.3f}", f"{c.loc['R:rma_mv|intercept'].group_mae:.3f}", "+5.6 %; CI includes 0"),
        ("CV bias", f"{c.loc[REF].bias_study_balanced:+.3f}", f"{c.loc['R:rma_mv|intercept'].bias_study_balanced:+.3f}", "study-balanced"),
        ("CV 90 % half-width, one contrast", f"±{g(REF, 'group_cvplus_contrast', 'half_width_mean'):.2f}",
         f"±{g('R:rma_mv|intercept', 'group_cvplus_contrast', 'half_width_mean'):.2f}",
         f"coverage {g(REF, 'group_cvplus_contrast', 'coverage_study_balanced'):.3f} -> {g('R:rma_mv|intercept', 'group_cvplus_contrast', 'coverage_study_balanced'):.3f}"),
        ("CV interval score, one contrast", f"{g(REF, 'group_cvplus_contrast', 'interval_score_study_balanced'):.2f}",
         f"{g('R:rma_mv|intercept', 'group_cvplus_contrast', 'interval_score_study_balanced'):.2f}", "-8.4 %; CI < 0"),
        ("TEST group-MAE", f"{b['group_mae']:.3f}", f"{a['group_mae']:.3f}", "post-hoc TEST re-use"),
        ("TEST RMSE", f"{b['rmse']:.3f}", f"{a['rmse']:.3f}", ""),
        ("TEST bias", f"{b['bias_study_balanced']:+.3f}", f"{a['bias_study_balanced']:+.3f}", "study-balanced"),
        ("TEST coverage, one contrast", f"{b['coverage_single']:.3f}", f"{a['coverage_single']:.3f}", "pre-registered threshold 0.85: not met"),
        ("TEST coverage, whole study", f"{b['coverage_simultaneous']:.3f}", f"{a['coverage_simultaneous']:.3f}", "11/12 -> 12/12"),
        ("TEST interval score, one contrast", f"{b['interval_score_single']:.2f}", f"{a['interval_score_single']:.2f}", "-11.6 %; CI < 0"),
        ("Pre-registered verdict", "", rep["verdict"], "H1 not met (coverage)"),
    ]
    pd.DataFrame(rows, columns=["quantity", "V2/V3.1 median", "V4 multilevel mean", "note"]).to_csv(
        F / "Table2_V4.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    fig12(); fig13(); table2()
    print("written to", F)
