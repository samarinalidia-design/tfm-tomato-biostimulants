"""V5 figures that depend on models / CV / TEST: Fig2, Fig3, Fig5, Fig6, Fig7, Fig12, Fig13, Fig17, Fig18, Fig20 and Table1/Table2."""
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from v5_style import *

M = RES / 'meta'; X = RES / 'extra'; T = RES / 'test'
OLD = V5.parent / 'results'
cvS = pd.read_csv(RES / 'v5_cv_summary.csv'); cvR = pd.read_csv(RES / 'v5_cv_metrics_by_seed.csv')
sel = pd.read_csv(RES / 'v5_selected_models.csv')
tm = pd.read_csv(T / 'v5_test_metrics_POST_HOC_TEST_REUSE.csv'); tp = pd.read_csv(T / 'v5_test_predictions_POST_HOC_TEST_REUSE.csv')
tv = pd.read_csv(T / 'v5_test_verdict_POST_HOC_TEST_REUSE.csv')
pooled = pd.read_csv(M / 'pooled_effects.csv')
MEDVI = {'yield': default(load('yield')).var_lnrr_imp.median(), 'biomass': default(load('dry_biomass')).var_lnrr_imp.median()}
spec = json.load(open(V5 / 'freeze/MODEL_FREEZE_V5.json'))
ORDER = ['BASELINE_mean', 'MR0', 'RIDGE_REF', 'RF_REF', 'RIDGE_V3TE', 'RF_V3TETF', 'STACK_A_REF', 'STACK_A_V3', 'LSTACK_A',
         'MR2mt', 'STACK_B_MR0', 'STACK_B_REF', 'STACK_B_V3', 'LSTACK_B']
SEL = {(r.endpoint, r.category): r.selected for r in sel.itertuples()}


def cv_bars(a, ep, metric='RMSE', letter='a'):
    s = cvS[cvS.endpoint == ep].set_index('model').reindex(ORDER).dropna(subset=['RMSE'])
    cols = [C['base'] if m in ('BASELINE_mean',) else (C['A'] if s.loc[m, 'category'] == 'A' else C['B']) for m in s.index]
    y = np.arange(len(s))[::-1]
    a.barh(y, s[metric], xerr=s[metric + '_sd'] if metric + '_sd' in s else None, color=cols, error_kw=dict(lw=0.6))
    base = s.loc['BASELINE_mean', metric]; a.axvline(base, color='#555', ls='--', lw=0.6)
    for yy, m in zip(y, s.index):
        star = ' ◀ selected' if m in (SEL.get((ep, 'A')), SEL.get((ep, 'B'))) else ''
        a.text(s.loc[m, metric], yy, f' {s.loc[m, metric]:.3f} ({s.loc[m, "d_vs_mean_pct"]:+.1f} %){star}', va='center', fontsize=5.2)
    a.set_yticks(y); a.set_yticklabels([MODEL_LABEL[m] for m in s.index], fontsize=5.6)
    lo = s[metric].min() * 0.85; a.set_xlim(lo, s[metric].max() * 1.12)
    a.set_xlabel(f'CV {metric} (lnRR), mean ± SD over 3 seeds')
    panel(a, letter, f'{"Yield" if ep == "yield" else "Biomass"}: nested cluster CV')


def fig2():
    fig, ax = plt.subplots(2, 2, figsize=(W, 6.2))
    cv_bars(ax[0, 0], 'yield', letter='a'); cv_bars(ax[0, 1], 'biomass', letter='b')
    a = ax[1, 0]
    for i, ep in enumerate(['yield', 'biomass']):
        s = cvS[cvS.endpoint == ep].set_index('model').reindex(ORDER).dropna(subset=['R2'])
        a.scatter(s.R2, np.arange(len(s))[::-1] + 0.2 * (1 - 2 * i), color=C['train'] if ep == 'yield' else C['bio'], s=12, label=ep.title())
        a.set_yticks(np.arange(len(s))[::-1]); a.set_yticklabels([MODEL_LABEL[m] for m in s.index], fontsize=5.6)
    a.axvline(0, color='#555', lw=0.6); a.set_xlabel('CV R² (1 − SSE/SST)'); a.legend(frameon=False); panel(a, 'c', 'Explained variance of new-cluster effects')
    a = ax[1, 1]
    for i, ep in enumerate(['yield', 'biomass']):
        r = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
        parts = np.array([r.tau2_study, r.tau2_within, MEDVI[ep]]); parts = parts / parts.sum()
        left = 0
        for v, lab, colr in zip(parts, ['between studies', 'within studies', 'sampling'], [C['train'], '#7fb3d5', C['grey']]):
            a.barh(i, 100 * v, left=left, color=colr, label=lab if i == 0 else None); a.text(left + 50 * v, i, f'{100 * v:.0f}%', ha='center', va='center', fontsize=6); left += 100 * v
        best = cvS[(cvS.endpoint == ep) & (cvS.category == 'A')].RMSE.min()
        a.text(101, i, f'best A\nRMSE\n{best:.3f}', fontsize=5.4, va='center')
    a.set_yticks([0, 1]); a.set_yticklabels(['Yield', 'Biomass']); a.set_xlim(0, 135); a.set_xlabel('% of variance of lnRR')
    a.legend(frameon=False, ncol=3, fontsize=5.6, loc='upper center', bbox_to_anchor=(0.4, -0.16)); panel(a, 'd', 'Where the error comes from')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig2_model_performance', 'Fig. 2. Model selection on TRAIN only: nested cross-validation (outer 5 folds × 3 seeds, inner 3 folds), both grouped by '
         'dependency_cluster_id. Blue = a-priori models (design features only); purple = conditional models that need the observed stress effect S_vs_C '
         '(meta-regression moderator, not an ML feature). Selection rule fixed in advance: lowest mean RMSE per category, simpler model if within 1 %. '
         '(d) Between-study variance dominates; it is not explained by the reported design descriptors.', bottom=0.1)


def fig3():
    fig, ax = plt.subplots(1, 3, figsize=(W, 3.0))
    for a, ep, letter in [(ax[0], 'yield', 'a'), (ax[1], 'biomass', 'b')]:
        s = cvS[cvS.endpoint == ep]
        for r in s.itertuples():
            col = C['base'] if r.model == 'BASELINE_mean' else (C['A'] if r.category == 'A' else C['B'])
            a.scatter(r.PI_width / 2, r.coverage95, color=col, s=16)
            if r.model in (SEL.get((ep, 'A')), SEL.get((ep, 'B')), 'BASELINE_mean', 'MR0'):
                a.annotate(MODEL_LABEL[r.model], (r.PI_width / 2, r.coverage95), fontsize=5, xytext=(3, 2), textcoords='offset points')
        a.axhline(0.95, color='#555', ls='--', lw=0.6); a.set_xlabel('Mean 95 % half-width (lnRR)'); a.set_ylabel('CV coverage')
        panel(a, letter, f'{"Yield" if ep == "yield" else "Biomass"}: intervals in CV')
    a = ax[2]; y = 0; yt, yl = [], []
    for ep, col in [('yield', C['train']), ('biomass', C['bio'])]:
        r = pooled[(pooled.endpoint == ep) & (pooled.set == 'TRAIN_primary')].iloc[0]
        a.hlines(y, r.ci_lo, r.ci_hi, color=col, lw=3); a.hlines(y - 0.3, r.pi_lo, r.pi_hi, color=col, lw=1)
        a.plot(r.mu, y, 'D', color=col, ms=4); yt += [y, y - 0.3]; yl += [f'{ep.title()}: 95 % CI of mean', f'{ep.title()}: 95 % PI new study']; y -= 1
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=5.6); a.axvline(0, color=C['red'], lw=0.6); a.set_xlabel('lnRR'); panel(a, 'c', 'Meta: CI vs PI')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig3_uncertainty', 'Fig. 3. Uncertainty. (a, b) 95 % interval coverage against half-width in nested cluster CV (ML: quantile of inner out-of-fold '
         'residuals; meta-models: model-based; equal stacks: mean member half-width; learned stacks: inner out-of-fold residuals). (c) The CI of the pooled '
         'mean is narrow, the prediction interval for a new study is wide: the average effect is well estimated, the effect in a new study is not.', bottom=0.2)


def test_fig(ep, name, num):
    te = tp[(tp.endpoint == ep)]
    a_m, b_m = SEL[(ep, 'A')], SEL.get((ep, 'B'))
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.8))
    a = ax[0, 0]
    d = te[te.model == a_m].copy(); st = d.groupby('study_id').y.median().sort_values().index.tolist()
    d['xi'] = d.study_id.map({s: i for i, s in enumerate(st)}) + np.random.default_rng(0).uniform(-0.25, 0.25, len(d))
    out = (d.y < d.lo) | (d.y > d.hi)
    a.scatter(d.xi[~out], d.y[~out], s=8, color=C['test'], alpha=0.7, label='TEST contrast (covered)')
    a.scatter(d.xi[out], d.y[out], s=12, marker='D', color=C['red'], label='outside 95 % interval')
    a.axhspan(d.lo.mean(), d.hi.mean(), color=C['train'], alpha=0.12, label=f'{MODEL_LABEL[a_m]} ±{(d.hi - d.lo).mean() / 2:.2f}')
    a.axhline(d.pred.mean(), color=C['train'], lw=1); a.axhline(0, color='#555', lw=0.5)
    a.set_xticks(range(len(st))); a.set_xticklabels(st, rotation=90, fontsize=4.6 if len(st) < 20 else 3.4); a.set_ylabel('Observed lnRR'); a.legend(frameon=False, fontsize=5.3)
    panel(a, 'a', f'TEST contrasts ({d.study_id.nunique()} studies, {len(d)} contrasts)')
    a = ax[0, 1]
    ms = [m for m in ['BASELINE_mean', 'MR0', 'RIDGE_REF', 'RF_V3TETF', 'LSTACK_A', a_m, 'MR2mt', 'STACK_B_MR0', 'LSTACK_B', b_m] if m]
    ms = list(dict.fromkeys(ms))
    r = tm[(tm.endpoint == ep)].set_index('model').reindex(ms)
    y = np.arange(len(ms))[::-1]
    a.barh(y + 0.18, r.RMSE_CV, 0.36, color=C['train'], label='TRAIN nested CV')
    a.barh(y - 0.18, r.RMSE, 0.36, color=C['test'], xerr=[r.RMSE - r.RMSE_ci_lo, r.RMSE_ci_hi - r.RMSE], error_kw=dict(lw=0.5), label='TEST (95 % cluster bootstrap)')
    a.set_yticks(y); a.set_yticklabels([MODEL_LABEL[m] + (' ◀' if m in (a_m, b_m) else '') for m in ms], fontsize=5.5)
    a.set_xlabel('RMSE (lnRR)'); a.legend(frameon=False, fontsize=5.5, loc='upper center', bbox_to_anchor=(0.5, -0.13), ncol=2); panel(a, 'b', 'Point accuracy: CV vs TEST')
    a = ax[1, 0]
    a.barh(y + 0.18, r.coverage_CV, 0.36, color=C['train']); a.barh(y - 0.18, r.coverage95, 0.36, color=C['test'])
    a.axvline(0.95, color='#555', ls='--', lw=0.6); a.axvline(0.90, color=C['red'], ls=':', lw=0.6)
    a.set_yticks(y); a.set_yticklabels([MODEL_LABEL[m] for m in ms], fontsize=5.5); a.set_xlim(0.5, 1.02); a.set_xlabel('95 % interval coverage')
    v = tv[tv.endpoint == ep].iloc[0]
    a.text(0.0, -0.25, f'H1 point < mean: {"pass" if v.H1_point_better_than_mean else "fail"} | H2 transfer: {"pass" if v.H2_transfer else "fail"} | '
           f'H3 coverage ≥ 0.90: {"pass" if v.H3_coverage else "fail"} → {v.verdict}', fontsize=5.6, fontweight='bold', transform=a.transAxes)
    panel(a, 'c', 'Coverage: CV vs TEST')
    a = ax[1, 1]; yy = 0
    P = pooled[pooled.endpoint == ep].set_index('set')
    for s, col in [('TRAIN_primary', C['train']), ('TEST', C['test']), ('TRAIN_plus_TEST', '#555'), ('TEST_minus_TRAIN', C['red'])]:
        if s not in P.index:
            continue
        q = P.loc[s]
        if s != 'TEST_minus_TRAIN':
            a.hlines(yy, pct(q.pi_lo), pct(q.pi_hi), color=col, lw=0.7)
        a.hlines(yy, pct(q.ci_lo), pct(q.ci_hi), color=col, lw=2.5); a.plot(pct(q.mu), yy, 'D', color=col, ms=4)
        lab = s.replace('_', ' ') + (f' (k={int(q.studies)})' if s != 'TEST_minus_TRAIN' else f' (p={q.typical_vi:.2f})')
        a.text(1.0, yy, f'{pct(q.mu):+.0f} % [{pct(q.ci_lo):+.0f}, {pct(q.ci_hi):+.0f}]', transform=a.get_yaxis_transform(), fontsize=5.4, va='center')
        a.text(-0.02, yy, lab, transform=a.get_yaxis_transform(), ha='right', fontsize=5.4, va='center'); yy -= 1
    a.set_yticks([]); a.axvline(0, color='#555', lw=0.5); a.set_xlim(-60, 250); a.set_xlabel('Pooled effect (%), CR2 95 % CI; thin = PI')
    panel(a, 'd', 'Pooled effect: TRAIN vs TEST')
    fig.tight_layout(rect=(0.04, 0, 1, 1))
    save(fig, name, f'Fig. {num}. {"Fruit yield" if ep == "yield" else "Dry biomass"}: frozen V5 pipeline on the 2024-2026 TEST set - POST_HOC_TEST_REUSE '
         '(this TEST corpus was used in earlier versions; this is a re-use, not a first blind test). Models, hyper-parameters, stack weights and interval rules were '
         f'frozen on TRAIN (MODEL_FREEZE_V5.json) before TEST was read. Selected a-priori model: {MODEL_LABEL[a_m]}; conditional models (purple in Fig. 2) need '
         'the observed S_vs_C of each TEST study and are shown separately.', bottom=0.1)


def fig5():
    test_fig('yield', 'Fig5_TRAIN_vs_TEST', 5)


def fig7():
    test_fig('biomass', 'Fig7_biomass_TEST', 7)


def fig6():
    b = default(load('dry_biomass')); ball = load('dry_biomass')
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.6))
    a = ax[0, 0]
    t = ball[ball.is_boxplot == 0].groupby(['organ_scope', 'is_last_timepoint']).size().unstack().fillna(0)
    t.plot.barh(stacked=True, ax=a, color=[C['grey'], C['bio']], width=0.6); a.legend(['earlier timepoints (sensitivity)', 'last timepoint (default)'], frameon=False, fontsize=5.6)
    a.set_xlabel('Contrasts (TRAIN)'); panel(a, 'a', f'Biomass data: {len(b)} contrasts / {b.study_id.nunique()} studies')
    cv_bars(ax[0, 1], 'biomass', letter='b')
    a = ax[1, 0]
    s = cvS[cvS.endpoint == 'biomass']
    for r in s.itertuples():
        a.scatter(r.PI_width / 2, r.coverage95, color=C['A'] if r.category == 'A' else C['B'], s=14)
    a.axhline(0.95, color='#555', ls='--', lw=0.6); a.set_xlabel('Mean 95 % half-width'); a.set_ylabel('CV coverage'); panel(a, 'c', 'Intervals (CV)')
    a = ax[1, 1]
    sm = pd.read_csv(X / 'stress_gradient_study_means.csv'); g = pd.read_csv(X / 'stress_gradient.csv')
    s = sm[(sm.endpoint == 'biomass') & (sm.role == 'TRAIN')]; q = g[(g.endpoint == 'biomass') & (g.role == 'TRAIN')].iloc[0]
    a.scatter(s.D, s.R, s=6, color=C['bio'], alpha=0.6); xs = np.linspace(s.D.min(), s.D.max(), 5); a.plot(xs, q.intercept + q.slope * xs, color=C['bio'])
    a.set_xlabel('D = ln(S/C)'); a.set_ylabel('ln(SB/S)'); a.text(0.98, 0.95, f'slope {q.slope:.2f} [{q.slope_ci_lo:.2f}, {q.slope_ci_hi:.2f}]', transform=a.transAxes, ha='right', fontsize=6, va='top')
    panel(a, 'd', 'Stress gradient (study means)')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig6_biomass_overview', 'Fig. 6. Dry biomass (secondary endpoint), V5 TRAIN: data (shoot/whole plant; last timepoint per group in the default table), '
         'nested cluster CV of all candidates, interval calibration and the stress-damage gradient.', bottom=0.08)


def fig12():
    rounds = []
    for f, lab in [('cv_metrics_round4_summary.csv', 'R4 combined'), ('cv_metrics_round5_summary.csv', 'R5 numeric recoding'),
                   ('cv_metrics_round6_summary.csv', 'R6 block selection'), ('cv_metrics_round7_summary.csv', 'R7 learned stacks')]:
        p = OLD / f
        if p.exists():
            d = pd.read_csv(p); d['round'] = lab; rounds.append(d)
    H = pd.concat(rounds, ignore_index=True)
    H['label'] = H.model.astype(str) + np.where(H.get('feature_set', pd.Series('', index=H.index)).fillna('') != '', ' | ' + H.get('feature_set', pd.Series('', index=H.index)).fillna('').astype(str), '')
    RC = {'R4 combined': '#7fb3d5', 'R5 numeric recoding': '#2a6f97', 'R6 block selection': '#e07a2f', 'R7 learned stacks': '#2e8b57'}
    fig = plt.figure(figsize=(W, 7.6))
    for pos, ep, letter in [([0.45, 0.70, 0.50, 0.27], 'yield', 'a'), ([0.45, 0.355, 0.50, 0.26], 'biomass', 'b')]:
        a = fig.add_axes(pos)
        h = H[H.endpoint == ep].sort_values('RMSE').drop_duplicates('label').head(12).iloc[::-1]
        a.barh(range(len(h)), h.RMSE, color=[RC[r] for r in h['round']])
        for i, v in enumerate(h.RMSE):
            a.text(v, i, f' {v:.3f}', va='center', fontsize=5.4)
        a.set_yticks(range(len(h))); a.set_yticklabels([l[:48] for l in h.label], fontsize=5.4)
        a.set_xlim(h.RMSE.min() * 0.95, h.RMSE.max() * 1.06); a.set_xlabel('CV RMSE (study-grouped CV, pre-V5 tables)')
        panel(a, letter, f'{ep.title()}: best variants of rounds 4-7 (historical)')
        if ep == 'yield':
            from matplotlib.patches import Patch
            a.legend(handles=[Patch(color=c_, label=k) for k, c_ in RC.items()], frameon=False, fontsize=5.4, loc='upper right')
    a = fig.add_axes([0.45, 0.06, 0.50, 0.22])
    dup = pd.concat([pd.read_csv(p) for p in RES.glob('v5_feature_duplicates_audit_*.csv')])
    dup['n_dup'] = dup.dropped_duplicates.fillna('').map(lambda s: len([x for x in s.split(';') if x]))
    dup = dup[dup.context.str.startswith('FINAL')]
    dup['set'] = dup.context.str.split('|').str[1] + ' | ' + dup.context.str.split('|').str[2]
    g = dup.groupby('set').agg(cols=('n_columns', 'mean'), dups=('n_dup', 'mean'), const=('n_constant', 'mean'))
    a.barh(g.index, g.cols, color=C['grey'], label='columns built'); a.barh(g.index, g.dups + g.const, color=C['red'], label='dropped (duplicate / constant)')
    for i, (k, r) in enumerate(g.iterrows()):
        a.text(r.cols, i, f' {r.dups:.0f} dup + {r.const:.0f} const', va='center', fontsize=5.4)
    a.set_yticks(range(len(g))); a.set_yticklabels(g.index, fontsize=5.6)
    a.set_xlim(0, g.cols.max() * 1.35); a.set_xlabel('Model input columns (final TRAIN fit, mean over inner fits)'); a.legend(frameon=False, fontsize=5.4, loc='upper right')
    panel(a, 'c', 'V5: duplicate inputs removed')
    save(fig, 'Fig12_TRAIN_development', 'Fig. 12. TRAIN-only development before V5 (HISTORICAL estimates on the pre-V5 tables, study-grouped CV; not comparable 1:1 '
         'with the V5 cluster-grouped CV and not new results) and the V5 audit of the actual model inputs: exact duplicate and constant columns, '
         'identified on the training rows of each fit, are removed (v5_feature_duplicates_audit_*.csv).', bottom=0.17)


def fig13():
    fig, ax = plt.subplots(1, 2, figsize=(W, 3.6), gridspec_kw=dict(width_ratios=[1.05, 1]))
    a = ax[0]; a.axis('off')
    V = tv.set_index('endpoint')
    rowsl = ['Selected model (A)', 'RMSE TEST', 'RMSE CV', 'RMSE mean (TEST)', 'H1 RMSE < mean', 'H2 TEST ≤ 1.25 × CV', 'H3 coverage ≥ 0.90',
             'Verdict (A)', 'Conditional (B)', 'RMSE TEST (B)']
    pf = lambda b: 'pass' if b else 'fail'
    cells = []
    for ep in ['yield', 'biomass']:
        v = V.loc[ep]
        SH = {'RIDGE_REF': 'Ridge (design)', 'BASELINE_mean': 'Mean', 'STACK_B_REF': 'Ridge + MR2', 'STACK_B_MR0': 'MR0 + MR2', 'MR0': 'MR0'}
        cells.append([SH.get(v.selected_A, v.selected_A), f'{v.RMSE_A:.3f}', f'{v.RMSE_A_CV:.3f}', f'{v.RMSE_mean:.3f}', pf(v.H1_point_better_than_mean),
                      pf(v.H2_transfer), f'{pf(v.H3_coverage)} ({v.coverage_A:.3f})', v.verdict, SH.get(v.selected_B, v.selected_B) + ' (cond.)', f'{v.RMSE_B:.3f}'])
    t = a.table(cellText=np.array(cells).T, rowLabels=rowsl, colLabels=['Yield', 'Biomass'], loc='center', cellLoc='center', colWidths=[0.36, 0.36])
    t.auto_set_font_size(False); t.set_fontsize(5.8); t.scale(1, 1.35)
    panel(a, 'a', 'Pre-specified criteria')
    a = ax[1]; yy, yt, yl = 0, [], []
    for ep in ['yield', 'biomass']:
        r = tm[(tm.endpoint == ep)].set_index('model')
        ms = list(dict.fromkeys([SEL[(ep, 'A')], 'MR0', 'BASELINE_mean', 'RIDGE_REF', 'RF_V3TETF'] + ([SEL[(ep, 'B')]] if (ep, 'B') in SEL else [])))
        for m in ms:
            a.errorbar(r.loc[m, 'dRMSE_vs_mean'], yy, xerr=[[r.loc[m, 'dRMSE_vs_mean'] - r.loc[m, 'dRMSE_vs_mean_ci_lo']], [r.loc[m, 'dRMSE_vs_mean_ci_hi'] - r.loc[m, 'dRMSE_vs_mean']]],
                       fmt='o', color=C['A'] if r.loc[m, 'category'] == 'A' else C['B'], ms=4, lw=1)
            yt.append(yy); yl.append(f'{ep.title()}: {MODEL_LABEL[m]}' + (' ◀' if m in (SEL[(ep, 'A')], SEL.get((ep, 'B'))) else '')); yy -= 1
        yy -= 0.8
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=5.3); a.axvline(0, color='#555', lw=0.6)
    a.set_xlabel('ΔRMSE vs mean, TEST (95 % bootstrap)'); panel(a, 'b', 'Gain over the mean on TEST')
    fig.tight_layout()
    save(fig, 'Fig13_V5_TEST_posthoc', 'Fig. 13. V5 TEST evaluation, POST_HOC_TEST_REUSE. H1: RMSE below the mean baseline with bootstrap CI of the difference < 0 '
         '(for biomass the selected A model is the mean itself, so H1 cannot pass); H2: RMSE_TEST ≤ 1.25 × RMSE_CV; H3: 95 % interval coverage ≥ 0.90. '
         'Criteria were written into MODEL_FREEZE_V5.json before TEST was read. ◀ = selected; models without ◀ are shown for transparency, not re-selected on TEST.')


def fig17():
    lc = pd.read_csv(X / 'learning_curves_summary.csv')
    fig, ax = plt.subplots(1, 2, figsize=(W, 2.9))
    for a, ep, letter in [(ax[0], 'yield', 'a'), (ax[1], 'biomass', 'b')]:
        for m, col in [('BASELINE_mean', C['base']), ('MR0', C['bio']), ('RIDGE_REF', C['train'])]:
            d = lc[(lc.endpoint == ep) & (lc.model == m)].sort_values('n_train_studies')
            a.plot(d.n_train_studies, d.RMSE, 'o-', color=col, ms=3, label=MODEL_LABEL[m])
            a.fill_between(d.n_train_studies, d.RMSE - 1.96 * d.RMSE_se, d.RMSE + 1.96 * d.RMSE_se, color=col, alpha=0.12)
        a.set_xlabel('Training studies'); a.set_ylabel('Outer-fold RMSE'); a.legend(frameon=False, fontsize=5.6)
        panel(a, letter, f'{"Yield" if ep == "yield" else "Biomass"}: learning curve')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig17_learning_curves', 'Fig. 17. Learning curves (TRAIN, outer folds grouped by dependency cluster, seed 11; 20-100 % of the training clusters, 3 random draws; '
         'band = ±1.96 SE over folds × draws). Ridge = design features with nested tuning.', bottom=0.2)


def fig18():
    r = pd.read_csv(X / 'applicability_domain_rows.csv'); s = pd.read_csv(X / 'applicability_domain_summary.csv')
    fig, ax = plt.subplots(1, 3, figsize=(W, 2.9))
    a = ax[0]
    for role, col in [('TRAIN_CV', C['train']), ('TEST', C['test'])]:
        a.hist(r[(r.role == role) & (r.endpoint == 'yield')].dist.clip(0, 3), bins=30, color=col, alpha=0.6, density=True, label=role)
    a.axvline(1, color=C['red'], lw=0.7); a.set_xlabel('Distance / threshold (yield)'); a.legend(frameon=False); panel(a, 'a', 'Distance to TRAIN')
    a = ax[1]
    for ep, col in [('yield', C['train']), ('biomass', C['bio'])]:
        d = r[(r.endpoint == ep) & (r.role == 'TRAIN_CV')].dropna(subset=['abs_err']).copy(); d['oct'] = pd.qcut(d.dist, 8, labels=False, duplicates='drop')
        g = d.groupby('oct').abs_err.agg(['mean', 'sem']); a.errorbar(g.index, g['mean'], yerr=1.96 * g['sem'], fmt='o-', color=col, ms=3, label=ep.title())
    a.set_xlabel('Distance octile (CV)'); a.set_ylabel('MAE'); a.legend(frameon=False); panel(a, 'b', 'Error vs distance')
    a = ax[2]; a.axis('off')
    cells = [[q.endpoint, q.role, 'out' if q.ood else 'in', int(q.n), f'{q.MAE:.3f}', f'{q.coverage:.2f}'] for q in s.itertuples()]
    t = a.table(cellText=cells, colLabels=['Endpoint', 'Set', 'Domain', 'n', 'MAE', 'Coverage'], loc='center', cellLoc='center'); t.auto_set_font_size(False); t.set_fontsize(5.6); t.scale(1, 1.3)
    panel(a, 'c', 'In vs out of domain')
    fig.tight_layout(rect=(0, 0, 1, 1))
    save(fig, 'Fig18_applicability_domain', 'Fig. 18. Applicability domain: mean distance to the 5 nearest TRAIN contrasts from other dependency clusters in the standardised '
         'design-feature space of the frozen Ridge featuriser; threshold = 95th percentile of TRAIN distances. Errors of the selected a-priori model '
         '(CV out-of-fold, seed 11, and TEST).', bottom=0.2)


def fig20():
    pi = pd.read_csv(X / 'permutation_importance.csv'); mr = pd.read_csv(M / 'moderator_metaregression.csv')
    fig, ax = plt.subplots(1, 2, figsize=(W, 3.8))
    a = ax[0]
    p = pi[(pi.endpoint == 'yield') & (pi.model == 'RIDGE_REF')].head(12).iloc[::-1]
    a.barh(range(len(p)), 1000 * p['mean'], xerr=1000 * p['std'], color=C['train'], error_kw=dict(lw=0.5))
    a.set_yticks(range(len(p))); a.set_yticklabels(p.feature, fontsize=5.4); a.axvline(0, color='#555', lw=0.5)
    a.set_xlabel('ΔRMSE × 10⁻³ when permuted (outer cluster CV)'); panel(a, 'a', 'Yield: permutation importance')
    a = ax[1]
    m = mr[mr.endpoint == 'yield'].sort_values('beta').reset_index(drop=True)
    for i, r in m.iterrows():
        col = C['red'] if r.p_holm < 0.05 else (C['train'] if r.p < 0.05 else C['grey'])
        a.errorbar(r.beta, i, xerr=1.96 * r.se, fmt='o', color=col, ms=3)
        a.text(1.0, i, f' p={r.p:.2f} (Holm {r.p_holm:.2f}), {int(r.studies)} st.', transform=a.get_yaxis_transform(), fontsize=4.8, va='center')
    a.set_yticks(range(len(m))); a.set_yticklabels(m.moderator, fontsize=5.2); a.axvline(0, color='#555', lw=0.5)
    a.set_xlabel('β (lnRR), CR2 95 % CI'); panel(a, 'b', 'Yield: meta-regressions')
    fig.tight_layout(rect=(0, 0, 0.9, 1))
    save(fig, 'Fig20_moderators', 'Fig. 20. Moderators of the yield effect. (a) Grouped permutation importance of the design-feature Ridge model in the outer cluster CV '
         '(seed 11; mean ± SD over folds). (b) Single-moderator rma.mv meta-regressions (binary: present − absent; numeric: per 1 SD), CR2 robust tests, Holm adjustment.', bottom=0.14)


def tables():
    v31y = 403; v31ys = 69
    ty = default(load('yield')); tb = default(load('dry_biomass')); ey = default(load('yield', 'test')); eb = default(load('dry_biomass', 'test'))
    py = pooled[(pooled.endpoint == 'yield') & (pooled.set == 'TRAIN_primary')].iloc[0]
    pb = pooled[(pooled.endpoint == 'biomass') & (pooled.set == 'TRAIN_primary')].iloc[0]
    t1 = [('Yield TRAIN contrasts / studies', f'{v31y} / {v31ys}', f'{len(ty)} / {ty.study_id.nunique()}', 'V5 keeps all yield tiers as features; corrections in corrections_register.csv'),
          ('Yield TEST contrasts / studies', '36 / 12', f'{len(ey)} / {ey.study_id.nunique()}', 'same rules as TRAIN (V3.1 TEST used stricter rules)'),
          ('Biomass TRAIN contrasts / studies', '762 / 153', f'{len(tb)} / {tb.study_id.nunique()}', 'shoot/whole plant, last timepoint'),
          ('Biomass TEST contrasts / studies', '144 / 28', f'{len(eb)} / {eb.study_id.nunique()}', ''),
          ('Pooled yield effect (TRAIN)', '+54 % (V4 rma.mv mean, lnRR 0.431)', f'{pct(py.mu):+.0f} % [{pct(py.ci_lo):+.0f}, {pct(py.ci_hi):+.0f}]', 'V5: rma.mv, CR2'),
          ('Pooled biomass effect (TRAIN)', '+36 % [+29, +43] (V2)', f'{pct(pb.mu):+.0f} % [{pct(pb.ci_lo):+.0f}, {pct(pb.ci_hi):+.0f}]', ''),
          ('CV grouping', 'study (5 folds × 5 seeds)', 'dependency_cluster_id (outer 5 × 3 seeds, inner 3)', ''),
          ('Variance imputation', 'per V2 rules', 'Nakagawa 2023 CV-bar from TRAIN only, applied to TEST', 'imputed variances are not author-reported')]
    pd.DataFrame(t1, columns=['quantity', 'V3.1 / V4 (historical)', 'V5 (this version)', 'note']).to_csv(FIG / 'Table1_V31_vs_V5.csv', index=False, encoding='utf-8-sig')
    t2 = tm.merge(cvS[['endpoint', 'model', 'RMSE', 'RMSE_sd', 'R2', 'coverage95']].rename(columns={'RMSE': 'CV_RMSE', 'RMSE_sd': 'CV_RMSE_sd', 'R2': 'CV_R2', 'coverage95': 'CV_coverage95'}),
                  on=['endpoint', 'model'])
    t2 = t2[['label', 'endpoint', 'category', 'model', 'selected', 'CV_RMSE', 'CV_RMSE_sd', 'CV_R2', 'CV_coverage95', 'RMSE', 'RMSE_ci_lo', 'RMSE_ci_hi', 'MAE', 'R2', 'bias',
             'coverage95', 'PI_width', 'dRMSE_vs_mean', 'dRMSE_vs_mean_ci_lo', 'dRMSE_vs_mean_ci_hi', 'n_contrasts', 'n_studies']]
    t2 = t2.rename(columns={'RMSE': 'TEST_RMSE', 'MAE': 'TEST_MAE', 'R2': 'TEST_R2', 'bias': 'TEST_bias', 'coverage95': 'TEST_coverage95', 'PI_width': 'TEST_PI_width'})
    t2.sort_values(['endpoint', 'category', 'CV_RMSE']).round(4).to_csv(FIG / 'Table2_V5_models_CV_TEST.csv', index=False, encoding='utf-8-sig')
    print('tables written')


if __name__ == '__main__':
    import sys
    for f in (sys.argv[1:] or ['fig2', 'fig3', 'fig5', 'fig6', 'fig7', 'fig12', 'fig13', 'fig17', 'fig18', 'fig20', 'tables']):
        globals()[f]()
