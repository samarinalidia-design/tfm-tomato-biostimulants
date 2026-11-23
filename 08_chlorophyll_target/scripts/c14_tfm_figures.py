"""TFM-style figures and tables (same layout conventions as the V5 figures of the TFM, v5_style) with the chlorophyll targets
added to fruit yield and dry biomass. Written to 08_chlorophyll_target/figures_TFM_V8 and tables_TFM_V8; the V5 originals used
in the TFM are not modified.  Numbers refer to the TFM document (TFM_Agrobiologia_Ambiental_Samarina.docx):
  Fig09  evidence landscape (stress x biostimulant class)                 + Table13
  Fig10  meta-analytic summary (pooled effects, variance partition)        + Table14
  Fig12b chlorophyll: study effects and subgroups (as Fig 11/12)
  Fig16  model selection on TRAIN (comparable grouped CV, four targets)    + Table15 (CV and TEST)
  Fig19b chlorophyll: frozen models on the 2024-2026 TEST studies (as Fig 18/19)
  Fig20  TEST criteria, four targets                                       + Table16
  Fig24b leave-one-study-out influence (chlorophyll)
  Fig25b small-study effects / publication bias (chlorophyll)
Sources: yield / biomass meta and TEST = V5 results (v5/results/meta, v5/results/test); CV for all four targets = c09 (same engine,
features and settings); chlorophyll meta = c13 (v5_05_meta.R statistics), TEST = c12 (frozen before TEST extraction).
"""
import sys, json, pathlib
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
V5S = REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'
sys.path.insert(0, str(V5S))
import v5_style as S
S.FIG = OUT / 'figures_TFM_V8'; S.FIG.mkdir(exist_ok=True)
S.VERSION_TAG = 'V8 chlorophyll (2026-11-23)'
from v5_style import plt, C, W, pct, panel, STRESS_LABEL, CLASS_LABEL
save = S.save
TAB = OUT / 'tables_TFM_V8'; TAB.mkdir(exist_ok=True)
V5R = REPO / '05_analysis_train_expansion_v5' / 'v5' / 'results'
M8 = OUT / 'v8_meta' / 'results' / 'meta'
R = OUT / 'results'
TG = ['yield', 'biomass', 'chlorophyll', 'chl_index']
TL = {'yield': 'Fruit yield', 'biomass': 'Dry biomass', 'chlorophyll': 'Leaf chlorophyll content', 'chl_index': 'Chlorophyll index (SPAD etc.)'}
TC = {'yield': C['train'], 'biomass': C['bio'], 'chlorophyll': '#b5651d', 'chl_index': '#7a5195'}
CHL = ['chlorophyll', 'chl_index']
SHORT = {'yield': 'Yield', 'biomass': 'Biomass', 'chlorophyll': 'Chl content', 'chl_index': 'Chl index'}
MLAB.update(S.MODEL_LABEL) if False else None
EP12 = {'chlorophyll': 'CHL_CONTENT', 'chl_index': 'CHL_INDEX'}
MLAB = {'BASELINE_mean': 'Mean (baseline)', 'BASELINE_mean_studyw': 'Mean, equal study weight', 'MR0': '3-level mean (MR0)',
        'RIDGE_REF_wivw_re': 'Ridge, ivw weights', 'RIDGE_REF_wnone': 'Ridge, no weights', 'RIDGE_REF_wn': 'Ridge, equal study weight',
        'RF_REF_wivw_re': 'RF, ivw weights', 'RF_REF_wn': 'RF, equal study weight'}


def ML2(m):
    return MLAB.get(m, S.MODEL_LABEL.get(m, m))


def meta(name):
    a = pd.read_csv(V5R / 'meta' / name); b = pd.read_csv(M8 / name)
    return pd.concat([a, b], ignore_index=True)


POOL = meta('pooled_effects.csv'); MAT = meta('class_x_stress_matrix.csv'); SUB = meta('subgroups_CR2.csv')
FOR = pd.read_csv(M8 / 'forest_studies.csv'); LOO = pd.read_csv(M8 / 'leave_one_study_out.csv'); BIAS = pd.read_csv(M8 / 'publication_bias.csv')


# ------------------------------------------------------------------------------------------------ Fig09 + Table13
def fig09():
    stresses = ['SALINITY', 'DROUGHT', 'HEAT', 'COLD', 'NUTRIENT', 'HEAVY_METAL', 'BIOTIC', 'COMBINED', 'NONE']
    classes = ['DJ_BENEFICIAL_BACTERIA', 'DJ_BENEFICIAL_FUNGI', 'DJ_INORGANIC', 'DJ_SEAWEED_BOTANICAL', 'DJ_PROTEIN_N', 'DJ_HUMIC_FULVIC',
               'DJ_CHITOSAN_BIOPOLYMER', 'DJ_OTHER_NON_DUJARDIN', 'DJ_MIXTURE']
    fig, ax = plt.subplots(2, 2, figsize=(W, 6.6))
    for col, ep in enumerate(CHL):
        m = MAT[MAT.endpoint == ep]
        for row, what in enumerate(['studies', 'effect']):
            a = ax[row, col]
            Z = np.full((len(classes), len(stresses)), np.nan)
            for i, c in enumerate(classes):
                for j, s in enumerate(stresses):
                    q = m[(m.biostimulant_class == c) & (m.stress == s)]
                    if len(q):
                        q = q.iloc[0]
                        Z[i, j] = q.studies if what == 'studies' else (pct(q.mu) if pd.notna(q.mu) else pct(q.median_study_mean))
                        txt = f'{int(q.studies)}' if what == 'studies' else (f'{pct(q.mu):+.0f}' if pd.notna(q.mu) else f'{pct(q.median_study_mean):+.0f}')
                        a.text(j, i, txt, ha='center', va='center', fontsize=5.4, fontweight='bold' if (what == 'effect' and pd.notna(q.mu)) else 'normal',
                               fontstyle='normal' if (what == 'studies' or pd.notna(q.mu)) else 'italic',
                               color='white' if ((what == 'studies' and Z[i, j] >= 15) or (what == 'effect' and (Z[i, j] > 55 or Z[i, j] < -20))) else '#222')
            if what == 'studies':
                a.imshow(Z, cmap='Blues', vmin=0, vmax=np.nanmax(Z) if np.isfinite(np.nanmax(Z)) else 1, aspect='auto')
            else:
                from matplotlib.colors import TwoSlopeNorm
                a.imshow(Z, cmap='RdBu_r', norm=TwoSlopeNorm(vmin=-30, vcenter=0, vmax=80), aspect='auto')
            a.set_xticks(range(len(stresses))); a.set_xticklabels([STRESS_LABEL[s].replace(' (B vs C)', '\n(B vs C)') for s in stresses], rotation=55, ha='right', fontsize=5.4)
            a.set_yticks(range(len(classes))); a.set_yticklabels([CLASS_LABEL[c] for c in classes] if col == 0 else [], fontsize=5.6)
            panel(a, 'abcd'[row * 2 + col], f'{SHORT[ep]}: ' + ('independent studies' if what == 'studies' else 'effect, %'))
    fig.tight_layout()
    save(fig, 'Fig09_evidence_landscape_chlorophyll', 'Fig. 9 (V8 addition). Evidence landscape for the chlorophyll targets (TRAIN), laid out as Fig. 9 for fruit yield. '
         '(a, b) Independent studies per stress class × biostimulant class; (c, d) effect of the biostimulant (SB vs S and B vs C): bold = pooled mean of a '
         'three-level REML model (≥ 3 studies), italics = median of study means (< 3 studies, no inference). Classes harmonised by the V5 feature code.')
    T = MAT[(MAT.studies >= 5) & MAT.mu.notna()].copy()
    T['effect_pct'] = pct(T.mu).round(1); T['ci95'] = [f'[{pct(a):+.1f}, {pct(b):+.1f}]' for a, b in zip(T.ci_lo, T.ci_hi)]
    T['pi95'] = [f'[{pct(a):+.0f}, {pct(b):+.0f}]' for a, b in zip(T.pi_lo, T.pi_hi)]
    T['endpoint'] = T.endpoint.map(TL); T['stress'] = T.stress.map(STRESS_LABEL); T['biostimulant_class'] = T.biostimulant_class.map(CLASS_LABEL)
    T = T[['endpoint', 'stress', 'biostimulant_class', 'studies', 'k', 'effect_pct', 'ci95', 'pi95']].sort_values(['endpoint', 'stress', 'studies'], ascending=[True, True, False])
    T.to_csv(TAB / 'Table13_class_x_stress_four_targets.csv', index=False)
    return T


# ------------------------------------------------------------------------------------------------ Fig10 + Table14
def fig10():
    sets = ['TRAIN_primary', 'TRAIN_SB_vs_S_only', 'TRAIN_author_SD_only', 'TEST', 'TRAIN_plus_TEST']
    fig, ax = plt.subplots(1, 2, figsize=(W, 3.9), gridspec_kw=dict(width_ratios=[1.6, 1]))
    a = ax[0]; y = 0; yt, yl = [], []
    for ep in TG:
        P = POOL[POOL.endpoint == ep].set_index('set')
        for s in sets:
            if s not in P.index or pd.isna(P.loc[s, 'mu']):
                continue
            q = P.loc[s]
            a.hlines(y, pct(q.pi_lo), pct(q.pi_hi), color=TC[ep], lw=0.6); a.hlines(y, pct(q.ci_lo), pct(q.ci_hi), color=TC[ep], lw=2.6)
            a.plot(pct(q.mu), y, 'D', color=TC[ep], ms=3.2)
            a.text(1.01, y, f'{pct(q.mu):+.0f} % [{pct(q.ci_lo):+.0f}, {pct(q.ci_hi):+.0f}] k={int(q.studies)}', transform=a.get_yaxis_transform(), fontsize=4.9, va='center')
            yt.append(y); yl.append(f'{TL[ep].split(" (")[0]}: {s.replace("TRAIN_", "").replace("_", " ")}'); y -= 1
        y -= 0.6
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=5.0); a.axvline(0, color='#555', lw=0.5); a.set_xlim(-60, 260)
    a.set_xlabel('Pooled effect, % (3-level REML, CR2 95 % CI; thin = 95 % PI)'); panel(a, 'a', 'Pooled effects by data set')
    a = ax[1]
    for i, ep in enumerate(TG):
        q = POOL[(POOL.endpoint == ep) & (POOL.set == 'TRAIN_primary')].iloc[0]
        parts = np.array([q.tau2_study, q.tau2_within, q.typical_vi]); parts = parts / parts.sum(); left = 0
        for v, lab, colr in zip(parts, ['between studies', 'within studies', 'sampling'], [TC[ep], '#9fb7c9', C['grey']]):
            a.barh(i, 100 * v, left=left, color=colr, label=lab if i == 0 else None)
            if v > 0.05:
                a.text(left + 50 * v, i, f'{100 * v:.0f}%', ha='center', va='center', fontsize=5.4, color='white' if lab == 'between studies' else '#222')
            left += 100 * v
        a.text(103, i, f'τ = {np.sqrt(q.tau2_study + q.tau2_within):.2f}', fontsize=5.4, va='center')
    a.set_yticks(range(4)); a.set_yticklabels([TL[e].replace(' (', '\n(') for e in TG], fontsize=5.6); a.invert_yaxis(); a.set_xlim(0, 128)
    a.set_xlabel('% of variance of lnRR'); a.legend(frameon=False, fontsize=5.0, loc='upper center', bbox_to_anchor=(0.45, -0.15), ncol=2)
    panel(a, 'b', 'Variance (TRAIN)')
    fig.tight_layout()
    save(fig, 'Fig10_meta_summary_four_targets', 'Fig. 10 (V8). Meta-analytic summary for fruit yield, dry biomass and the two chlorophyll targets. (a) Pooled effects for '
         'different data subsets, TEST and TRAIN+TEST; (b) partition of the variance (between studies, within studies, typical sampling variance). Same model and '
         'code for all targets (v5_05_meta.R: rma.mv REML, study/contrast random effects, shared-control covariance, CR2 robust CI).')
    rows = []
    for ep in TG:
        for r in POOL[(POOL.endpoint == ep) & POOL.set.isin(sets + ['TEST_minus_TRAIN'])].itertuples():
            rows.append(dict(endpoint=TL[ep], data_set=r.set, studies=int(r.studies), contrasts=int(r.k), effect_pct=round(pct(r.mu), 1),
                             ci95=f'[{pct(r.ci_lo):+.1f}, {pct(r.ci_hi):+.1f}]',
                             pi95='' if pd.isna(r.pi_lo) else f'[{pct(r.pi_lo):+.0f}, {pct(r.pi_hi):+.0f}]',
                             tau_total='' if pd.isna(r.tau2_study) else round(float(np.sqrt(r.tau2_study + r.tau2_within)), 3),
                             I2='' if pd.isna(r.I2) else round(float(r.I2), 1)))
    T = pd.DataFrame(rows); T.to_csv(TAB / 'Table14_pooled_effects_four_targets.csv', index=False)
    return T


# ------------------------------------------------------------------------------------------------ Fig12b
def fig12b():
    fig, ax = plt.subplots(2, 2, figsize=(W, 7.2), gridspec_kw=dict(height_ratios=[1.6, 1]))
    for col, ep in enumerate(CHL):
        f = FOR[FOR.endpoint == ep].sort_values('yi')
        a = ax[0, col]; y = np.arange(len(f))
        a.hlines(y, pct(f.yi - 1.96 * np.sqrt(f.vi)), pct(f.yi + 1.96 * np.sqrt(f.vi)), color=TC[ep], lw=0.6)
        a.scatter(pct(f.yi), y, s=4 + 60 * f.weight_pct / f.weight_pct.max(), marker='s', color=TC[ep])
        q = POOL[(POOL.endpoint == ep) & (POOL.set == 'TRAIN_primary')].iloc[0]
        a.axvspan(pct(q.ci_lo), pct(q.ci_hi), color=TC[ep], alpha=0.15); a.axvline(0, color='#555', lw=0.5)
        a.set_yticks(y); a.set_yticklabels(f.study_id, fontsize=2.6 if len(f) > 60 else 3.6); a.set_xlim(-80, 300)
        a.set_xlabel('Study effect, % (95 % CI)'); panel(a, 'ab'[col], f'{SHORT[ep]}: {len(f)} studies (TRAIN)')
        a = ax[1, col]; s = SUB[(SUB.endpoint == ep) & SUB.moderator.isin(['h_stress_class', 'h2_dujardin'])].copy()
        s = s.sort_values(['moderator', 'mu']); yy = np.arange(len(s))
        a.hlines(yy, pct(s.ci_lo), pct(s.ci_hi), color=TC[ep], lw=1.6); a.plot(pct(s.mu), yy, 'D', color=TC[ep], ms=3)
        lab = [(('other stress' if mo == 'h_stress_class' else 'other class') if l == 'other' else STRESS_LABEL.get(l, CLASS_LABEL.get(l, l))) + f' (k={int(k)})'
               for l, k, mo in zip(s.level, s.studies, s.moderator)]
        a.set_yticks(yy); a.set_yticklabels(lab, fontsize=5.0); a.axvline(0, color='#555', lw=0.5); a.set_xlim(-40, 120)
        p = s.groupby('moderator').p_HTZ.first()
        a.set_xlabel('Subgroup mean, % (CR2 CI); Wald p: stress ' + f'{p.get("h_stress_class", np.nan):.2f}, class {p.get("h2_dujardin", np.nan):.2f}', fontsize=5.6)
        panel(a, 'cd'[col], f'{SHORT[ep]}: subgroups (≥ 4 studies)')
    fig.tight_layout()
    save(fig, 'Fig12b_forest_chlorophyll', 'Fig. 12b (V8 addition). Chlorophyll targets: study effects and subgroups (TRAIN), panels as in Figs 11 and 12. (a, b) Study aggregates '
         '(ρ = 0.5 within study) with 95 % CI, square size = weight in the three-level model, shaded band = CR2 95 % CI of the pooled mean; (c, d) subgroup means '
         'by stress class and biostimulant class with robust CI and Wald (HTZ) p-values.')


# ------------------------------------------------------------------------------------------------ Fig16 + Table15
def cv_table():
    rows = []
    for t in TG:
        for g, suf in [('A399', ''), ('group', '_authorgroup')]:
            s = pd.read_csv(R / f'c09_cv_summary_{t}{suf}.csv')
            for r in s.itertuples():
                rows.append(dict(target=t, grouping=g, model=r.model, RMSE=r.RMSE, d=r.d_vs_mean_pct, lo=r.d_ci_low_pct, hi=r.d_ci_high_pct, R2=r.R2))
    return pd.DataFrame(rows)


def test_table():
    tm5 = pd.read_csv(V5R / 'test' / 'v5_test_metrics_POST_HOC_TEST_REUSE.csv')
    rows = []
    for ep in ['yield', 'biomass']:
        x = tm5[tm5.endpoint == ep]; base = x[x.model == 'BASELINE_mean'].RMSE.iloc[0]
        for r in x.itertuples():
            rows.append(dict(target=ep, model=r.model, RMSE=r.RMSE, R2=r.R2, coverage=r.coverage95, d=100 * r.dRMSE_vs_mean / base,
                             lo=100 * r.dRMSE_vs_mean_ci_lo / base, hi=100 * r.dRMSE_vs_mean_ci_hi / base, selected=bool(r.selected),
                             studies=r.n_studies, contrasts=r.n_contrasts))
    tm8 = pd.read_csv(R / 'c12_test_metrics.csv')
    for t in CHL:
        for r in tm8[tm8.endpoint == EP12[t]].itertuples():
            rows.append(dict(target=t, model=r.model, RMSE=r.RMSE, R2=r.R2, coverage=r.coverage95, d=r.d_vs_mean_pct, lo=r.d_vs_mean_ci_lo_pct,
                             hi=r.d_vs_mean_ci_hi_pct, selected=bool(r.primary or r.ml_candidate), studies=r.n_studies, contrasts=r.n_contrasts))
    return pd.DataFrame(rows)


def fig16():
    A = cv_table()
    models = ['BASELINE_mean', 'MR0', 'RIDGE_REF_wivw_re', 'RIDGE_REF_wn', 'RF_REF_wivw_re', 'RF_REF_wn']
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.6), sharex=True)
    for a, t, letter in zip(ax.ravel(), TG, 'abcd'):
        y = np.arange(len(models))[::-1]
        for off, g, mk in [(0.14, 'A399', 'o'), (-0.14, 'group', 's')]:
            q = A[(A.target == t) & (A.grouping == g)].set_index('model').reindex(models)
            a.errorbar(q.d, y + off, xerr=[q.d - q.lo, q.hi - q.d], fmt=mk, ms=3.2, lw=0.8, color=TC[t] if g == 'A399' else '#777',
                       label='folds by A399 dependency cluster' if g == 'A399' else 'folds by research group (stricter)')
        a.axvline(0, color='#555', lw=0.6); a.axvspan(-100, 0, color='#eaf4ea', zorder=0)
        a.set_yticks(y); a.set_yticklabels([MLAB[m] for m in models], fontsize=5.4); a.set_xlim(-37, 22)
        n = pd.read_parquet(OUT / 'data' / 'train_chl_index_V8.parquet') if False else None
        panel(a, letter, TL[t])
        if letter in 'cd':
            a.set_xlabel('CV RMSE change vs mean, %')
    h, l = ax[0, 0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.legend(h, l, frameon=False, fontsize=5.6, loc='lower center', ncol=2)
    save(fig, 'Fig16_model_selection_four_targets', 'Fig. 16 (V8). Model selection on TRAIN for four targets with one engine (nested grouped CV, 5 outer folds × 3 seeds, '
         'inner 3 folds; V5 REF design features; same models and weights). Points: change of the CV RMSE relative to the training mean with 95 % study-bootstrap '
         'CI; coloured = folds by A399 dependency cluster, grey = folds by research group (shared authors), which removes near-duplicate publications of one group.')
    T = test_table()
    rows = []
    for t in TG:
        cvA = A[(A.target == t) & (A.grouping == 'A399')].set_index('model'); cvG = A[(A.target == t) & (A.grouping == 'group')].set_index('model')
        for m in models:
            r = dict(target=TL[t], model=MLAB[m],
                     CV_RMSE=round(cvA.RMSE.get(m, np.nan), 4), CV_d_vs_mean_pct=round(cvA.d.get(m, np.nan), 1),
                     CV_ci=f'[{cvA.lo.get(m, np.nan):+.1f}, {cvA.hi.get(m, np.nan):+.1f}]',
                     CVgroup_d_vs_mean_pct=round(cvG.d.get(m, np.nan), 1), CVgroup_ci=f'[{cvG.lo.get(m, np.nan):+.1f}, {cvG.hi.get(m, np.nan):+.1f}]')
            rows.append(r)
    pd.DataFrame(rows).to_csv(TAB / 'Table15a_CV_four_targets.csv', index=False)
    T2 = T.copy(); T2['target'] = T2.target.map(TL)
    T2['d_ci'] = [f'[{a:+.1f}, {b:+.1f}]' for a, b in zip(T2.lo, T2.hi)]
    T2 = T2[['target', 'model', 'selected', 'studies', 'contrasts', 'RMSE', 'R2', 'coverage', 'd', 'd_ci']].round(3)
    T2.to_csv(TAB / 'Table15b_TEST_four_targets.csv', index=False)
    return A, T


# ------------------------------------------------------------------------------------------------ Fig19b
def fig19b():
    tp = pd.read_csv(R / 'c12_test_predictions.csv'); tm = pd.read_csv(R / 'c12_test_metrics.csv'); spec = json.loads((OUT / 'freeze' / 'MODEL_FREEZE_CHL.json').read_text(encoding='utf-8'))
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.8))
    for col, t in enumerate(CHL):
        ep = EP12[t]; prim = spec['targets'][ep]['primary']; mlc = spec['targets'][ep]['ml_candidate']
        a = ax[0, col]; d = tp[(tp.endpoint == ep) & (tp.model == mlc)].copy()
        st = d.groupby('study_id').y.median().sort_values().index.tolist()
        d['xi'] = d.study_id.map({s: i for i, s in enumerate(st)}) + np.random.default_rng(0).uniform(-0.25, 0.25, len(d))
        out = (d.y < d.lo) | (d.y > d.hi)
        a.scatter(d.xi[~out], d.y[~out], s=7, color=C['test'], alpha=0.75, label='TEST contrast (inside interval)')
        a.scatter(d.xi[out], d.y[out], s=11, marker='D', color=C['red'], label='outside 95 % interval')
        a.axhline(0, color='#555', lw=0.5); a.axhline(spec['targets'][ep]['train_mean'], color=C['train'], lw=0.8, ls='--', label='TRAIN mean')
        a.set_xticks(range(len(st))); a.set_xticklabels(st, rotation=90, fontsize=4.6); a.set_ylabel('Observed lnRR'); a.legend(frameon=False, fontsize=5, loc='lower right')
        panel(a, 'ab'[col], f'{SHORT[t]}: {d.study_id.nunique()} studies, {len(d)} contr.')
        a = ax[1, col]; r = tm[tm.endpoint == ep].set_index('model')
        ms = ['BASELINE_mean', 'MR0', 'RIDGE_REF_wivw_re', 'RIDGE_REF_wn', 'RF_REF_wivw_re', 'RF_REF_wn']; r = r.reindex(ms); y = np.arange(len(ms))[::-1]
        a.barh(y + 0.18, r.RMSE_CV, 0.36, color=C['train'], label='TRAIN CV')
        a.barh(y - 0.18, r.RMSE, 0.36, color=C['test'], xerr=[r.RMSE - r.RMSE_ci_lo, r.RMSE_ci_hi - r.RMSE], error_kw=dict(lw=0.5), label='TEST (95 % cluster bootstrap)')
        a.set_yticks(y); a.set_yticklabels([MLAB[m] + (' ◀ primary' if m == prim else (' ◀ ML candidate' if m == mlc else '')) for m in ms], fontsize=5.2)
        for yy, m in zip(y, ms):
            a.text(1.01, yy - 0.18, f'{r.loc[m, "d_vs_mean_pct"]:+.0f} %', fontsize=4.8, va='center', transform=a.get_yaxis_transform())
        a.set_xlabel('RMSE (lnRR); right: TEST vs mean')
        if col == 0:
            a.legend(frameon=False, fontsize=5, loc='upper center', bbox_to_anchor=(1.1, -0.17), ncol=2)
        panel(a, 'cd'[col], f'{SHORT[t]}: CV vs TEST')
    fig.tight_layout()
    save(fig, 'Fig19b_chlorophyll_TEST', 'Fig. 19b (V8 addition). Chlorophyll targets: frozen models on the 2024-2026 TEST studies, as Figs 18 and 19. Models were fitted '
         'on TRAIN and frozen (MODEL_FREEZE_CHL.json, SHA-256) before any TEST chlorophyll value was extracted; the TEST corpus was used before for yield and '
         'biomass (POST_HOC_TEST_REUSE for the corpus, first use for chlorophyll). (a, b) TEST contrasts with the 95 % interval of the pre-declared ML candidate; '
         '(c, d) RMSE in CV and on TEST.')


# ------------------------------------------------------------------------------------------------ Fig20 + Table16
def fig20(T):
    v5 = pd.read_csv(V5R / 'test' / 'v5_test_verdict_POST_HOC_TEST_REUSE.csv'); v8 = pd.read_csv(R / 'c12_test_verdict.csv')
    rows = []
    for r in v5.itertuples():
        rows.append(dict(target=r.endpoint, role='selected A', model=r.selected_A, H1=r.H1_point_better_than_mean, H2=r.H2_transfer, H3=r.H3_coverage, verdict=r.verdict))
    for r in v8.itertuples():
        t = 'chlorophyll' if r.endpoint == 'CHL_CONTENT' else 'chl_index'
        if r.role == 'ml_candidate' and t == 'chl_index':
            continue                                   # identical to the primary model for the index
        rows.append(dict(target=t, role='primary' if r.role == 'primary' else 'pre-declared ML candidate', model=r.model, H1=r.H1_better_than_mean,
                         H2=r.H2_transfer, H3=r.H3_coverage, verdict=r.verdict))
    V = pd.DataFrame(rows)
    fig, ax = plt.subplots(1, 2, figsize=(W, 3.4), gridspec_kw=dict(width_ratios=[1, 1.3]))
    a = ax[0]; a.axis('off')
    ROLE = {'selected A': 'selected', 'primary': 'primary', 'pre-declared ML candidate': 'ML cand.'}
    cell = [[SHORT[r.target], ROLE[r.role], ML2(r.model).replace('design features', 'REF').replace('equal study weight', 'eq. weight').replace(' weights', '').replace('Mean (baseline)', 'Mean'), '✔' if r.H1 else '✘', '✔' if r.H2 else '✘', '✔' if r.H3 else '✘', r.verdict] for r in V.itertuples()]
    tb = a.table(cellText=cell, colLabels=['Target', 'Role', 'Model', 'H1', 'H2', 'H3', 'Verdict'], loc='center', cellLoc='center',
                 colWidths=[0.17, 0.14, 0.27, 0.07, 0.07, 0.07, 0.21])
    tb.auto_set_font_size(False); tb.set_fontsize(4.6); tb.scale(1, 1.5)
    panel(a, 'a', 'Pre-specified TEST criteria')
    a = ax[1]; y = 0; yt, yl = [], []
    for t in TG:
        x = T[T.target == t]
        for r in x[~x.model.isin(['BASELINE_mean'])].itertuples():
            if r.model not in ('MR0', 'RIDGE_REF', 'RF_REF', 'RIDGE_REF_wivw_re', 'RIDGE_REF_wn', 'RF_REF_wivw_re', 'RF_REF_wn', 'LSTACK_A') and not r.selected:
                continue
            a.errorbar(r.d, y, xerr=[[r.d - r.lo], [r.hi - r.d]], fmt='D' if r.selected else 'o', color=TC[t], ms=3.4 if r.selected else 2.6, lw=0.8)
            yt.append(y); yl.append(f'{SHORT[t]}: {ML2(r.model)}' + (' ◀' if r.selected else '')); y -= 1
        y -= 0.5
    a.axvline(0, color='#555', lw=0.6); a.axvspan(-100, 0, color='#eaf4ea', zorder=0); a.set_xlim(-40, 45)
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=4.6); a.set_xlabel('TEST RMSE change vs TRAIN mean, % (95 % CI)')
    panel(a, 'b', 'TEST: change relative to the mean')
    fig.tight_layout()
    save(fig, 'Fig20_TEST_criteria_four_targets', 'Fig. 20 (V8). Pre-specified TEST criteria for fruit yield, dry biomass (V5 frozen models) and the chlorophyll targets '
         '(models frozen before the chlorophyll TEST extraction). H1: selected model better than the mean (95 % CI of the RMSE difference below 0); H2: transfer, '
         'RMSE_TEST ≤ 1.25 × RMSE_CV; H3: coverage of the 95 % interval ≥ 0.90. (b) ◀ = selected / pre-declared models; other models shown for context.')
    V.assign(target=V.target.map(TL)).to_csv(TAB / 'Table16_TEST_criteria_four_targets.csv', index=False)
    return V


# ------------------------------------------------------------------------------------------------ Fig24b, Fig25b
def fig24b_25b():
    fig, ax = plt.subplots(1, 2, figsize=(W, 3.0))
    for a, t, letter in zip(ax, CHL, 'ab'):
        l = LOO[LOO.endpoint == t].sort_values('mu'); q = POOL[(POOL.endpoint == t) & (POOL.set == 'TRAIN_primary')].iloc[0]
        y = np.arange(len(l)); a.hlines(y, pct(l.ci_lo), pct(l.ci_hi), color=TC[t], lw=0.5); a.plot(pct(l.mu), y, '.', color=TC[t], ms=3)
        a.axvline(pct(q.mu), color='#333', lw=0.7, ls='--'); a.set_yticks([])
        sh = (pct(l.mu) - pct(q.mu)).abs().max()
        a.set_xlabel(f'Pooled effect without one study, % (max shift {sh:.1f} points)'); panel(a, letter, f'{SHORT[t]}: leave-one-study-out')
    fig.tight_layout()
    save(fig, 'Fig24b_influence_chlorophyll', 'Fig. 24b (V8 addition). Leave-one-study-out influence on the pooled TRAIN effect of the chlorophyll targets, as Fig. 24. '
         'Dashed line = pooled effect with all studies (three-level REML).')
    fig, ax = plt.subplots(1, 3, figsize=(W, 2.9), gridspec_kw=dict(width_ratios=[1, 1, 1.1]))
    for a, t, letter in zip(ax[:2], CHL, 'ab'):
        fu = pd.read_csv(M8 / f'funnel_{t}.csv'); b = BIAS[BIAS.endpoint == t].iloc[0]
        a.scatter(fu.yi[fu.filled == 0], fu.sei[fu.filled == 0], s=6, color=TC[t]); a.scatter(fu.yi[fu.filled == 1], fu.sei[fu.filled == 1], s=6, facecolor='none', edgecolor='#555')
        se = np.linspace(0, fu.sei.max() * 1.05, 20); a.plot(b.REML_study_level_mu - 1.96 * se, se, color='#999', lw=0.5); a.plot(b.REML_study_level_mu + 1.96 * se, se, color='#999', lw=0.5)
        a.axvline(b.REML_study_level_mu, color='#333', lw=0.6); a.invert_yaxis(); a.set_xlabel('Study effect (lnRR)'); a.set_ylabel('SE')
        panel(a, letter, TL[t].split(' (')[0])
    a = ax[2]; a.axis('off')
    B = BIAS.set_index('endpoint').reindex(CHL)
    rowsT = [('Egger p', [f'{v:.2f}' for v in B.egger_regtest_p]), ('Begg p', [f'{v:.3f}' for v in B.begg_ranktest_p]),
             ('Multilevel Egger p', [f'{v:.2f}' for v in B.ml_egger_p]), ('REML effect, %', [f'{pct(v):+.0f}' for v in B.REML_study_level_mu]),
             ('PET, %', [f'{pct(v):+.0f}' for v in B.PET_mu]), ('PEESE, %', [f'{pct(v):+.0f}' for v in B.PEESE_mu]),
             ('Trim-and-fill k0', [f'{int(v)}' for v in B.trimfill_k0])]
    tb = a.table(cellText=[[n] + v for n, v in rowsT], colLabels=['', SHORT['chlorophyll'], SHORT['chl_index']], loc='center', cellLoc='center',
                 colWidths=[0.5, 0.25, 0.25])
    tb.auto_set_font_size(False); tb.set_fontsize(5.2); tb.scale(1, 1.35); panel(a, 'c', 'Tests')
    fig.tight_layout()
    save(fig, 'Fig25b_publication_bias_chlorophyll', 'Fig. 25b (V8 addition). Small-study effects and publication bias for the chlorophyll targets, as Fig. 25: funnel plots of '
         'study aggregates (open = trim-and-fill), Egger, Begg and multilevel Egger tests, PET-PEESE and trim-and-fill estimates.')


if __name__ == '__main__':
    t13 = fig09(); t14 = fig10(); fig12b(); A, T = fig16(); fig19b(); V = fig20(T); fig24b_25b()
    with pd.ExcelWriter(TAB / 'TFM_tables_V8_four_targets.xlsx') as xw:
        for f in sorted(TAB.glob('Table*.csv')):
            pd.read_csv(f).to_excel(xw, sheet_name=f.stem[:31], index=False)
    print(V.to_string(index=False))
