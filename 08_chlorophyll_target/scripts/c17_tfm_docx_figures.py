"""Updated TFM figures for the docx: the original V5 figure of the TFM (yield / biomass panels, unchanged, taken from the
document itself) with an added row of chlorophyll panels (same style, letters continue). Used for TFM Figs 10, 16, 17, 20,
21, 22 and 23. Inputs: the unpacked TFM media (argv[1]), c09 / c12 / c13 / c15 results. Output: figures_TFM_V8/TFM_FigNN_*.png
(the chlorophyll row alone is also saved as *_chl_row.png).
Usage: python c17_tfm_docx_figures.py <unpacked_docx_media_dir>
"""
import sys, pathlib
import numpy as np
import pandas as pd
from PIL import Image

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
import v5_style as S
from v5_style import plt, C, W, pct, panel
MEDIA = pathlib.Path(sys.argv[1])
FIG = OUT / 'figures_TFM_V8'
R = OUT / 'results'
M8 = OUT / 'v8_meta' / 'results' / 'meta'
CHL = ['chlorophyll', 'chl_index']
TL = {'chlorophyll': 'Chl content', 'chl_index': 'Chl index (SPAD)'}
TLL = {'chlorophyll': 'Leaf chlorophyll content', 'chl_index': 'Chlorophyll index (SPAD etc.)'}
TC = {'chlorophyll': '#b5651d', 'chl_index': '#7a5195'}
EP = {'chlorophyll': 'CHL_CONTENT', 'chl_index': 'CHL_INDEX'}
ML = {'chlorophyll': 'RF_REF_wn', 'chl_index': 'RF_REF_wivw_re'}
MLAB = {'BASELINE_mean': 'Mean (baseline)', 'BASELINE_mean_studyw': 'Mean, equal study weight', 'MR0': '3-level mean (MR0)',
        'RIDGE_REF_wivw_re': 'Ridge, ivw weights', 'RIDGE_REF_wnone': 'Ridge, no weights', 'RIDGE_REF_wn': 'Ridge, equal study weight',
        'RF_REF_wivw_re': 'RF, ivw weights', 'RF_REF_wn': 'RF, equal study weight'}
POOL = pd.read_csv(M8 / 'pooled_effects.csv')


def stack(top_png, row_fig, name):
    p = FIG / f'{name}_chl_row.png'
    row_fig.savefig(p, dpi=300); plt.close(row_fig)
    a = Image.open(top_png).convert('RGB'); b = Image.open(p).convert('RGB')
    b = b.resize((a.width, round(b.height * a.width / b.width)), Image.LANCZOS)
    gap = 30
    c = Image.new('RGB', (a.width, a.height + gap + b.height), 'white'); c.paste(a, (0, 0)); c.paste(b, (0, a.height + gap))
    c.save(FIG / f'{name}.png', dpi=(300, 300)); print('saved', name, c.size, flush=True)


# ---------------------------------------------------------------- TFM Fig 10 (meta summary): (e) pooled effects, (f) variance
def fig10():
    sets = ['TRAIN_primary', 'TRAIN_SB_vs_S_only', 'TRAIN_author_SD_only', 'TEST', 'TRAIN_plus_TEST']
    fig, ax = plt.subplots(1, 2, figsize=(W, 2.9), gridspec_kw=dict(width_ratios=[1.7, 1]))
    a = ax[0]; y = 0; yt, yl = [], []
    for ep in CHL:
        P = POOL[POOL.endpoint == ep].set_index('set')
        for s in sets:
            q = P.loc[s]
            a.hlines(y, pct(q.pi_lo), pct(q.pi_hi), color=TC[ep], lw=0.6); a.hlines(y, pct(q.ci_lo), pct(q.ci_hi), color=TC[ep], lw=2.6)
            a.plot(pct(q.mu), y, 'D', color=TC[ep], ms=3.2)
            a.text(1.01, y, f'{pct(q.mu):+.0f} % [{pct(q.ci_lo):+.0f}, {pct(q.ci_hi):+.0f}] k={int(q.studies)}', transform=a.get_yaxis_transform(), fontsize=5.0, va='center')
            yt.append(y); yl.append(f'{TL[ep]}: {s.replace("TRAIN_", "").replace("_", " ").replace("plus", "TRAIN +")}'); y -= 1
        y -= 0.6
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=5.2); a.axvline(0, color='#555', lw=0.5); a.set_xlim(-75, 260)
    a.set_xlabel('Pooled effect, % (CR2 95 % CI; thin = 95 % PI)'); panel(a, 'e', 'Chlorophyll: pooled effects')
    a = ax[1]
    for i, ep in enumerate(CHL):
        q = POOL[(POOL.endpoint == ep) & (POOL.set == 'TRAIN_primary')].iloc[0]
        parts = np.array([q.tau2_study, q.tau2_within, q.typical_vi]); parts = parts / parts.sum(); left = 0
        for v, lab, colr in zip(parts, ['between studies', 'within studies', 'sampling'], [TC[ep], '#9fb7c9', C['grey']]):
            a.barh(i, 100 * v, left=left, color=colr, label=lab if i == 0 else None)
            if v > 0.05:
                a.text(left + 50 * v, i, f'{100 * v:.0f}%', ha='center', va='center', fontsize=5.6, color='white' if lab == 'between studies' else '#222')
            left += 100 * v
        a.text(103, i, f'τ = {np.sqrt(q.tau2_study + q.tau2_within):.2f}', fontsize=5.6, va='center')
    a.set_yticks(range(2)); a.set_yticklabels([TLL[e].replace(' (', '\n(') for e in CHL], fontsize=5.6); a.invert_yaxis(); a.set_xlim(0, 130)
    a.set_xlabel('% of variance of lnRR'); a.legend(frameon=False, fontsize=5.0, loc='upper center', bbox_to_anchor=(0.4, -0.25), ncol=2)
    panel(a, 'f', 'Chl: variance (TRAIN)')
    fig.tight_layout()
    stack(MEDIA / 'image10.png', fig, 'TFM_Fig10_meta_summary_with_chlorophyll')


# ---------------------------------------------------------------- TFM Fig 16 (model selection): (e, f) chlorophyll CV
def cvrows(t):
    out = []
    for g, suf in [('A399', ''), ('group', '_authorgroup')]:
        d = pd.read_csv(R / f'c09_cv_summary_{t}{suf}.csv'); d['grouping'] = g; out.append(d)
    return pd.concat(out)


def fig16():
    models = ['BASELINE_mean', 'MR0', 'RIDGE_REF_wivw_re', 'RIDGE_REF_wnone', 'RIDGE_REF_wn', 'RF_REF_wivw_re', 'RF_REF_wn']
    fig, ax = plt.subplots(1, 2, figsize=(W, 2.9), sharex=True)
    for a, t, letter in zip(ax, CHL, 'ef'):
        A = cvrows(t); y = np.arange(len(models))[::-1]
        for off, g, mk in [(0.15, 'A399', 'o'), (-0.15, 'group', 's')]:
            q = A[A.grouping == g].set_index('model').reindex(models)
            a.errorbar(q.d_vs_mean_pct, y + off, xerr=[q.d_vs_mean_pct - q.d_ci_low_pct, q.d_ci_high_pct - q.d_vs_mean_pct], fmt=mk, ms=3.2, lw=0.8,
                       color=TC[t] if g == 'A399' else '#777', label='folds by dependency cluster' if g == 'A399' else 'folds by research group (stricter)')
        q = A[A.grouping == 'A399'].set_index('model')
        for yy, m in zip(y, models):
            a.text(1.0, yy, f' {q.RMSE[m]:.3f}', transform=a.get_yaxis_transform(), fontsize=5.0, va='center')
        a.axvline(0, color='#555', lw=0.6); a.axvspan(-100, 0, color='#eaf4ea', zorder=0); a.set_xlim(-37, 22)
        a.set_yticks(y); a.set_yticklabels([MLAB[m] + (' ◀' if m == ML[t] or (t == 'chlorophyll' and m == 'MR0') else '') for m in models], fontsize=5.4)
        a.set_xlabel('CV RMSE change vs mean, % (95 % CI)'); panel(a, letter, f'{TL[t]}: grouped CV')
    h, l = ax[0].get_legend_handles_labels(); fig.tight_layout(rect=(0, 0.07, 0.97, 1))
    fig.legend(h, l, frameon=False, fontsize=5.4, loc='lower center', ncol=2)
    stack(MEDIA / 'image16.png', fig, 'TFM_Fig16_model_selection_with_chlorophyll')


# ---------------------------------------------------------------- TFM Fig 17 (uncertainty): (d, e) coverage vs half-width, (f) CI vs PI
def fig17():
    fig, ax = plt.subplots(1, 3, figsize=(W, 2.6), gridspec_kw=dict(width_ratios=[1, 1, 0.8]))
    for a, t, letter in zip(ax[:2], CHL, 'de'):
        s = pd.read_csv(R / f'c15_uncertainty_{t}.csv')
        for r in s.itertuples():
            col = C['base'] if r.model == 'BASELINE_mean' else (TC[t] if r.model.startswith(('RF', 'RIDGE')) else C['train'])
            a.scatter(r.half_width, r.coverage95, color=col, s=16)
            a.annotate(MLAB[r.model].replace(' weights', '').replace('equal study weight', 'eq. weight'), (r.half_width, r.coverage95), fontsize=4.6,
                       xytext=(3, 2), textcoords='offset points')
        a.axhline(0.95, color='#555', ls='--', lw=0.6); a.set_xlabel('Mean 95 % half-width (lnRR)'); a.set_ylabel('CV coverage')
        panel(a, letter, f'{TL[t]}: intervals in CV')
    a = ax[2]; y = 0; yt, yl = [], []
    for ep in CHL:
        r = POOL[(POOL.endpoint == ep) & (POOL.set == 'TRAIN_primary')].iloc[0]
        a.hlines(y, r.ci_lo, r.ci_hi, color=TC[ep], lw=3); a.hlines(y - 0.3, r.pi_lo, r.pi_hi, color=TC[ep], lw=1)
        a.plot(r.mu, y, 'D', color=TC[ep], ms=4); yt += [y, y - 0.3]; yl += [f'{TL[ep].split(" (")[0]}: CI of mean', f'{TL[ep].split(" (")[0]}: PI new study']; y -= 1
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=5.2); a.axvline(0, color=C['red'], lw=0.6); a.set_xlabel('lnRR'); panel(a, 'f', 'Chl: CI vs PI')
    fig.tight_layout()
    stack(MEDIA / 'image17.png', fig, 'TFM_Fig17_uncertainty_with_chlorophyll')


# ---------------------------------------------------------------- TFM Fig 20 (TEST criteria): (c) table, (d) change vs mean
def fig20():
    v = pd.read_csv(R / 'c12_test_verdict.csv'); m = pd.read_csv(R / 'c12_test_metrics.csv')
    fig, ax = plt.subplots(1, 2, figsize=(W, 2.9), gridspec_kw=dict(width_ratios=[1, 1.25]))
    a = ax[0]; a.axis('off')
    rows = [r for r in v.itertuples() if not (r.endpoint == 'CHL_INDEX' and r.role == 'ml_candidate')]
    cols = [f'{"Chl content" if r.endpoint == "CHL_CONTENT" else "Chl index"}\n{"primary" if r.role == "primary" else "ML candidate"}' for r in rows]
    lab = lambda mm: MLAB[mm].replace(' weights', '').replace('equal study weight', 'eq. weight').replace('3-level mean (MR0)', 'MR0')
    f = lambda b: 'pass' if b else 'fail'
    cell = [['Model'] + [lab(r.model) for r in rows],
            ['RMSE TEST'] + [f'{r.RMSE:.3f}' for r in rows],
            ['RMSE CV'] + [f'{r.RMSE_CV:.3f}' for r in rows],
            ['Mean, TEST'] + [f'{r.RMSE_mean:.3f}' for r in rows],
            ['H1 < mean'] + [f(r.H1_better_than_mean) for r in rows],
            ['H2 ≤ 1.25 × CV'] + [f(r.H2_transfer) for r in rows],
            ['H3 cov. ≥ 0.90'] + [f'{f(r.H3_coverage)} ({r.coverage:.2f})' for r in rows],
            ['Verdict'] + [r.verdict for r in rows]]
    tb = a.table(cellText=cell, colLabels=[''] + cols, loc='center', cellLoc='center', colWidths=[0.28, 0.24, 0.24, 0.24])
    tb.auto_set_font_size(False); tb.set_fontsize(5.0); tb.scale(1, 1.45)
    for (i, j), c in tb.get_celld().items():
        if i == 0:
            c.set_height(c.get_height() * 1.6)
    panel(a, 'c', 'Chlorophyll: pre-specified criteria')
    a = ax[1]; y = 0; yt, yl = [], []
    for t in CHL:
        x = m[m.endpoint == EP[t]].set_index('model')
        sel = {'chlorophyll': ['MR0', 'RF_REF_wn'], 'chl_index': ['RF_REF_wivw_re']}[t]
        for mm in ['MR0', 'RIDGE_REF_wivw_re', 'RIDGE_REF_wnone', 'RIDGE_REF_wn', 'RF_REF_wivw_re', 'RF_REF_wn']:
            r = x.loc[mm]; s = mm in sel
            a.errorbar(r.d_vs_mean_pct, y, xerr=[[r.d_vs_mean_pct - r.d_vs_mean_ci_lo_pct], [r.d_vs_mean_ci_hi_pct - r.d_vs_mean_pct]],
                       fmt='D' if s else 'o', color=TC[t], ms=3.4 if s else 2.6, lw=0.8)
            yt.append(y); yl.append(f'{TL[t]}: {MLAB[mm]}' + (' ◀' if s else '')); y -= 1
        y -= 0.5
    a.axvline(0, color='#555', lw=0.6); a.axvspan(-100, 0, color='#eaf4ea', zorder=0); a.set_xlim(-30, 35)
    a.set_yticks(yt); a.set_yticklabels(yl, fontsize=4.9); a.set_xlabel('TEST RMSE change vs TRAIN mean, % (95 % CI)')
    panel(a, 'd', 'Chlorophyll: gain over the mean on TEST')
    fig.tight_layout()
    stack(MEDIA / 'image20.png', fig, 'TFM_Fig20_TEST_criteria_with_chlorophyll')


# ---------------------------------------------------------------- TFM Fig 21 (learning curves): (c, d)
def fig21():
    fig, ax = plt.subplots(1, 2, figsize=(W, 2.5))
    for a, t, letter in zip(ax, CHL, 'cd'):
        lc = pd.read_csv(R / f'c15_learning_{t}.csv')
        for mm, col in [('BASELINE_mean', C['base']), ('MR0', C['bio']), (ML[t], TC[t])]:
            d = lc[lc.model == mm].sort_values('n_train_studies')
            a.plot(d.n_train_studies, d.RMSE, 'o-', color=col, ms=3, label=MLAB[mm])
            a.fill_between(d.n_train_studies, d.RMSE - 1.96 * d.RMSE_se, d.RMSE + 1.96 * d.RMSE_se, color=col, alpha=0.12)
        a.set_xlabel('Training studies'); a.set_ylabel('Outer-fold RMSE'); a.legend(frameon=False, fontsize=5.6)
        panel(a, letter, f'{TL[t]}: learning curve')
    fig.tight_layout()
    stack(MEDIA / 'image21.png', fig, 'TFM_Fig21_learning_curves_with_chlorophyll')


# ---------------------------------------------------------------- TFM Fig 22 (applicability domain): (d, e, f)
def fig22():
    r = pd.concat([pd.read_csv(R / f'c15_ad_rows_{t}.csv') for t in CHL]); s = pd.concat([pd.read_csv(R / f'c15_ad_summary_{t}.csv') for t in CHL])
    fig, ax = plt.subplots(1, 3, figsize=(W, 2.6))
    a = ax[0]
    for t in CHL:
        for role, ls in [('TRAIN_CV', '-'), ('TEST', '--')]:
            d = r[(r.target == t) & (r.role == role)].dist.clip(0, 3)
            a.hist(d, bins=30, histtype='step', density=True, color=TC[t], ls=ls, lw=1, label=f'{TL[t]}, {role.replace("TRAIN_CV", "CV")}')
    a.axvline(1, color=C['red'], lw=0.7); a.set_xlabel('Distance / threshold'); a.legend(frameon=False, fontsize=4.8); panel(a, 'd', 'Chl: distance to TRAIN')
    a = ax[1]
    for t in CHL:
        d = r[(r.target == t) & (r.role == 'TRAIN_CV')].dropna(subset=['abs_err']).copy(); d['oct'] = pd.qcut(d.dist, 8, labels=False, duplicates='drop')
        g = d.groupby('oct').abs_err.agg(['mean', 'sem']); a.errorbar(g.index, g['mean'], yerr=1.96 * g['sem'], fmt='o-', color=TC[t], ms=3, label=TL[t])
    a.set_xlabel('Distance octile (CV)'); a.set_ylabel('MAE'); a.legend(frameon=False, fontsize=5.4); panel(a, 'e', 'Error vs distance')
    a = ax[2]; a.axis('off')
    cells = [['Content' if q.target == 'chlorophyll' else 'Index', 'CV' if q.role == 'TRAIN_CV' else 'TEST', 'out' if q.ood else 'in', int(q.n), f'{q.MAE:.3f}', f'{q.coverage:.2f}'] for q in s.itertuples()]
    tb = a.table(cellText=cells, colLabels=['Target', 'Set', 'Domain', 'n', 'MAE', 'Cov.'], loc='center', cellLoc='center')
    tb.auto_set_font_size(False); tb.set_fontsize(5.2); tb.scale(1, 1.25)
    panel(a, 'f', 'In vs out of domain')
    fig.tight_layout()
    stack(MEDIA / 'image22.png', fig, 'TFM_Fig22_applicability_domain_with_chlorophyll')


# ---------------------------------------------------------------- TFM Fig 23 (selective prediction): (g-i) content, (j-l) index
def fig23():
    SC = {'LOCAL_ERROR': ('Local error of neighbours', C['train']), 'AD_DISTANCE': ('Distance to TRAIN (AD)', C['purple']),
          'DISAGREEMENT': ('|RF − mean|', C['test']), 'RANDOM': ('Random (control)', C['grey'])}
    fig, ax = plt.subplots(2, 3, figsize=(W, 4.6))
    for row, t in enumerate(CHL):
        A = pd.read_csv(R / f'c15_selective_{t}.csv')
        a = ax[row, 0]
        for s, (lab, col) in SC.items():
            d = A[A.score == s].sort_values('retained_frac')
            a.plot(d.retained_frac, d.RMSE_ml, 'o-', color=col, ms=3, lw=1, label=f'RF, {lab}')
            if s == 'LOCAL_ERROR':
                a.plot(d.retained_frac, d.RMSE_mean, 's--', color=col, ms=3, lw=0.8, mfc='white', label='Mean on the same rows')
        a.set_xlabel('Share of contrasts predicted'); a.set_ylabel('RMSE (lnRR)')
        if row == 0:
            a.legend(frameon=False, fontsize=4.7)
        panel(a, 'gj'[row], f'{TL[t].replace(" (SPAD)", "")}: error vs share')
        a = ax[row, 1]
        for s, (lab, col) in SC.items():
            d = A[A.score == s].sort_values('retained_frac')
            a.plot(d.retained_frac, d.d_ml_vs_mean, 'o-', color=col, ms=3, lw=1)
            if s == 'LOCAL_ERROR':
                a.fill_between(d.retained_frac, d.d_ml_vs_mean_ci_lo, d.d_ml_vs_mean_ci_hi, color=col, alpha=0.15)
                for x, yv, n in zip(d.retained_frac, d.d_ml_vs_mean, d.retained_studies):
                    a.text(x, yv, f'{n:.0f}', fontsize=4.8, ha='center', va='bottom', color=col)
        a.axhline(0, color='#555', lw=0.6); a.set_xlabel('Share of contrasts predicted'); a.set_ylabel('RMSE RF − RMSE mean')
        panel(a, 'hk'[row], 'RF − mean, same rows')
        a = ax[row, 2]
        for s, (lab, col) in SC.items():
            d = A[A.score == s].sort_values('retained_frac')
            a.plot(d.retained_frac, d.coverage_ml, 'o-', color=col, ms=3, lw=1)
        a.axhline(0.95, color='#555', ls='--', lw=0.6); a.axhline(0.90, color=C['red'], ls=':', lw=0.6)
        a.set_xlabel('Share of contrasts predicted'); a.set_ylabel('95 % interval coverage'); panel(a, 'il'[row], 'Interval coverage')
    fig.tight_layout()
    stack(MEDIA / 'image23.png', fig, 'TFM_Fig23_selective_prediction_with_chlorophyll')


if __name__ == '__main__':
    todo = sys.argv[2:] or ['10', '16', '17', '20', '21', '22', '23']
    for k in todo:
        globals()[f'fig{k}']()
