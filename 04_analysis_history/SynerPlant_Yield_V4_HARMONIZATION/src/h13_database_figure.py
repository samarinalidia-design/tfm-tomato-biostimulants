"""H13 - Fig21_database: the verified relational evidence database (TRAIN_DEV, class A), queried read-only.
a  schema with live row counts      b  endpoints measured      c  computable contrast types by endpoint
d  provenance and data quality      e  risk of bias by domain
Source: SynerPlant_Yield_V2/db/TFM_V3_WORKING.sqlite (opened with mode=ro)."""
from __future__ import annotations
import sqlite3, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from h00_common import OUT, V2

F = OUT / "figures_TFM_A4_V4"
DB = V2 / "db" / "TFM_V3_WORKING.sqlite"
BLUE, GREEN, ORANGE, GREY, INK, RED, PURPLE = "#2a6f97", "#2e8b57", "#e07a2f", "#c9ced6", "#333333", "#c0392b", "#7a5195"
plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 6.8,
                     "ytick.labelsize": 6.8, "legend.fontsize": 6.3, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "DejaVu Sans", "axes.titleweight": "bold",
                     "axes.titlelocation": "left"})
W = 7.0


def fmt(n):
    return f"{n:,}".replace(",", " ")


def box(ax, x, y, w, h, title, lines, ec=BLUE, fc="#eef3f7"):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.004,rounding_size=0.015",
                                fc=fc, ec=ec, lw=0.9))
    ax.text(x, y + h / 2 - 0.035, title, ha="center", va="top", fontsize=6.6, weight="bold", color=INK)
    ax.text(x, y - 0.02, lines, ha="center", va="center", fontsize=5.9, color=INK, linespacing=1.3)


def arrow(ax, x0, y0, x1, y1, c="#555"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", lw=0.8, color=c, shrinkA=0, shrinkB=0, mutation_scale=7))


def main():
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    q = lambda s: pd.read_sql(s, c)
    n = lambda t: int(c.execute(f'select count(*) from "{t}"').fetchone()[0])
    files = q("select role, count(*) k from files group by role").set_index("role").k
    arms = q("select role, count(*) k from arms group by role").set_index("role").k
    meas = q("select source_kind, count(*) k from measurements group by 1").set_index("source_kind").k
    nmods = int(c.execute("select count(distinct feature) from moderators").fetchone()[0])

    fig = plt.figure(figsize=(W, 10.2))
    ga = fig.add_axes([0.01, 0.635, 0.98, 0.345])
    ga.set_xlim(0, 1)
    ga.set_ylim(0, 1)
    ga.axis("off")
    ga.set_title("a  Relational evidence database (class A, TRAIN_DEV): entities and current row counts", fontsize=8.5)
    y1, y2 = 0.74, 0.25
    bw, bh = 0.15, 0.25
    xs = [0.09, 0.26, 0.43, 0.60, 0.77, 0.925]
    main = [("Source files", f"{fmt(n('files'))}\nfull texts {files.get('FULLTEXT', 0)}\nsupplements {files.get('SUPPLEMENT', 0)}"),
            ("Studies", f"{fmt(n('studies'))}\nidentity, year,\nDOI, role"),
            ("Experiments", f"{fmt(n('experiments'))}\nsystem, allocation,\nfactorial check"),
            ("Arms", f"{fmt(n('arms'))}\nC {arms.get('C', 0)} · S {arms.get('S', 0)}\nB {arms.get('B', 0)} · SB {arms.get('SB', 0)}"),
            ("Measurements", f"{fmt(n('measurements'))}\ntable {fmt(meas.get('TABLE', 0))}\nfigure {fmt(meas.get('FIGURE', 0))}"),
            ("Contrasts", f"{fmt(n('contrast_candidates'))}\nlnRR + variance\n+ dependency id")]
    for x, (t, l) in zip(xs, main):
        box(ga, x, y1, bw if x < 0.9 else 0.13, bh, t, l)
    for a, b in zip(xs[:-1], xs[1:]):
        arrow(ga, a + bw / 2, y1, b - (bw if b < 0.9 else 0.13) / 2, y1)
    side = [(0.09, "Source receipts", f"{fmt(n('wf_source_receipts'))} quotes / cells\n{fmt(n('wf_fig_points'))} digitised points", 4),
            (0.26, "Study relations", f"{n('study_relations')} links\n(companion papers,\nshared data)", 1),
            (0.43, "Moderators", f"{fmt(n('moderators'))} values\n{nmods} features,\nall source-adjudicated", 2),
            (0.60, "Risk of bias", f"{fmt(n('risk_of_bias'))} judgements\n10 domains", 2),
            (0.77, "Covariance", f"{fmt(n('covariance'))} pairs\n(shared controls,\nrepeated measures)", 5),
            (0.925, "Analysis marts", f"{sum(1 for t in c.execute(chr(32).join(['select name from sqlite_master', 'where type=' + repr('table'), 'and name like ' + repr('A_%')])))} versioned\nsets (yield, biomass,\nS×B, A×B, …)", 5)]
    for x, t, l, src in side:
        box(ga, x, y2, bw if x < 0.9 else 0.13, 0.23, t, l, ec="#888", fc="#f6f6f6")
        arrow(ga, x if x < 0.9 else 0.925, y1 - bh / 2, x if x < 0.9 else 0.925, y2 + 0.115, c="#999")
    ga.text(0.5, 0.035, "Every value carries a source file, page, locator and verbatim quote; contrasts carry the lowest "
            "verification level of their inputs.", ha="center", fontsize=6.2, color=INK, style="italic")

    # b endpoints
    gs = fig.add_gridspec(2, 2, left=0.17, right=0.97, top=0.58, bottom=0.165, hspace=0.55, wspace=0.75,
                          width_ratios=[1, 1.15])
    ax = fig.add_subplot(gs[0, 0])
    e = q("select endpoint, count(distinct study_id) s, count(*) k from measurements group by 1 order by s desc").head(10)
    col = [BLUE if x == "FRUIT_YIELD" else GREEN if x == "DRY_BIOMASS" else PURPLE if x.startswith("BIOTIC") else GREY
           for x in e.endpoint]
    ax.barh(range(len(e)), e.s, color=col, height=0.62)
    for i, (s, k) in enumerate(zip(e.s, e.k)):
        ax.text(s + 2, i, f"{s} ({fmt(k)})", va="center", fontsize=6)
    ax.set_yticks(range(len(e)), [x.lower().replace("_", " ") for x in e.endpoint], fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlim(0, e.s.max() * 1.35)
    ax.set_xlabel("studies (measurements)")
    ax.set_title("b  Endpoints measured", fontsize=8.5)

    # c contrast types x endpoint (studies)
    ax = fig.add_subplot(gs[0, 1])
    ct = q("select endpoint, contrast_type, count(distinct study_id) s from contrast_candidates group by 1,2")
    eps = ["FRUIT_YIELD", "DRY_BIOMASS", "FRUIT_NUMBER", "MEAN_FRUIT_MASS", "BIOTIC_SEVERITY"]
    types = ["SB_vs_S", "S_vs_C", "B_vs_C", "SxB", "AxB"]
    M = ct.pivot_table(index="endpoint", columns="contrast_type", values="s", fill_value=0).reindex(index=eps, columns=types,
                                                                                                    fill_value=0)
    im = ax.imshow(M.to_numpy(), cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#f4f7fa", BLUE, "#163e57"]),
                   aspect="auto", vmin=0)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = int(M.iat[i, j])
            ax.text(j, i, str(v) if v else "–", ha="center", va="center", fontsize=6.3,
                    color="white" if v > M.to_numpy().max() * 0.5 else INK)
    ax.set_xticks(range(len(types)), ["SB vs S\n(primary)", "S vs C\n(damage)", "B vs C\n(no stress)", "S × B", "A × B"],
                  fontsize=6)
    ax.set_yticks(range(len(eps)), [x.lower().replace("_", " ") for x in eps], fontsize=6.4)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("c  Computable contrasts (studies)", fontsize=8.5)

    # d provenance and quality (100 % stacked)
    ax = fig.add_subplot(gs[1, 0])
    cc = q("select min_verification v, var_available a from contrast_candidates")
    disp = q("select dispersion_type d, count(*) k from measurements group by 1").set_index("d").k
    rows = [("value source\n(measurements)", [("table", meas.get("TABLE", 0), BLUE), ("figure (digitised)", meas.get("FIGURE", 0), ORANGE),
                                              ("supplement / text", meas.drop(["TABLE", "FIGURE"], errors="ignore").sum(), GREY)]),
            ("dispersion reported\n(measurements)", [("SE", disp.get("SE", 0), BLUE), ("SD", disp.get("SD", 0), GREEN),
                                                     ("CI95", disp.get("CI95", 0), PURPLE), ("unclear", disp.get("UNCLEAR", 0), "#e9b38a"),
                                                     ("none", disp.get("NONE", 0), GREY)]),
            ("verification\n(contrasts)", [("double extraction agrees", int((cc.v == "DOUBLE_AGREE").sum()), GREEN),
                                           ("adjudicated", int((cc.v == "ADJUDICATED").sum()), ORANGE),
                                           ("human verified", int((cc.v == "HUMAN_VERIFIED").sum()), BLUE)]),
            ("sampling variance\n(contrasts)", [("available", int((cc.a == 1).sum()), GREEN), ("not computable", int((cc.a == 0).sum()), GREY)])]
    for i, (nm, parts) in enumerate(rows):
        tot = sum(p[1] for p in parts)
        left = 0
        for lab, v, colr in parts:
            w = 100 * v / tot
            ax.barh(i, w, left=left, color=colr, height=0.62, edgecolor="white", lw=0.8)
            if w >= 9:
                ax.text(left + w / 2, i, f"{lab}\n{w:.0f} %", ha="center", va="center", fontsize=5.3,
                        color="white" if colr in (BLUE, GREEN, PURPLE, ORANGE) else INK, linespacing=1.1)
            left += w
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=6.2)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of records")
    ax.set_title("d  Provenance and data quality", fontsize=8.5)

    # e risk of bias
    ax = fig.add_subplot(gs[1, 1])
    rb = q("select domain, judgement, count(*) k from risk_of_bias group by 1,2")
    P = rb.pivot_table(index="domain", columns="judgement", values="k", fill_value=0)
    P = P.div(P.sum(1), axis=0) * 100
    order = ["low", "some_concerns", "unclear", "high"]
    P = P.reindex(columns=order, fill_value=0).sort_values("low")
    colr = {"low": GREEN, "some_concerns": "#e9b38a", "unclear": GREY, "high": RED}
    for i, (d, r) in enumerate(P.iterrows()):
        left = 0
        for k in order:
            ax.barh(i, r[k], left=left, color=colr[k], height=0.62, edgecolor="white", lw=0.6,
                    label=k.replace("_", " ") if i == 0 else None)
            if r[k] >= 12:
                ax.text(left + r[k] / 2, i, f"{r[k]:.0f}", ha="center", va="center", fontsize=5.6,
                        color="white" if k in ("low", "high") else INK)
            left += r[k]
    ax.set_yticks(range(len(P)), [d.replace("_", " ") for d in P.index], fontsize=6.2)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of experiment-level judgements")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.4, -0.17), ncol=4, fontsize=6)
    ax.set_title("e  Risk of bias by domain", fontsize=8.5)

    cap = ("Figure 21. The SynerPlant evidence database (class A studies of the development corpus; read-only query of "
           "the working SQLite). (a) Core entities from source file to computable contrast with current row counts; grey "
           "boxes are the provenance, context, quality and dependency layers attached to them. (b) Studies and "
           "measurements per endpoint (blue: primary yield; green: secondary biomass; purple: biotic outcomes). "
           "(c) Studies with each computable contrast type: SB vs S is the primary mitigation estimand, S x B and A x B "
           "the interaction estimands. (d) Where the numbers come from and how they were checked: share of measurements "
           "read from tables or digitised from figures, reported dispersion type, verification level of contrasts "
           "(double independent extraction agreeing, adjudicated, human verified) and availability of a sampling "
           "variance. (e) Risk-of-bias judgements by domain; 'unclear' mostly reflects incomplete reporting.")
    fig.text(0.01, 0.004, textwrap.fill(cap, 140), fontsize=6.2, color=INK, ha="left", va="bottom")
    for ext in ("png", "pdf", "svg"):
        fig.savefig(F / f"Fig21_database.{ext}", dpi=300 if ext == "png" else None)
    plt.close(fig)
    print("Fig21 written")


if __name__ == "__main__":
    main()
