"""SynerPlant Yield V2 - local TFM dashboard (streamlit run dashboard/app.py; binds to 127.0.0.1)."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

V2 = Path(__file__).resolve().parents[1]
OUT = V2 / "outputs"
DATA, ML, UNC, META = OUT / "data", OUT / "ml", OUT / "uncertainty", OUT / "meta"
st.set_page_config(page_title="SynerPlant Yield V2", layout="wide")


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@st.cache_data
def csv(p, **kw):
    return pd.read_csv(p, low_memory=False, **kw)


BASE = ["row_mean", "row_median", "study_mean", "study_median"]
sections = ["Data Quality", "Yield Dataset", "Model Performance", "Feature Importance", "Validation",
            "Prediction Uncertainty", "Subgroup Analysis", "Independent TEST", "Biomass (secondary)", "Scientific Interpretation"]
sec = st.sidebar.radio("Section", sections)
st.sidebar.caption("PRIMARY TARGET: fruit-yield lnRR = ln(Yield SB / Yield S). Studies are the independent units.")
freeze = V2 / "exports"
fz = sorted(freeze.glob("DATA_FREEZE_V2_*/MANIFEST.json"))
if fz:
    m = rj(fz[-1])
    st.sidebar.markdown(f"**Freeze:** `{fz[-1].parent.name}`  \n**Status:** {m.get('status')}")

if sec == "Data Quality":
    st.header("Data Quality")
    integ = rj(V2 / "audit" / "integrity_report.json")
    st.subheader(f"Integrity checks on the V2 working SQLite - overall {integ['overall']}")
    st.dataframe(pd.DataFrame(integ["checks"]), width="stretch", hide_index=True)
    st.subheader("Source-verified decisions (corrections register)")
    reg = rj(V2 / "audit" / "corrections_register.json")
    rows = [{"section": k, "id": it.get("id", ""), "policy": it.get("policy", ""), "study": it.get("study_id", ""),
             "summary": (it.get("finding") or it.get("evidence") or it.get("reason") or "")[:300]}
            for k, v in reg.items() if not k.startswith("_") for it in v]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption("Policy: A confirmed error, B ambiguous (safe choice + sensitivity), C unresolved, D methodological "
               "proposal. Agent checks are AUTO_VERIFIED_V2, never HUMAN_VERIFIED.")
    uq = V2 / "audit" / "UNRESOLVED_QUEUE.csv"
    if uq.exists():
        st.subheader("Unresolved questions")
        st.dataframe(csv(uq), width="stretch", hide_index=True)

elif sec == "Yield Dataset":
    st.header("Yield Dataset")
    rep = rj(DATA / "dataset_build_report.json")
    s = pd.DataFrame([{"set": k, **{x: v[x] for x in ("rows", "studies", "biotic_studies")}} for k, v in rep["sets"].items()])
    st.dataframe(s, width="stretch", hide_index=True)
    reg = csv(DATA / "v2_yield_contrast_register.csv")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.histogram(reg, x="status", color="yield_tier", title="Candidate yield contrasts by status"),
                        width="stretch")
    with c2:
        d = csv(DATA / "PRIMARY_EXPANDED.csv")
        st.plotly_chart(px.box(d, x="stress_family", y="lnRR", points="all", title="PRIMARY_EXPANDED lnRR by stress (no error bars)"),
                        width="stretch")
    st.subheader("Feature completeness (PRIMARY_EXPANDED)")
    st.dataframe(csv(DATA / "feature_completeness.csv"), width="stretch", hide_index=True)
    st.subheader("Contrast register (included and excluded, with reasons)")
    f = st.selectbox("filter status", ["(all)"] + sorted(reg.status.unique()))
    st.dataframe(reg if f == "(all)" else reg[reg.status == f], width="stretch", hide_index=True)

elif sec == "Model Performance":
    st.header("Model Performance (grouped 5 x 5 repeated nested CV)")
    sel = rj(ML / "selection_report.json")
    st.json(sel["selection"].get("PRIMARY_EXPANDED", {}))
    mc = csv(ML / "model_comparison.csv")
    ds = st.selectbox("dataset", sorted(mc.dataset.unique()), index=sorted(mc.dataset.unique()).index("PRIMARY_EXPANDED"))
    x = mc[mc.dataset == ds].sort_values("group_mae")
    fig = go.Figure(go.Bar(x=x.group_mae, y=x.candidate, orientation="h",
                           error_x=dict(type="data", array=x.group_mae_sd_seeds),
                           marker_color=["#2e8b57" if f in BASE else "#2a6f97" for f in x.family]))
    fig.update_layout(height=650, yaxis=dict(autorange="reversed"), xaxis_title="group-balanced MAE (lnRR)",
                      title="Error bars = Type A: SD of group-MAE across 5 CV seeds")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(x, width="stretch", hide_index=True)
    st.subheader("Ablation F0 -> F4")
    st.dataframe(csv(ML / "ablation_F0_F4.csv"), width="stretch", hide_index=True)
    st.info(f"V1 reference group-MAE {sel['v1_reference']['group_mae']:.3f}: {sel['v1_reference']['note']}. "
            "Compare V1 to V2 only through the V1_EQUIVALENT dataset rows above (same pipeline, same splits).")

elif sec == "Feature Importance":
    st.header("Feature Importance (exploratory, not causal)")
    cp = OUT / "model" / "coefficients.csv"
    pi = ML / "permutation_importance.csv"
    if pi.exists():
        st.subheader("Grouped permutation importance (increase in group-MAE when a feature block is shuffled)")
        t = csv(pi)
        st.plotly_chart(px.bar(t, x="importance_mean", y="feature", error_x="importance_sd", orientation="h",
                               title="Error bars = SD over outer folds and seeds"), width="stretch")
    if cp.exists():
        st.subheader("Coefficients of the saved linear model (standardised numeric; one-hot categories)")
        st.dataframe(csv(cp), width="stretch")
    if not (pi.exists() or cp.exists()):
        st.write("The selected model is a constant baseline: no feature importance exists by construction.")

elif sec == "Validation":
    st.header("Validation")
    fm = csv(ML / "cv_fold_metrics.csv")
    ds = st.selectbox("dataset", sorted(fm.dataset.unique()), index=sorted(fm.dataset.unique()).index("PRIMARY_EXPANDED"))
    cands = sorted((fm[fm.dataset == ds].family + "|" + fm[fm.dataset == ds].fs).unique())
    pick = st.multiselect("candidates", cands, default=[c for c in cands if c.split("|")[0] in ("study_median", "row_mean")][:2] +
                          [rj(ML / "selection_report.json")["selection"][ds]["chosen"]] if ds in rj(ML / "selection_report.json")["selection"] else cands[:3])
    x = fm[(fm.dataset == ds) & (fm.family + "|" + fm.fs).isin(pick)].assign(candidate=lambda t: t.family + "|" + t.fs)
    st.plotly_chart(px.strip(x, x="candidate", y="group_mae", color="seed", title="Group-MAE per outer fold (25 folds; no error bars)"),
                    width="stretch")
    st.subheader("Per-study out-of-fold errors")
    st.dataframe(csv(ML / "per_study_errors.csv"), width="stretch", hide_index=True)

elif sec == "Prediction Uncertainty":
    st.header("Prediction Uncertainty")
    st.markdown("**Four different quantities - never mixed:** A = CV error bars (model-assessment noise); "
                "B = conformal prediction interval for a future experiment; C = CI of the pooled mean (meta-analysis); "
                "D = meta-analytic prediction interval (heterogeneity of true study effects).")
    s = csv(UNC / "interval_methods_comparison.csv")
    st.subheader("Type B: interval methods, coverage measured on held-out studies")
    st.dataframe(s, width="stretch", hide_index=True)
    dep = rj(UNC / "deployment_intervals.json")
    st.metric("V2 90% half-width, single new contrast (lnRR)", f"{dep['single_contrast_q']:.2f}",
              delta=f"{dep['single_contrast_q'] - dep['v1_half_width']:.2f} vs V1 ({dep['v1_half_width']:.2f})", delta_color="inverse")
    st.metric("V2 90% half-width, all contrasts of a new study simultaneously", f"{dep['simultaneous_q']:.2f}")
    st.subheader("Types C and D: meta-analysis")
    mm = rj(META / "meta_summary.json")
    st.dataframe(pd.DataFrame(mm["overall"]), width="stretch", hide_index=True)
    st.subheader("Try a prediction")
    try:
        import joblib, sys
        sys.path.insert(0, str(V2 / "src"))
        model = joblib.load(OUT / "model" / "V2_YIELD_MODEL.joblib")
        d = csv(DATA / "PRIMARY_EXPANDED.csv")
        row = {}
        cols = st.columns(3)
        for i, c in enumerate(getattr(model.prep, "cat", []) if model.prep else []):
            row[c] = cols[i % 3].selectbox(c, ["(unknown)"] + sorted(d[c].dropna().astype(str).unique()))
        for i, c in enumerate(getattr(model.prep, "num", []) if model.prep else []):
            v = cols[i % 3].text_input(c, "")
            row[c] = float(v) if v.strip() else np.nan
        X = pd.DataFrame([{k: (np.nan if v == "(unknown)" else v) for k, v in row.items()}])
        for c in d.columns:
            if c not in X:
                X[c] = np.nan
        r = model.predict_interval(X)
        st.write(r.round(3))
        st.caption("lnRR prediction with 90% conformal interval for one new contrast; % = 100*(exp(lnRR)-1).")
    except Exception as e:  # noqa
        st.warning(f"model not available: {e}")

elif sec == "Subgroup Analysis":
    st.header("Subgroup Analysis")
    sg = csv(ML / "subgroup_performance.csv")
    g = st.selectbox("subgroup", sorted(sg.subgroup.unique()))
    x = sg[sg.subgroup == g]
    st.plotly_chart(px.bar(x, x="level", y="group_mae", color="model", barmode="group",
                           hover_data=["n_rows", "n_studies", "bias"], title="Out-of-fold group-MAE by subgroup (no error bars)"),
                    width="stretch")
    st.dataframe(x, width="stretch", hide_index=True)
    st.subheader("Meta-analytic subgroups (exploratory)")
    st.dataframe(csv(META / "meta_subgroups.csv"), width="stretch", hide_index=True)

elif sec == "Independent TEST":
    st.header("Independent TEST 2024-2026 (one-time, pre-registered)")
    TST = OUT / "test_evaluation"
    if not (TST / "TEST_EVALUATED.lock").exists():
        st.info("The TEST has not been evaluated yet.")
    else:
        rep, mt = rj(TST / "TEST_REPORT.json"), rj(TST / "TEST_meta.json")
        P, C = rep["primary"], rep["conditional"]
        st.caption(f"Evaluated {rep['evaluated_at']} (registration {rep['registration']}). Nothing re-fitted on TEST.")
        c = st.columns(4)
        c[0].metric("TEST studies / contrasts", f"{P['n_studies']} / {P['n_contrasts']}")
        c[1].metric("group-MAE (TRAIN CV 0.361)", f"{P['group_mae']:.3f}", "pass (<= 0.587)" if P["pass_accuracy_transport"] else "fail")
        c[2].metric("coverage single (>= 0.85)", f"{P['coverage_single']:.3f}", "pass" if P["pass_coverage_single"] else "fail", delta_color="normal" if P["pass_coverage_single"] else "inverse")
        c[3].metric("coverage simultaneous (>= 0.85)", f"{P['coverage_simultaneous']:.3f}", "pass" if P["pass_coverage_simultaneous"] else "fail")
        st.subheader(f"Conditional stress-damage models - verdict: {C['verdict'].replace('_', ' ')}")
        st.dataframe(pd.DataFrame([{"model": "median", "TEST group-MAE": C["median_group_mae"]}] +
                                  [{"model": k, "TEST group-MAE": C[k]["group_mae"], "gain vs median": C[k]["gain_vs_median"],
                                    "null-world 95th pct": C[k]["null_gain_q95"], "coverage single": C[k]["coverage_single"]}
                                   for k in ("C1", "C2", "C3")]), width="stretch", hide_index=True)
        s = C["between_slope"]
        st.caption(f"Between-study slope on damage: {s['observed']:+.3f} (95% CI {s['ci95'][0]:.2f} to {s['ci95'][1]:.2f}; "
                   f"null band {s['null_band95'][0]:.2f} to {s['null_band95'][1]:.2f}; TRAIN -0.59). Criteria: {C['criteria']}")
        st.subheader("Meta-analysis (R metafor + CR2)")
        rows = [{"set": k, "studies": mt[k]["k_studies"], "pooled lnRR": mt[k]["mu_lnRR"],
                 "effect %": 100 * np.expm1(mt[k]["mu_lnRR"]), "CI low": mt[k]["ci95_CR2"][0], "CI high": mt[k]["ci95_CR2"][1],
                 "PI low": mt[k]["pi95_new_study_mean"][0], "PI high": mt[k]["pi95_new_study_mean"][1]}
                for k in ("TRAIN", "TEST", "TRAIN_plus_TEST")]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        d = mt["TRAIN_vs_TEST"]
        st.caption(f"TEST - TRAIN difference {d['diff_TEST_minus_TRAIN']:+.3f} (95% CI {d['ci95_CR2'][0]:.2f} to "
                   f"{d['ci95_CR2'][1]:.2f}, p = {d['p_CR2']:.2f}): consistent.")
        fig = OUT / "figures_TFM_A4" / "Fig5_TRAIN_vs_TEST.png"
        if fig.exists():
            st.image(str(fig), caption="Figure 5. TRAIN vs independent TEST")
        te = OUT / "test_inputs" / "TEST_PRIMARY.csv"
        if te.exists():
            with st.expander("TEST contrasts used (TEST_PRIMARY)"):
                st.dataframe(csv(te), width="stretch", hide_index=True)

elif sec == "Biomass (secondary)":
    st.header("Biomass V2 - dry biomass lnRR (secondary target)")
    BIO = OUT / "biomass_v2"
    rep = rj(BIO / "data" / "dataset_build_report.json")
    sel = rj(BIO / "ml" / "selection_report.json")["selection"]["PRIMARY_EXPANDED"]
    dep = rj(BIO / "uncertainty" / "deployment_intervals.json")
    c = st.columns(4)
    s = rep["sets"]["PRIMARY_EXPANDED"]
    c[0].metric("contrasts / studies", f"{s['rows']} / {s['studies']}", "V1: 708 / 145")
    c[1].metric("selected predictor", sel["chosen"], f"group-MAE {sel['best_baseline_group_mae']:.3f} (V1 0.257)")
    c[2].metric("90% interval, single", f"±{dep['single_contrast_q']:.2f}", f"V1 ±{dep['v1_half_width']:.2f}", delta_color="off")
    c[3].metric("90% interval, whole study", f"±{dep['simultaneous_q']:.2f}")
    st.subheader("Model comparison (grouped 5x5 nested CV)")
    mc = csv(BIO / "ml" / "model_comparison.csv")
    st.dataframe(mc[mc.dataset == "PRIMARY_EXPANDED"][["candidate", "group_mae", "gain_vs_best_baseline", "diff_ci_lo",
                                                      "diff_ci_hi", "median_fold_wins_of_5", "passes_rule"]].head(15),
                 width="stretch", hide_index=True)
    st.subheader("Stress gradient and conditional models (TRAIN CV)")
    st.dataframe(csv(BIO / "stress_recovery" / "predictive_cv.csv"), width="stretch", hide_index=True)
    st.subheader("Meta-analysis TRAIN (R metafor + CR2)")
    st.dataframe(csv(BIO / "meta" / "R_vs_python.csv")[["set", "k_studies", "R_mu", "R_pct", "R_CI95_CR2", "R_PI95_new_study"]],
                 width="stretch", hide_index=True)
    TB = BIO / "test_evaluation"
    if (TB / "TEST_EVALUATED.lock").exists():
        tr, tm = rj(TB / "TEST_REPORT.json"), rj(TB / "TEST_meta.json")
        P, C = tr["primary"], tr["conditional"]
        st.subheader(f"Independent biomass TEST ({P['n_studies']} studies, evaluated {tr['evaluated_at']})")
        c = st.columns(4)
        c[0].metric("group-MAE", f"{P['group_mae']:.3f}", "pass" if P["pass_accuracy_transport"] else "fail")
        c[1].metric("coverage single", f"{P['coverage_single']:.3f}", "pass" if P["pass_coverage_single"] else "fail")
        c[2].metric("coverage simultaneous", f"{P['coverage_simultaneous']:.3f}", "pass" if P["pass_coverage_simultaneous"] else "fail")
        c[3].metric("TEST pooled effect", f"+{100 * np.expm1(tm['TEST']['mu_lnRR']):.0f}%",
                    f"TRAIN +{100 * np.expm1(tm['TRAIN']['mu_lnRR']):.0f}%, p = {tm['TRAIN_vs_TEST']['p_CR2']:.2f}", delta_color="off")
        st.caption(f"Conditional C1 verdict: {C['verdict']} (criteria {C['criteria']}); C3 secondary: "
                   f"{'PASS' if C.get('C3_secondary_pass') else 'FAIL'} (gain {C['C3']['gain_vs_median']:.0%})")
    for f in ("Fig6_biomass_V1_to_V2.png", "Fig7_biomass_TEST.png", "Fig8_influence.png", "Fig9_forest_yield.png", "Fig10_forest_biomass.png", "Fig11_publication_bias.png"):
        fp = OUT / "figures_TFM_A4" / f
        if fp.exists():
            st.image(str(fp), caption=f.replace(".png", ""))

else:
    st.header("Scientific Interpretation")
    rp = V2 / "FINAL_REPORT_EN.md"
    st.markdown(rp.read_text(encoding="utf-8") if rp.exists() else "Report not generated yet.")
