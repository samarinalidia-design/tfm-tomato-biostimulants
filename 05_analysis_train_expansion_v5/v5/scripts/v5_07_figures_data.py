"""V5 figures that depend on the data and the meta-analysis only (descriptive estimates):
Fig1 (data V3.1 -> V5), Fig4 (stress gradient), Fig8 (influence), Fig9/Fig10 (forest), Fig11 (publication bias),
Fig14 (meta summary), Fig15 (evidence landscape + biostimulant class x stress matrix), Fig16 (PRISMA), Fig19 (interactions),
Fig21 (database). Tables: class_x_stress_matrix (CSV/XLSX)."""
import json, sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap
from scipy import stats
from v5_style import *

MASTER = V5.parents[1]
V4FIG = MASTER / 'TFM_A399_Agent_System_v2_2_2026-10-19/SynerPlant_Yield_V4_HARMONIZATION/outputs/figures_TFM_A4_V4'
TRAIN_FREEZE = MASTER / 'TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z'
TEST_FREEZE = MASTER / 'TFM_TEST_2024_2026_Agent_System/exports/DATA_FREEZE_20261118T105532769144Z'
M = RES / 'meta'; X = RES / 'extra'
ty, tb = default(load('yield')), default(load('dry_biomass'))
ey, eb = default(load('yield', 'test')), default(load('dry_biomass', 'test'))
pooled = pd.read_csv(M / 'pooled_effects.csv')
MEDVI = {'yield': default(load('yield')).var_lnrr_imp.median(), 'biomass': default(load('dry_biomass')).var_lnrr_imp.median()}


# ------------------------------------------------------------------ Fig1
def fig1():
    v31 = {k: pd.read_excel(V4FIG / f'SynerPlant_{k}_TRAIN_TEST_V3.1.xlsx', sheet_name=None) for k in ('YIELD', 'BIOMASS')}
    reg = pd.read_csv(DATA / 'corrections_register.csv')
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.6))
    a = ax[0, 0]
    rows = [('Yield TRAIN', len(v31['YIELD']['TRAIN']), v31['YIELD']['TRAIN'].study_id.nunique(), len(ty), ty.study_id.nunique()),
            ('Yield TEST', len(v31['YIELD']['TEST']), v31['YIELD']['TEST'].study_id.nunique(), len(ey), ey.study_id.nunique()),
            ('Biomass TRAIN', len(v31['BIOMASS']['TRAIN']), v31['BIOMASS']['TRAIN'].study_id.nunique(), len(tb), tb.study_id.nunique()),
            ('Biomass TEST', len(v31['BIOMASS']['TEST']), v31['BIOMASS']['TEST'].study_id.nunique(), len(eb), eb.study_id.nunique())]
    xx = np.arange(len(rows))
    a.bar(xx - 0.2, [r[1] for r in rows], 0.4, color=C['v1'], label='V3.1 (used for V4 figures)')
    a.bar(xx + 0.2, [r[3] for r in rows], 0.4, color=C['train'], label='V5 (this version)')
    for i, r in enumerate(rows):
        a.text(i - 0.2, r[1], f'{r[2]} st.', ha='center', va='bottom', fontsize=5.6)
        a.text(i + 0.2, r[3], f'{r[4]} st.', ha='center', va='bottom', fontsize=5.6)
    a.set_xticks(xx); a.set_xticklabels([r[0].replace(' ', chr(10)) for r in rows], fontsize=6.3); a.set_ylabel('Contrasts (default table)')
    a.set_ylim(0, a.get_ylim()[1] * 1.15); a.legend(frameon=False, loc='upper left'); panel(a, 'a', 'Data volume, V3.1 vs V5')
    a = ax[0, 1]
    reg['kind'] = reg.field.map(lambda f: 'size fractions -> total' if 'fraction' in f else ('year / experiment' if 'year' in f else
                                ('yield fraction excluded' if f == 'yield_scope' else ('stress reclassified' if 'stress' in f else f))))
    k = reg.groupby('kind').study_id.nunique()
    old = pd.read_parquet(V5.parent / 'data/processed/train_yield_v3.parquet', columns=['contrast_id', 'study_id', 'h_stress_class', 'h3_hybrid'])
    mm = old.merge(ty[['contrast_id', 'h_stress_class', 'h3_hybrid']], on='contrast_id', suffixes=('_old', '_new'))
    k['stress class recoded (fixed rules)'] = mm[mm.h_stress_class_old != mm.h_stress_class_new].study_id.nunique()
    k['hybrid unknown: 0 -> missing'] = mm[(mm.h3_hybrid_old == 0) & mm.h3_hybrid_new.isna()].study_id.nunique()
    a.barh(k.index, k.values, color=C['red']); a.set_xlabel('Studies affected')
    for i, v in enumerate(k.values):
        a.text(v, i, f' {v}', va='center', fontsize=6)
    # stress-class recoding (all rows of the yield TRAIN table)
    panel(a, 'b', 'Corrections (register)')
    a = ax[1, 0]
    s5 = ty.groupby('h_stress_class').study_id.nunique().sort_values()
    s31 = v31['YIELD']['TRAIN'].groupby('stress_family').study_id.nunique()
    a.barh(np.arange(len(s5)), s5.values, color=C['train'], label='V5 stress class')
    a.set_yticks(np.arange(len(s5))); a.set_yticklabels([STRESS_LABEL.get(c, c) for c in s5.index], fontsize=6.2)
    a.set_xlabel('Independent studies (yield TRAIN)'); panel(a, 'c', 'Studies per stress class (V5)')
    a.text(0.98, 0.35, chr(10).join(['V3.1 stress families (studies):'] + [f'{k.title()} {v}' for k, v in s31.sort_values(ascending=False).head(6).items()]),
           transform=a.transAxes, ha='right', fontsize=5.3, color='#555')
    a = ax[1, 1]
    feats = {'Cultivar': 'f_cultivar', 'Hybrid status': 'h_hybrid', 'Route': 'f_route', 'Dose': 'f_dose', 'Application stage': 'f_application_stage',
             'Stress onset stage': 'f_stress_onset_stage', 'Soil texture': 'f_soil_texture', 'Country': 'f_country', 'Season': 'f_season',
             'N applications': 'h3_n_applications', 'Plant density': 'h2_plant_density_m2', 'Latitude (printed)': 'f_latitude'}
    rep = {}
    for lab, c in feats.items():
        v = ty[c].astype(str).str.strip().str.lower()
        ok = ~v.isin(['', 'nan', 'none', 'unspecified', 'not reported', 'null'])
        rep[lab] = 100 * ty[ok].study_id.nunique() / ty.study_id.nunique()
    rep = pd.Series(rep).sort_values()
    a.barh(rep.index, rep.values, color=C['train']); a.axvline(20, color=C['red'], lw=0.7, ls='--')
    a.set_xlabel('% of yield TRAIN studies reporting'); a.set_xlim(0, 100); panel(a, 'd', 'Feature reporting')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig1_data_V31_to_V5', 'Fig. 1. Training and test data, V3.1 (basis of the V4 figure set) versus V5. (a) Contrasts and studies in the default tables; '
         'V5 keeps all yield-definition tiers as features and uses the 2024-2026 TEST freeze with the same selection rules. (b) Source-verified corrections '
         '(size fractions summed into total yield with SD not summed; measurement year bound per row for study 717; green-fruit fraction excluded; '
         'stress classes BIOTIC/COMBINED corrected; study 112 salinity flagged as disputed). (c) Independent studies per harmonised stress class. '
         '(d) Share of studies reporting each descriptor; unknown values stay missing (e.g. hybrid status UNSPECIFIED, never 0).', bottom=0.12)


# ------------------------------------------------------------------ Fig4 stress gradient
def fig4():
    sm = pd.read_csv(X / 'stress_gradient_study_means.csv'); gr = pd.read_csv(X / 'stress_gradient.csv')
    sal = pd.read_csv(X / 'salinity_expected_vs_realised.csv')
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.4))
    for a, ep, letter in [(ax[0, 0], 'yield', 'a'), (ax[1, 1], 'biomass', 'd')]:
        for role, col, mk in [('TRAIN', C['train'], 'o'), ('TEST', C['test'], 'D')]:
            s = sm[(sm.endpoint == ep) & (sm.role == role)]
            a.scatter(s.D, s.R, s=np.clip(s.k * 3, 6, 40), color=col, alpha=0.6, marker=mk, edgecolor='none', label=f'{role} ({len(s)} studies)')
            g = gr[(gr.endpoint == ep) & (gr.role == role)]
            if len(g):
                g = g.iloc[0]; xs = np.linspace(s.D.min(), s.D.max(), 10)
                a.plot(xs, g.intercept + g.slope * xs, color=col, lw=1.2)
                a.text(0.98, 0.95 if role == 'TRAIN' else 0.85, f'{role}: slope {g.slope:.2f} [{g.slope_ci_lo:.2f}, {g.slope_ci_hi:.2f}], R² {g.R2:.2f}; '
                       f'artefact ≈ {g.null_artefact_slope_approx:.2f}', transform=a.transAxes, ha='right', va='top', fontsize=5.6, color=col)
        a.axhline(0, color='#999', lw=0.5); a.axvline(0, color='#999', lw=0.5)
        a.set_xlabel('Stress damage D = ln(S/C)'); a.set_ylabel('Biostimulant effect ln(SB/S)'); a.legend(frameon=False, loc='lower left')
        panel(a, letter, f'{"Yield" if ep == "yield" else "Biomass"}: effect vs stress damage')
    a = ax[0, 1]
    for role, col in [('TRAIN', C['train']), ('TEST', C['test'])]:
        s = sm[(sm.endpoint == 'yield') & (sm.role == role) & (sm.D < -0.05)]
        a.hist((s.R / (-s.D)).clip(-1, 2.5), bins=np.linspace(-1, 2.5, 22), color=col, alpha=0.6, label=role)
    g = gr[(gr.endpoint == 'yield') & (gr.role == 'TRAIN')].iloc[0]
    a.axvline(g.recovered_share_median, color=C['train'], ls='--', lw=0.8); a.axvline(1, color='#555', lw=0.6)
    a.set_xlabel('Recovered share of the stress loss, ln(SB/S)/(-D)'); a.set_ylabel('Studies'); a.legend(frameon=False)
    panel(a, 'b', f'Yield: recovered share (median {g.recovered_share_median:.2f})')
    a = ax[1, 0]
    for role, col in [('TRAIN', C['train']), ('TEST', C['test'])]:
        s = sal[sal.role == role]
        a.scatter(100 * s.expected_loss, 100 * s.realised_loss, color=col, s=14, alpha=0.7, label=f'{role} ({len(s)})')
    s = sal[sal.role == 'TRAIN']; rho = stats.spearmanr(s.expected_loss, s.realised_loss)
    a.plot([0, 100], [0, 100], color='#888', lw=0.6, ls=':')
    a.set_xlabel('Expected yield loss, Maas-Hoffman (%)'); a.set_ylabel('Realised loss 1 - S/C (%)')
    a.text(0.02, 0.95, f'TRAIN Spearman ρ = {rho.correlation:.2f} (p = {rho.pvalue:.2f})', transform=a.transAxes, fontsize=6, va='top')
    a.legend(frameon=False, loc='lower right'); panel(a, 'c', 'Salinity: expected vs realised damage')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig4_stress_gradient', 'Fig. 4. Stress-damage gradient (descriptive). Study means of ln(SB/S) against the stress damage D = ln(S/C) of the same study; '
         'lines: between-study OLS, 95 % study-bootstrap CI in brackets; "artefact" = slope expected from the shared S arm alone (−mean var(S)/var(D)). '
         'Stronger damage goes with a larger relative biostimulant gain, but part of the slope is a shared-arm artefact and the relation is between studies '
         '(not causal). D is known only after the experiment, so it is used only as a conditional meta-regression moderator, never as an ML feature. '
         'Expected salinity loss: tomato threshold 2.5 dS/m, slope 9.9 %/dS/m (NaCl mM/10 as EC equivalent where EC is not printed).', bottom=0.13)


# ------------------------------------------------------------------ Fig8 influence
def fig8():
    loo = pd.read_csv(M / 'leave_one_study_out.csv')
    fig, ax = plt.subplots(1, 3, figsize=(W, 2.8), gridspec_kw=dict(width_ratios=[1.2, 1.2, 1]))
    out = []
    for a, ep, col, letter in [(ax[0], 'yield', C['train'], 'a'), (ax[1], 'biomass', C['bio'], 'b')]:
        l = loo[loo.endpoint == ep].sort_values('mu').reset_index(drop=True)
        full = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
        a.fill_between(range(len(l)), l.ci_lo, l.ci_hi, color=col, alpha=0.15, lw=0)
        a.plot(range(len(l)), l.mu, color=col, lw=1)
        a.axhline(full.mu, color='#333', ls='--', lw=0.7)
        sh = (l.mu - full.mu).abs(); i = sh.idxmax()
        a.annotate(f'max shift {sh.max():.3f}\n(without {l.left_out[i]})', (i, l.mu[i]), fontsize=5.5, xytext=(5, 10), textcoords='offset points')
        a.set_xlabel('Study left out (sorted)'); a.set_ylabel('Pooled lnRR'); panel(a, letter, f'{"Yield" if ep == "yield" else "Biomass"} (k = {len(l)} studies)')
        out.append((ep, sh.max(), (sh > 0.02).sum()))
    a = ax[2]
    a.bar(['Yield', 'Biomass'], [o[1] for o in out], color=[C['train'], C['bio']])
    for i, o in enumerate(out):
        a.text(i, o[1], f'{o[1]:.3f}\n{o[2]} studies > 0.02', ha='center', va='bottom', fontsize=5.8)
    a.set_ylabel('Max |shift| of pooled lnRR'); panel(a, 'c', 'Influence summary')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig8_influence', 'Fig. 8. Leave-one-study-out influence on the pooled TRAIN effect (rma.mv REML, study/contrast random effects, shared-control '
         'covariance; band = model-based 95 % CI). No single study changes the conclusion.', bottom=0.16)


# ------------------------------------------------------------------ Fig9 / Fig10 forest
def forest(ep, name, col):
    fs = pd.read_csv(M / 'forest_studies.csv'); fs = fs[fs.endpoint == ep].sort_values('yi').reset_index(drop=True)
    sg = pd.read_csv(M / 'subgroups_CR2.csv'); sg = sg[sg.endpoint == ep]
    p = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
    n = len(fs); h = max(6.0, 0.075 * n + 1.5)
    fig = plt.figure(figsize=(W, min(h, 11.5)))
    a = fig.add_axes([0.22, 0.10, 0.36, 0.86])
    lo, hi = fs.yi - 1.96 * np.sqrt(fs.vi), fs.yi + 1.96 * np.sqrt(fs.vi)
    a.hlines(range(n), lo.clip(-2, 3), hi.clip(-2, 3), color='#777', lw=0.5)
    a.scatter(fs.yi, range(n), s=4 + 40 * fs.weight_pct / fs.weight_pct.max(), marker='s', color=col, zorder=3)
    a.axvline(0, color=C['red'], lw=0.6); a.axvline(p.mu, color='#333', ls='--', lw=0.6)
    a.fill_betweenx([-2.5, -1.0], p.ci_lo, p.ci_hi, color='#333', alpha=0.8)
    a.set_yticks(range(n)); a.set_yticklabels([f'{s} ({k})' for s, k in zip(fs.study_id, fs.k)], fontsize=max(2.8, 6.5 - n / 40))
    a.set_ylim(-3, n); a.set_xlim(-2, 3); a.set_xlabel('lnRR (study aggregate, 95 % CI)')
    a.text(0.98, 0.01, f'pooled {pct(p.mu):+.0f} % [{pct(p.ci_lo):+.0f}, {pct(p.ci_hi):+.0f}], k = {int(p.studies)} studies / {int(p.k)} contrasts',
           transform=a.transAxes, ha='right', fontsize=6)
    a.set_title('a  Studies (TRAIN)', loc='left', fontsize=8.5, fontweight='bold')
    b = fig.add_axes([0.70, 0.10, 0.28, 0.86])
    y = 0; ticks = []; labels = []
    for g, gg in sg.groupby('moderator', sort=False):
        b.text(-0.6, y, f'{ {"h_stress_class": "Stress", "h2_dujardin": "Biostimulant class", "h_route": "Route", "h_system": "System"}[g]}  (HTZ p = {gg.p_HTZ.iloc[0]:.2f})',
               fontsize=6.2, fontweight='bold', va='center'); y -= 1
        for r in gg.sort_values('mu', ascending=False).itertuples():
            b.hlines(y, r.ci_lo, r.ci_hi, color=col, lw=1); b.plot(r.mu, y, 'o', color=col, ms=3)
            ticks.append(y); lab = r.level
            labels.append(f'{STRESS_LABEL.get(lab, CLASS_LABEL.get(lab, lab.title()))} ({int(r.studies)})'); y -= 1
        y -= 0.5
    b.set_yticks(ticks); b.set_yticklabels(labels, fontsize=5.4); b.axvline(0, color=C['red'], lw=0.6); b.axvline(p.mu, color='#333', ls='--', lw=0.6)
    b.set_xlim(-0.6, 1.5); b.set_xlabel('lnRR (CR2 95 % CI)')
    b.set_title('b  Subgroups', loc='left', fontsize=8.5, fontweight='bold')
    return fig, p


def fig9():
    fig, p = forest('yield', 'Fig9', C['train'])
    save(fig, 'Fig9_forest_yield', 'Fig. 9. Fruit yield, TRAIN. (a) Study aggregates (rho = 0.5 within study, compound symmetry); square size = rma.mv weight; '
         'bar at the bottom = pooled 95 % CR2 CI. (b) Subgroup means (levels with < 4 studies pooled as "other"), robust CR2 CIs and HTZ Wald p. Variances: '
         'author SD where reported, otherwise imputed with the mean CV (Nakagawa et al. 2023) - imputed variances are not author-reported.', bottom=0.07)


def fig10():
    fig, p = forest('biomass', 'Fig10', C['bio'])
    save(fig, 'Fig10_forest_biomass', 'Fig. 10. Dry biomass (shoot / whole plant, last timepoint), TRAIN. Panels as in Fig. 9.', bottom=0.05)


# ------------------------------------------------------------------ Fig11 publication bias
def fig11():
    pb = pd.read_csv(M / 'publication_bias.csv')
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.2))
    for a, ep, col, letter in [(ax[0, 0], 'yield', C['train'], 'a'), (ax[0, 1], 'biomass', C['bio'], 'b')]:
        f = pd.read_csv(M / f'funnel_{ep}.csv'); r = pb[pb.endpoint == ep].iloc[0]
        se = np.linspace(0, f.sei.max() * 1.05, 50)
        a.fill_betweenx(se, r.REML_study_level_mu - 1.96 * se, r.REML_study_level_mu + 1.96 * se, color='#eee')
        a.scatter(f.yi[f.filled == 0], f.sei[f.filled == 0], s=8, color=col, alpha=0.7)
        a.scatter(f.yi[f.filled == 1], f.sei[f.filled == 1], s=10, facecolor='none', edgecolor=C['red'], label=f'trim-and-fill ({int(r.trimfill_k0)})')
        a.axvline(r.REML_study_level_mu, color='#333', lw=0.7); a.invert_yaxis(); a.set_xlabel('Study lnRR'); a.set_ylabel('SE')
        a.legend(frameon=False, loc='lower right'); panel(a, letter, f'{"Yield" if ep == "yield" else "Biomass"}: funnel (study aggregates)')
    a = ax[1, 0]
    for i, ep in enumerate(['yield', 'biomass']):
        r = pb[pb.endpoint == ep].iloc[0]; prim = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
        vals = [('3-level REML', prim.mu), ('Study-level REML', r.REML_study_level_mu), ('PET (ml)', r.PET_mu), ('PEESE (ml)', r.PEESE_mu), ('Trim-and-fill', r.trimfill_mu)]
        for j, (lab, v) in enumerate(vals):
            a.plot(pct(v), j + i * 0.25, 'o' if ep == 'yield' else 's', color=C['train'] if ep == 'yield' else C['bio'], ms=4,
                   label=('Yield' if ep == 'yield' else 'Biomass') if j == 0 else None)
        a.set_yticks(range(len(vals))); a.set_yticklabels([v[0] for v in vals])
    a.axvline(0, color=C['red'], lw=0.6); a.set_xlabel('Pooled effect (%)'); a.legend(frameon=False); panel(a, 'c', 'Bias-adjusted estimates')
    a = ax[1, 1]; a.axis('off')
    t = pb.set_index('endpoint')
    cells = [[f'{t.loc[e, "ml_egger_p"]:.2f}', f'{t.loc[e, "egger_regtest_p"]:.2f}', f'{t.loc[e, "begg_ranktest_p"]:.2f}', f'{int(t.loc[e, "trimfill_k0"])}',
              f'{t.loc[e, "I2_study_level"]:.0f} %'] for e in ['yield', 'biomass']]
    tab = a.table(cellText=cells, rowLabels=['Yield', 'Biomass'], colLabels=['Multilevel\nEgger p', 'Egger\n(regtest) p', 'Begg\np', 'Trim-fill\nk0', 'I²'],
                  loc='center', cellLoc='center'); tab.auto_set_font_size(False); tab.set_fontsize(6.5); tab.scale(1, 1.6)
    panel(a, 'd', 'Small-study tests')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig11_publication_bias', 'Fig. 11. Small-study effects / publication bias. Funnels of study aggregates; multilevel Egger (lnRR ~ SE, rma.mv, CR2), '
         'regtest/ranktest on study aggregates, PET-PEESE and trim-and-fill. Standard errors partly rest on imputed variances.', bottom=0.11)


# ------------------------------------------------------------------ Fig14 meta summary
def fig14():
    sg = pd.read_csv(M / 'subgroups_CR2.csv')
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.6))
    a = ax[0, 0]; y = 0; yt, yl = [], []
    order = ['TRAIN_primary', 'TRAIN_STRICT', 'TRAIN_SB_vs_S_only', 'TRAIN_author_SD_only', 'TRAIN_all_timepoints', 'TEST', 'TRAIN_plus_TEST']
    for ep, col in [('yield', C['train']), ('biomass', C['bio'])]:
        P = pooled[(pooled.endpoint == ep) & pooled.set.isin(order)].set_index('set')
        for s in order:
            if s not in P.index or not np.isfinite(P.loc[s, 'mu']):
                continue
            r = P.loc[s]
            a.hlines(y, pct(r.pi_lo), pct(r.pi_hi), color=col, lw=0.6); a.hlines(y, pct(r.ci_lo), pct(r.ci_hi), color=col, lw=2.2)
            a.plot(pct(r.mu), y, 'D' if s == 'TRAIN_primary' else ('o' if 'TEST' not in s else 'o'), color=col if 'TEST' not in s else C['test'], ms=4,
                   mfc='white' if 'TEST' in s else None)
            a.text(1.0, y, f'{pct(r.mu):+.0f} % [{pct(r.ci_lo):+.0f}, {pct(r.ci_hi):+.0f}]', transform=a.get_yaxis_transform(), fontsize=5.4, va='center')
            yt.append(y); yl.append(f'{"Y" if ep == "yield" else "B"}: {s.replace("_", " ")} (k={int(r.studies)})'); y -= 1
        y -= 0.6
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=5.3); a.axvline(0, color=C['red'], lw=0.6); a.set_xlim(-60, 250)
    a.set_xlabel('Effect (%); thick = 95 % CI (CR2), thin = 95 % PI'); panel(a, 'a', 'Pooled effects')
    a = ax[0, 1]
    for i, ep in enumerate(['yield', 'biomass']):
        r = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
        parts = np.array([r.tau2_study, r.tau2_within, MEDVI[ep]]); parts = 100 * parts / parts.sum()
        left = 0
        for v, lab, colr in zip(parts, ['between studies', 'within studies', 'sampling'], [C['train'], '#7fb3d5', C['grey']]):
            a.barh(i, v, left=left, color=colr, label=lab if i == 0 else None); a.text(left + v / 2, i, f'{v:.0f} %', ha='center', va='center', fontsize=6)
            left += v
        a.text(101, i, f'I² {r.I2:.0f} %\nτ {np.sqrt(r.tau2_study + r.tau2_within):.2f}', fontsize=5.8, va='center')
    a.set_yticks([0, 1]); a.set_yticklabels(['Yield', 'Biomass']); a.set_xlim(0, 120); a.legend(frameon=False, ncol=3, loc='upper center', bbox_to_anchor=(0.45, -0.18))
    a.set_xlabel('% of total variance'); panel(a, 'b', 'Heterogeneity (TRAIN)')
    a = ax[1, 0]
    g = sg.groupby(['endpoint', 'moderator']).agg(R2=('pseudoR2_tau', 'first'), p=('p_HTZ', 'first')).reset_index()
    lab = {'h_stress_class': 'Stress class', 'h2_dujardin': 'Biostimulant class', 'h_route': 'Route', 'h_system': 'System'}
    mods = list(lab)
    for i, ep in enumerate(['yield', 'biomass']):
        gg = g[g.endpoint == ep].set_index('moderator').reindex(mods)
        yy = np.arange(len(mods)) + 0.2 * (1 - 2 * i)
        a.barh(yy, 100 * gg.R2.fillna(0), 0.4, color=C['train'] if ep == 'yield' else C['bio'], label=ep.title())
        for y_, (m, r) in zip(yy, gg.iterrows()):
            a.text(100 * (0 if np.isnan(r.R2) else r.R2), y_, f' {100 * r.R2:.1f} %, p={r.p:.2f}', va='center', fontsize=5.5)
    a.set_yticks(range(len(mods))); a.set_yticklabels([lab[m] for m in mods]); a.set_xlabel('Pseudo-R² of τ² (%)'); a.legend(frameon=False, loc='lower right')
    a.set_xlim(0, max(6, 100 * g.R2.max() * 1.6))
    panel(a, 'c', 'Explained heterogeneity by moderator')
    a = ax[1, 1]
    gains = [0, 10, 25, 50]
    for ep, col in [('yield', C['train']), ('biomass', C['bio'])]:
        r = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
        sd = np.sqrt(r.tau2_study + r.tau2_within + r.se_CR2 ** 2)
        pr = [100 * (1 - stats.norm.cdf((np.log(1 + g / 100) - r.mu) / sd)) for g in gains]
        a.plot(gains, pr, 'o-', color=col, label=ep.title())
        for g_, p_ in zip(gains, pr):
            a.text(g_, p_ + 2, f'{p_:.0f}', fontsize=5.6, ha='center', color=col)
    a.set_xlabel('Gain threshold (%)'); a.set_ylabel('P(new study effect > threshold) (%)'); a.set_ylim(0, 100); a.legend(frameon=False)
    panel(a, 'd', 'Chance of a gain in a new study')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig14_meta_summary', 'Fig. 14. Meta-analytic summary (descriptive; rma.mv REML with study/contrast random effects and shared-control covariance, '
         'CR2 robust CIs; PI = prediction interval for a new study). TEST and TRAIN+TEST are shown for comparison only. (d) P(gain) from the normal '
         'predictive distribution N(mu, tau²_total + SE²).', bottom=0.10)


# ------------------------------------------------------------------ Fig15 evidence landscape + class x stress matrix
def fig15():
    mat = pd.read_csv(M / 'class_x_stress_matrix.csv'); mat = mat[mat.endpoint == 'yield'].copy()
    # model-based prediction column: mean out-of-fold prediction of the selected category-A model (if CV results exist)
    try:
        sel = pd.read_csv(RES / 'v5_selected_models.csv'); a = sel[(sel.endpoint == 'yield') & (sel.category == 'A')].selected.iloc[0]
        oof = pd.concat([pd.read_parquet(RES / f'v5_cv_oof_yield_{s}.parquet') for s in (11, 22, 33)])
        oof = oof[oof.model == a].groupby('contrast_id').pred.mean()
        t = ty.assign(oof=ty.contrast_id.map(oof))
        cm = t.groupby(['h2_dujardin', 'h_stress_class']).oof.mean().rename('cv_oof_prediction_lnRR').reset_index()
        mat = mat.merge(cm, left_on=['biostimulant_class', 'stress'], right_on=['h2_dujardin', 'h_stress_class'], how='left').drop(columns=['h2_dujardin', 'h_stress_class'])
        mat['cv_oof_model'] = a
    except Exception as ex:
        mat['cv_oof_prediction_lnRR'] = np.nan; mat['cv_oof_model'] = f'not available ({ex.__class__.__name__})'
    for c in ['mu', 'ci_lo', 'ci_hi', 'pi_lo', 'pi_hi', 'median_study_mean', 'cv_oof_prediction_lnRR']:
        mat[c + '_pct'] = pct(mat[c])
    mat['note'] = np.where(mat.estimate_type == 'POOLED_RMA_MV_CR2', 'descriptive pooled mean (>= 3 studies): 95 % CI = uncertainty of the mean; '
                           '95 % PI = range expected for a NEW study (prediction)', 'descriptive only (< 3 studies): median of study means, no interval')
    mat.to_csv(RES / 'class_x_stress_matrix_yield_V5.csv', index=False)
    with pd.ExcelWriter(RES / 'class_x_stress_matrix_yield_V5.xlsx') as w:
        mat.to_excel(w, 'matrix', index=False)
        pd.DataFrame({'column': ['studies', 'k', 'mu_pct / ci_lo_pct / ci_hi_pct', 'pi_lo_pct / pi_hi_pct', 'median_study_mean_pct', 'cv_oof_prediction_lnRR_pct', 'estimate_type'],
                      'meaning': ['independent studies in the cell (TRAIN)', 'contrasts', 'DESCRIPTIVE pooled effect and 95 % CR2 CI (rma.mv, >= 3 studies)',
                                  'PREDICTION interval for a new study in this cell', 'descriptive median of study means (all cells)',
                                  'mean out-of-fold PREDICTION of the selected a-priori model (cluster CV) for the TRAIN rows of the cell',
                                  'POOLED_RMA_MV_CR2 or DESCRIPTIVE_MEDIAN_OF_STUDY_MEANS']}).to_excel(w, 'legend', index=False)
    rows = mat.groupby('stress').studies.sum().sort_values(ascending=False).index.tolist()
    cols = mat.groupby('biostimulant_class').studies.sum().sort_values(ascending=False).index.tolist()[:10]
    nmat = mat.pivot_table(index='stress', columns='biostimulant_class', values='studies', aggfunc='sum').reindex(index=rows, columns=cols)
    fig = plt.figure(figsize=(W, 10.5))
    a = fig.add_axes([0.19, 0.79, 0.79, 0.18])
    cm = LinearSegmentedColormap.from_list('b', ['#f4f7fa', '#2a6f97', '#163e57'])
    a.imshow(nmat.values, cmap=cm, vmin=0, vmax=max(8, np.nanmax(nmat.values)), aspect='auto')
    for i in range(nmat.shape[0]):
        for j in range(nmat.shape[1]):
            v = nmat.values[i, j]
            if np.isfinite(v):
                a.text(j, i, int(v), ha='center', va='center', fontsize=5.6, color='white' if v > 6 else '#222')
    tot = ty.groupby('h_stress_class').study_id.nunique()
    a.set_yticks(range(len(rows))); a.set_yticklabels([f'{STRESS_LABEL.get(r, r)} ({tot.get(r, 0)})' for r in rows], fontsize=5.8)
    a.set_xticks(range(len(cols))); a.set_xticklabels([])
    a.set_title('a  Yield TRAIN: independent studies per cell (columns as in b)', loc='left', fontsize=8.5, fontweight='bold')
    b = fig.add_axes([0.19, 0.565, 0.79, 0.20])
    emat = mat.pivot_table(index='stress', columns='biostimulant_class', values='mu', aggfunc='first').reindex(index=rows, columns=cols)
    dmat = mat.pivot_table(index='stress', columns='biostimulant_class', values='median_study_mean', aggfunc='first').reindex(index=rows, columns=cols)
    lo = mat.pivot_table(index='stress', columns='biostimulant_class', values='ci_lo', aggfunc='first').reindex(index=rows, columns=cols)
    hi = mat.pivot_table(index='stress', columns='biostimulant_class', values='ci_hi', aggfunc='first').reindex(index=rows, columns=cols)
    show = emat.where(emat.notna(), dmat)
    b.imshow(show.values, cmap='RdBu', norm=TwoSlopeNorm(vmin=-0.6, vcenter=0, vmax=1.2), aspect='auto')
    for i in range(show.shape[0]):
        for j in range(show.shape[1]):
            if np.isfinite(emat.values[i, j]):
                b.text(j, i, f'{pct(emat.values[i, j]):+.0f}%\n[{pct(lo.values[i, j]):+.0f},{pct(hi.values[i, j]):+.0f}]', ha='center', va='center',
                       fontsize=4.6, fontweight='bold', color='white' if abs(emat.values[i, j]) > 0.7 else '#111')
            elif np.isfinite(dmat.values[i, j]):
                b.text(j, i, f'({pct(dmat.values[i, j]):+.0f}%)', ha='center', va='center', fontsize=4.8, color='white' if abs(dmat.values[i, j]) > 0.7 else '#555', style='italic')
    b.set_yticks(range(len(rows))); b.set_yticklabels([STRESS_LABEL.get(r, r) for r in rows], fontsize=5.8)
    b.set_xticks(range(len(cols))); b.set_xticklabels([CLASS_LABEL.get(c, c) for c in cols], rotation=30, ha='right', fontsize=5.6)
    b.set_title('b  Yield effect (%): bold = pooled mean [95 % CI]; italics = descriptive median (< 3 studies)', loc='left', fontsize=8.5, fontweight='bold')
    # c: prediction intervals for the cells with >= 3 studies
    c = fig.add_axes([0.33, 0.255, 0.38, 0.21])
    pm = mat[mat.estimate_type == 'POOLED_RMA_MV_CR2'].sort_values('mu').reset_index(drop=True)
    for i, r in pm.iterrows():
        c.hlines(i, pct(r.pi_lo), min(pct(r.pi_hi), 400), color=C['grey'], lw=3)
        c.hlines(i, pct(r.ci_lo), pct(r.ci_hi), color=C['train'], lw=1.6); c.plot(pct(r.mu), i, 'o', color=C['train'], ms=3)
        if np.isfinite(r.cv_oof_prediction_lnRR):
            c.plot(pct(r.cv_oof_prediction_lnRR), i, 'x', color=C['test'], ms=4)
    c.set_yticks(range(len(pm))); c.set_yticklabels([f'{STRESS_LABEL.get(r.stress, r.stress)} × {CLASS_LABEL.get(r.biostimulant_class, r.biostimulant_class)} ({r.studies})'
                                                      for r in pm.itertuples()], fontsize=5.2)
    c.axvline(0, color=C['red'], lw=0.6); c.set_xlabel('Yield effect (%)'); c.set_xlim(-80, 400)
    c.set_title('c  Mean [CI] (blue) vs new-study PI (grey), model (×)', loc='left', fontsize=7.5, fontweight='bold')
    d = fig.add_axes([0.80, 0.255, 0.18, 0.21])
    yr_tr = pd.to_numeric(ty.groupby('study_id').year.first(), errors='coerce'); yr_te = pd.to_numeric(ey.groupby('study_id').year.first(), errors='coerce')
    bins = np.arange(2005, 2028)
    d.hist(yr_tr.dropna(), bins=bins, color=C['train'], label=f'TRAIN ({len(yr_tr)})'); d.hist(yr_te.dropna(), bins=bins, color=C['test'], label=f'TEST ({len(yr_te)})')
    d.set_xlabel('Publication year'); d.set_ylabel('Yield studies'); d.legend(frameon=False); d.set_title('d  Years', loc='left', fontsize=8.5, fontweight='bold')
    e = fig.add_axes([0.19, 0.04, 0.30, 0.15])
    sy = pd.concat([ty.assign(r='TRAIN'), ey.assign(r='TEST')]).groupby(['r', 'h_system']).study_id.nunique().unstack(0).fillna(0)
    sy = sy.loc[sy.sum(1).sort_values().index]
    e.barh(range(len(sy)), sy['TRAIN'], color=C['train'], label='TRAIN'); e.barh(range(len(sy)), sy['TEST'], left=sy['TRAIN'], color=C['test'], label='TEST')
    e.set_yticks(range(len(sy))); e.set_yticklabels([s.title() for s in sy.index], fontsize=6); e.set_xlabel('Yield studies'); e.legend(frameon=False)
    e.set_title('e  Cultivation system', loc='left', fontsize=8.5, fontweight='bold')
    f = fig.add_axes([0.66, 0.04, 0.32, 0.15])
    co = pd.concat([ty, ey]).groupby('h3_country').study_id.nunique().sort_values(ascending=False)
    top = co.drop('UNSPECIFIED', errors='ignore').head(9)
    vals = list(top.values) + [co.drop(list(top.index) + ['UNSPECIFIED'], errors='ignore').sum(), co.get('UNSPECIFIED', 0)]
    labs = [s.title() for s in top.index] + ['other countries', 'not reported']
    f.barh(range(len(vals))[::-1], vals, color=[C['train']] * len(top) + [C['grey'], C['grey']])
    f.set_yticks(range(len(vals))[::-1]); f.set_yticklabels(labs, fontsize=5.8); f.set_xlabel('Yield studies (TRAIN+TEST)')
    f.set_title('f  Countries', loc='left', fontsize=8.5, fontweight='bold')
    save(fig, 'Fig15_evidence_landscape', 'Fig. 15. Evidence landscape for fruit yield (TRAIN unless stated). (a) Independent studies per stress class × biostimulant class '
         '(du Jardin v2 classes; a study testing two classes counts in both). (b) Yield effect: bold = DESCRIPTIVE pooled mean with 95 % CR2 CI (rma.mv, ≥ 3 studies); '
         'grey italics in brackets = descriptive median of study means (< 3 studies, no interval). (c) For cells with ≥ 3 studies the grey bar is the 95 % prediction '
         'interval for a NEW study and the cross is the mean out-of-fold PREDICTION of the selected a-priori model; descriptive means and predictions are different '
         'quantities. Full table: class_x_stress_matrix_yield_V5.csv/.xlsx.', bottom=0.0)


# ------------------------------------------------------------------ Fig16 PRISMA
def fig16():
    fl = pd.read_csv(RES / 'build_flow_v5.csv')
    g = lambda role, t, step: fl[(fl.role == role) & (fl.table == t) & fl.step.str.startswith(step)].iloc[0]
    fig, a = plt.subplots(figsize=(W, 4.6)); a.axis('off'); a.set_xlim(0, 10); a.set_ylim(1.4, 9.8); fig.subplots_adjust(0.01, 0.01, 0.99, 0.99)

    def box(x, y, w, h, txt, col='#eef3f7', ec=C['train']):
        a.add_patch(plt.Rectangle((x, y), w, h, facecolor=col, edgecolor=ec, lw=0.8)); a.text(x + w / 2, y + h / 2, txt, ha='center', va='center', fontsize=6.2, wrap=True)

    def arr(x1, y1, x2, y2):
        a.annotate('', (x2, y2), (x1, y1), arrowprops=dict(arrowstyle='->', lw=0.7, color='#444'))
    hist = '#f3f3f3'
    box(0.3, 8.6, 4.2, 1.1, 'Records identified (databases, 2000-2023): 39 627\n(historical upstream counts, unchanged in V5)', hist, '#888')
    box(0.3, 7.1, 4.2, 1.1, 'After de-duplication 12 141 → title/abstract screened 7 331\n→ full texts assessed 1 732 → 1 192 → 766', hist, '#888')
    box(0.3, 5.6, 4.2, 1.1, 'Class-A database (TRAIN_DEV, frozen 2026-11-13):\n399 studies, 8 322 candidate contrasts')
    yA, bA = g('TRAIN', 'yield', '08'), g('TRAIN', 'biomass', '08')
    box(0.3, 3.6, 2.0, 1.5, f'TRAIN yield V5\n{yA.contrasts} contrasts\n{yA.studies} studies\n{yA.clusters} dependency clusters')
    box(2.5, 3.6, 2.0, 1.5, f'TRAIN dry biomass V5\n{bA.contrasts} contrasts\n{bA.studies} studies\n{bA.clusters} clusters', '#eef7f1', C['bio'])
    box(5.5, 8.6, 4.2, 1.1, 'TEST corpus 2024-2026 (first online ≥ 2024):\n108 records → 80 in scope → 58 closed (historical counts)', hist, '#888')
    box(5.5, 5.6, 4.2, 1.1, 'TEST database (EXTERNAL_TEST, frozen 2026-11-18):\n57 studies with contrasts, 2 001 candidate contrasts')
    yT, bT = g('TEST', 'yield', '08'), g('TEST', 'biomass', '08')
    box(5.5, 3.6, 2.0, 1.5, f'TEST yield V5\n{yT.contrasts} contrasts\n{yT.studies} studies', '#fdf1e8', C['test'])
    box(7.7, 3.6, 2.0, 1.5, f'TEST dry biomass V5\n{bT.contrasts} contrasts\n{bT.studies} studies', '#fdf1e8', C['test'])
    for x in (2.4,):
        arr(x, 8.6, x, 8.2); arr(x, 7.1, x, 6.7); arr(1.3, 5.6, 1.3, 5.1); arr(3.5, 5.6, 3.5, 5.1)
    arr(7.6, 8.6, 7.6, 6.7); arr(6.5, 5.6, 6.5, 5.1); arr(8.7, 5.6, 8.7, 5.1)
    ex = fl[(fl.role == 'TRAIN') & (fl.table == 'yield')]
    txt = 'Yield exclusions (TRAIN): ' + '; '.join(f'{r.step[3:]} → {r.contrasts}' for r in ex.itertuples() if r.step[:2] in ('05', '06', '07'))
    box(0.3, 1.6, 9.4, 1.4, txt + '\nBiomass: shoot/whole-plant dry mass, last timepoint per group, no box-plot centres. Same rules for TEST.'
        '\n0 study_id, 0 dependency-cluster, 0 DOI and 0 title overlaps between TRAIN and TEST.', '#fafafa', '#888')
    save(fig, 'Fig16_PRISMA_flow', 'Fig. 16. Flow of studies and contrasts. Grey boxes: upstream screening counts from the earlier PRISMA record (not re-run in V5). '
         'Coloured boxes: V5 TRAIN and TEST tables built with identical definitions and selection rules.', bottom=0.06)


# ------------------------------------------------------------------ Fig19 interactions
def fig19():
    ip = pd.read_csv(M / 'interactions_pooled.csv')
    fig, ax = plt.subplots(1, 3, figsize=(W, 3.0))
    a = ax[0]; i = 0; yt, yl = [], []
    for ep, col in [('yield', C['train']), ('dry_biomass', C['bio'])]:
        for role in ['train', 'test']:
            f = M / f'interaction_by_study_{ep}_{role}_SxB.csv'
            if not f.exists():
                continue
            s = pd.read_csv(f); r = ip[(ip.endpoint == ep) & (ip.role == role) & (ip.type == 'SxB')].iloc[0]
            a.scatter(s.effect.clip(-1.5, 1.5), np.full(len(s), i) + np.random.default_rng(0).uniform(-0.15, 0.15, len(s)), s=5, color=col if role == 'train' else C['test'], alpha=0.5)
            a.errorbar(r.mean_of_study_means, i, xerr=[[r.mean_of_study_means - r.ci_lo], [r.ci_hi - r.mean_of_study_means]] if np.isfinite(r.ci_lo) else None,
                       fmt='D', color='#222', ms=4)
            yt.append(i); yl.append(f'{"Yield" if ep == "yield" else "Biomass"} {role.upper()} ({int(r.studies)})'); i += 1
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=6); a.axvline(0, color=C['red'], lw=0.6); a.set_xlabel('S×B = ln(SB/S) − ln(B/C)')
    panel(a, 'a', 'Stress × biostimulant')
    a = ax[1]
    cnt = []
    for ep in ['yield', 'dry_biomass']:
        x = pd.read_parquet(DATA / f'train_{ep}_interactions.parquet'); z = x[x.contrast_type == 'AxB']
        se = np.sqrt(pd.to_numeric(z.var_effect, errors='coerce'))
        lo, hi = z.effect - 1.96 * se, z.effect + 1.96 * se
        cl = np.where(se.isna(), 'no variance', np.where(lo > 0, 'synergy', np.where(hi < 0, 'antagonism', 'additive')))
        cnt.append(pd.Series(cl).value_counts().rename(ep))
    cnt = pd.concat(cnt, axis=1).fillna(0)
    cnt.T.plot.bar(stacked=True, ax=a, color={'synergy': C['bio'], 'additive': C['grey'], 'antagonism': C['red'], 'no variance': '#eeeeee'}, width=0.6)
    a.set_xticklabels(['Yield', 'Biomass'], rotation=0); a.set_ylabel('A×B contrasts (TRAIN)'); a.legend(frameon=False, fontsize=5.6)
    panel(a, 'b', 'A×B: classification')
    a = ax[2]; i = 0
    for ep, col in [('yield', C['train']), ('dry_biomass', C['bio'])]:
        f = M / f'interaction_by_study_{ep}_train_AxB.csv'
        if not f.exists():
            continue
        s = pd.read_csv(f).sort_values('effect'); r = ip[(ip.endpoint == ep) & (ip.role == 'train') & (ip.type == 'AxB')].iloc[0]
        a.scatter(s.effect, np.arange(len(s)) + i, s=6, color=col)
        a.errorbar(r.mean_of_study_means, i + len(s) + 0.8, xerr=[[r.mean_of_study_means - r.ci_lo], [r.ci_hi - r.mean_of_study_means]] if np.isfinite(r.ci_lo) else None,
                   fmt='D', color='#222', ms=4)
        a.text(r.mean_of_study_means, i + len(s) + 2.2, f'{"Yield" if ep == "yield" else "Biomass"}: {pct(r.mean_of_study_means):+.0f} % ({int(r.studies)} st.)', fontsize=5.6, ha='center')
        i += len(s) + 4
    a.axvline(0, color=C['red'], lw=0.6); a.set_yticks([]); a.set_xlabel('A×B = ln(AB) − ln(A) − ln(B) + ln(C)'); panel(a, 'c', 'A×B by study')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig19_interactions', 'Fig. 19. Interactions (descriptive). (a) S×B by study (dots) and mean of study means with t-based 95 % CI (diamond). '
         '(b) A×B contrasts classified by their 95 % CI (author/derived variance only). (c) A×B study means. Size fractions of D_8a246bc169c4b812 '
         'were summed to total yield before computing A×B.', bottom=0.2)


# ------------------------------------------------------------------ Fig21 database
def fig21():
    def counts(db):
        c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        q = lambda t: c.execute(f'select count(*) from "{t}"').fetchone()[0]
        tabs = ['files', 'studies', 'experiments', 'arms', 'measurements', 'contrast_candidates', 'moderators', 'risk_of_bias', 'covariance', 'wf_source_receipts']
        out = {t: q(t) for t in tabs if c.execute("select count(*) from sqlite_master where name=?", (t,)).fetchone()[0]}
        ep = pd.read_sql('select endpoint, count(distinct study_id) s, count(*) n from contrast_candidates group by endpoint', c)
        ct = pd.read_sql('select endpoint, contrast_type, count(distinct study_id) s from contrast_candidates group by 1,2', c)
        rob = pd.read_sql('select domain, judgement, count(*) n from risk_of_bias group by 1,2', c)
        va = pd.read_sql('select var_available, count(*) n from contrast_candidates group by 1', c)
        c.close(); return out, ep, ct, rob, va
    tr = counts(TRAIN_FREEZE / 'TFM_DATABASE_CLASS_A_FINAL.sqlite'); te = counts(TEST_FREEZE / 'TFM_DATABASE_CLASS_A_FINAL.sqlite')
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.6))
    a = ax[0, 0]
    t = pd.DataFrame({'TRAIN_DEV': tr[0], 'EXTERNAL_TEST': te[0]}).fillna(0)
    t.plot.barh(ax=a, color=[C['train'], C['test']], width=0.75, logx=True)
    for i, (k, r) in enumerate(t.iterrows()):
        a.text(r.max() * 1.1, i, f'{int(r.TRAIN_DEV):,} / {int(r.EXTERNAL_TEST):,}', va='center', fontsize=5.4)
    a.set_xlabel('Rows (log)'); a.legend(frameon=False, fontsize=5.8); panel(a, 'a', 'Relational database: tables and rows')
    a = ax[0, 1]
    e = tr[1].set_index('endpoint').s.sort_values().tail(10)
    a.barh(e.index, e.values, color=C['train']); a.set_xlabel('Studies (TRAIN_DEV)'); panel(a, 'b', 'Endpoints')
    a = ax[1, 0]
    h = tr[2].pivot_table(index='endpoint', columns='contrast_type', values='s').fillna(0)
    h = h.loc[h.sum(1).sort_values(ascending=False).index[:8]]
    a.imshow(h.values, cmap=LinearSegmentedColormap.from_list('b', ['#f4f7fa', '#2a6f97']), aspect='auto')
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            a.text(j, i, int(h.values[i, j]), ha='center', va='center', fontsize=5.4)
    a.set_yticks(range(len(h))); a.set_yticklabels(h.index, fontsize=5.6); a.set_xticks(range(h.shape[1])); a.set_xticklabels(h.columns, rotation=45, ha='right', fontsize=5.6)
    panel(a, 'c', 'Endpoint × contrast type (studies, TRAIN)')
    a = ax[1, 1]
    r = tr[3].pivot_table(index='domain', columns='judgement', values='n').fillna(0)
    r = 100 * r.div(r.sum(1), axis=0)
    order = [c for c in ['low', 'some_concerns', 'unclear', 'high'] if c in r.columns] + [c for c in r.columns if c not in ('low', 'some_concerns', 'unclear', 'high')]
    rc = {'low': '#2e8b57', 'some_concerns': '#f0b35a', 'unclear': '#c9ced6', 'high': '#c0392b'}
    r[order].plot.barh(stacked=True, ax=a, color=[rc.get(c, '#888') for c in order], width=0.7); a.set_xlabel('% of experiments'); a.set_ylabel('')
    a.legend(frameon=False, fontsize=5.4, ncol=4, loc='upper center', bbox_to_anchor=(0.4, -0.12))
    panel(a, 'd', 'Risk of bias (TRAIN)')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig21_database', 'Fig. 21. Relational databases behind the V5 tables (read-only queries of the frozen TRAIN_DEV and EXTERNAL_TEST SQLite files).', bottom=0.08)


if __name__ == '__main__':
    import sys
    for f in (sys.argv[1:] or ['fig1', 'fig4', 'fig8', 'fig9', 'fig10', 'fig11', 'fig14', 'fig15', 'fig16', 'fig19', 'fig21']):
        globals()[f]()
