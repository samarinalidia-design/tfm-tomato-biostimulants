"""Compact, modern one-row panels for the four additional checks (blocks 1-4), V5 TRAIN only.
FigB1_selective_prediction, FigB2_product_choice, FigB3_data_sensitivity, FigB4_simulation  (PNG 300 dpi + PDF + SVG)."""
import textwrap, pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

V5 = pathlib.Path(__file__).resolve().parents[1]; RES = V5 / 'results'; FIG = V5 / 'figures'
INK, MUTED, GRID = '#1f2937', '#6b7280', '#e5e7eb'
P = dict(blue='#2563eb', teal='#0d9488', orange='#ea580c', violet='#7c3aed', grey='#9ca3af', red='#dc2626', green='#16a34a')
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7.2, 'axes.titlesize': 8, 'axes.labelsize': 7, 'xtick.labelsize': 6.5,
                     'ytick.labelsize': 6.5, 'legend.fontsize': 6.2, 'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'xtick.color': MUTED,
                     'ytick.color': MUTED, 'text.color': INK, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
                     'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'svg.fonttype': 'none',
                     'axes.titleweight': 'bold', 'axes.titlelocation': 'left', 'axes.titlepad': 8})
W = 7.0


def head(fig, title, subtitle):
    fig.text(0.012, 0.985, title, fontsize=10, fontweight='bold', va='top', color=INK)
    fig.text(0.012, 0.925, subtitle, fontsize=7, va='top', color=MUTED)


def save(fig, name, note):
    fig.savefig(FIG / f'{name}_nocap.png', dpi=300, facecolor='white')
    fig.text(0.012, 0.012, textwrap.fill(note, 158), fontsize=5.6, color=MUTED, va='bottom')
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(FIG / f'{name}.{ext}', dpi=300 if ext == 'png' else None, facecolor='white')
    plt.close(fig); print('saved', name)


def tag(ax, t):
    ax.set_title(t, fontsize=7.8, color=INK)


def b1():
    A = pd.read_csv(RES / 'selective/selective_summary.csv'); A = A[A.endpoint == 'yield']
    fig, ax = plt.subplots(1, 3, figsize=(W, 3.1), gridspec_kw=dict(wspace=0.38))
    fig.subplots_adjust(top=0.78, bottom=0.36, left=0.07, right=0.985)
    head(fig, '1 · Can we flag reliable predictions?', 'Fruit yield, TRAIN, nested CV by dependency cluster; thresholds learnt inside training folds')
    L = A[A.score == 'LOCAL_ERROR'].sort_values('retained_frac'); Rn = A[A.score == 'RANDOM'].sort_values('retained_frac')
    a = ax[0]
    a.plot(L.retained_frac * 100, L.RMSE_ridge, '-o', color=P['blue'], ms=3.5, lw=1.6, label='Ridge, local-error rule')
    a.plot(L.retained_frac * 100, L.RMSE_mean, '--o', color=P['grey'], ms=3, lw=1.2, mfc='white', label='Mean, same contrasts')
    a.plot(Rn.retained_frac * 100, Rn.RMSE_ridge, ':', color=P['orange'], lw=1.4, label='Ridge, random abstention')
    a.set_xlabel('Contrasts predicted (%)'); a.set_ylabel('RMSE, lnRR'); a.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, -0.27), ncol=1, fontsize=5.4); tag(a, 'a  Error falls for everyone')
    a = ax[1]
    for s, col, lab in [('LOCAL_ERROR', P['blue'], 'local error'), ('AD_DISTANCE', P['violet'], 'distance (AD)'), ('RANDOM', P['grey'], 'random')]:
        d = A[A.score == s].sort_values('retained_frac')
        if s == 'LOCAL_ERROR':
            a.fill_between(d.retained_frac * 100, d.d_ridge_vs_mean_ci_lo, d.d_ridge_vs_mean_ci_hi, color=col, alpha=0.12, lw=0)
            for x, y, n in zip(d.retained_frac * 100, d.d_ridge_vs_mean, d.retained_studies):
                a.annotate(f'{n:.0f}', (x, y), xytext=(0, 4), textcoords='offset points', ha='center', fontsize=5.4, color=col)
        a.plot(d.retained_frac * 100, d.d_ridge_vs_mean, '-o', color=col, ms=3, lw=1.3, label=lab)
    a.axhline(0, color=INK, lw=0.7); a.set_xlabel('Contrasts predicted (%)'); a.set_ylabel('RMSE Ridge − mean')
    a.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, -0.27), ncol=3, fontsize=5.6); tag(a, 'b  …Ridge’s edge does not grow')
    a = ax[2]
    for s, col in [('LOCAL_ERROR', P['blue']), ('AD_DISTANCE', P['violet']), ('RANDOM', P['grey'])]:
        d = A[A.score == s].sort_values('retained_frac'); a.plot(d.retained_frac * 100, d.coverage_ridge, '-o', color=col, ms=3, lw=1.3)
    a.axhline(0.95, color=INK, lw=0.7, ls='--'); a.set_ylim(0.9, 0.98); a.set_xlabel('Contrasts predicted (%)'); a.set_ylabel('95 % interval coverage')
    tag(a, 'c  Interval coverage')
    save(fig, 'FigB1_selective_prediction', 'Numbers in b = studies that keep ≥ 1 prediction (of 76); band = 95 % cluster-bootstrap CI. Pre-specified criterion '
         '(local error, 80 % predicted): Ridge − mean = −0.021 [−0.049; +0.009] → not confirmed. Biomass: Ridge worse than the mean at every share.')


def b2():
    S = pd.read_csv(RES / 'choice/choice_summary.csv'); S = S[S.endpoint == 'yield']
    lab = {'CLASS_PRIOR': 'Class prior (in-fold)', 'RIDGE_REF': 'Ridge (selected A)', 'RF_V3TETF': 'RF, recoding+TE+text', 'STACK_A_REF': 'Stack Ridge+RF',
           'LSTACK_A': 'Learned stack A', 'MR2mt': 'MR2 + S_vs_C (cond.)', 'STACK_B_REF': 'Ridge+MR2 (cond.)'}
    order = list(lab)
    fig, ax = plt.subplots(1, 3, figsize=(W, 3.3), gridspec_kw=dict(wspace=0.12, width_ratios=[1.25, 1, 1]))
    fig.subplots_adjust(top=0.79, bottom=0.36, left=0.20, right=0.985)
    head(fig, '2 · Does the model pick the better biostimulant?', 'Fruit yield, TRAIN, out-of-fold; arms vs the same control: 49 studies / 911 pairs (15 / 280 across classes)')
    y = np.arange(len(order))[::-1]
    for a, metric, subsets, title in [(ax[0], 'correct', [('all pairs', P['grey']), ('different class', P['blue'])], 'a  Pairwise accuracy'),
                                      (ax[1], 'correct_noise', [('decisive pairs', P['grey']), ('decisive, different class', P['teal'])], 'b  Decisive pairs')]:
        for k, (sub, col) in enumerate(subsets):
            d = S[(S.metric == metric) & (S.subset == sub)].set_index('model').reindex(order)
            yy = y + (0.17 if k == 0 else -0.17)
            a.errorbar(d.value, yy, xerr=[d.value - d.ci_lo, d.ci_hi - d.value], fmt='o', color=col, ms=3.5, lw=1, capsize=0,
                       label=f'{sub.replace("different", "diff.")} ({int(d.studies.max())} st.)')
        a.axvline(0.5, color=INK, lw=0.7, ls='--'); a.set_xlim(0.35, 0.95); a.set_xlabel('share of correct choices')
        a.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=1, fontsize=5.4); tag(a, title); a.grid(axis='y', visible=False)
    ax[0].set_yticks(y); ax[0].set_yticklabels([lab[m] for m in order]); ax[1].set_yticks(y); ax[1].set_yticklabels([])
    a = ax[2]
    for k, (sub, col) in enumerate([('all sets', P['grey']), ('multi-class sets', P['orange'])]):
        d = S[(S.metric == 'regret_minus_random') & (S.subset == sub)].set_index('model').reindex(order)
        v = 100 * d.value; lo = 100 * d.ci_lo; hi = 100 * d.ci_hi
        a.errorbar(v, y + (0.17 if k == 0 else -0.17), xerr=[v - lo, hi - v], fmt='s', color=col, ms=3.2, lw=1, label=sub)
    a.axvline(0, color=INK, lw=0.7, ls='--'); a.set_yticks(y); a.set_yticklabels([]); a.grid(axis='y', visible=False)
    a.set_xlabel('regret − random (lnRR × 100)'); a.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=1, fontsize=5.4); tag(a, 'c  Loss vs best arm')
    save(fig, 'FigB2_product_choice', 'Choice = arm with the highest predicted lnRR. Decisive pairs: |observed difference| > 1.96 SE (control cancels). Noise-aware accuracy weights each '
         'pair by P(observed order is true). Regret < 0 = less yield lost than a random pick. Study-balanced means, 2000 study bootstrap resamples. RF was not the '
         'pre-selected model (exploratory). A simple class prior performs as well as the ML models.')


def b3():
    A = pd.read_csv(RES / 'sensitivity/sensitivity_summary.csv')
    lab = {'MAIN': 'V5 default', 'VAR_CVBAR_ALL': 'CV̄ for all groups', 'VAR_IMPUTED_x0.5': 'imputed CV × 0.5', 'VAR_IMPUTED_x1.5': 'imputed CV × 1.5',
           'N_IMPUTED_3': 'missing n = 3', 'SC_NO_COVARIANCE': 'no shared-control cov.', 'SC_ONE_PER_CONTROL': 'one contrast per control',
           'AUTHOR_SD_ONLY': 'author SD only', 'DEF_KNOWN': 'known definitions', 'DEF_NO_UNSPECIFIED': 'no UNSPECIFIED / all tps', 'WITH_BOXPLOTS': 'with box-plot centres'}
    order = list(lab); y = np.arange(len(order))[::-1]
    fig, ax = plt.subplots(1, 3, figsize=(W, 3.0), gridspec_kw=dict(wspace=0.12))
    fig.subplots_adjust(top=0.78, bottom=0.22, left=0.20, right=0.985)
    head(fig, '3 · Do data-preparation decisions change the conclusions?', 'TRAIN; one decision changed at a time; all methods on the same rows')
    for k, (ep, col) in enumerate([('yield', P['blue']), ('biomass', P['green'])]):
        d = A[(A.endpoint == ep) & (A.model == 'RIDGE_REF')].set_index('scenario').reindex(order)
        pc = lambda v: 100 * (np.exp(v) - 1)
        yy = y + (0.17 if k == 0 else -0.17)
        ax[0].errorbar(pc(d.mu), yy, xerr=[pc(d.mu) - pc(d.ci_lo), pc(d.ci_hi) - pc(d.mu)], fmt='o', color=col, ms=3.2, lw=1, label=ep)
        ax[1].plot(d.ridge_gain_pct, yy, 'o', color=col, ms=4)
        m = A[(A.endpoint == ep) & (A.model == 'MR0')].set_index('scenario').reindex(order)
        ax[2].plot(d.coverage95, yy, 'o', color=col, ms=4); ax[2].plot(m.coverage95, yy, '|', color=col, ms=7, mew=1.4)
        main = d.loc['MAIN']
        ax[0].axvline(pc(main.mu), color=col, lw=0.6, ls=':'); ax[1].axvline(main.ridge_gain_pct, color=col, lw=0.6, ls=':')
    ax[0].set_yticks(y); ax[0].set_yticklabels([lab[s] for s in order]); ax[0].set_xlabel('pooled effect, % (95 % CR1 CI)'); ax[0].legend(frameon=False, loc='lower right')
    tag(ax[0], 'a  Meta-analytic effect')
    ax[1].axvline(0, color=INK, lw=0.7, ls='--'); ax[1].set_yticks(y); ax[1].set_yticklabels([]); ax[1].set_xlabel('Ridge vs mean, ΔRMSE %')
    tag(ax[1], 'b  ML gain over the mean')
    ax[2].axvline(0.95, color=INK, lw=0.7, ls='--'); ax[2].set_yticks(y); ax[2].set_yticklabels([]); ax[2].set_xlabel('95 % coverage (● Ridge, | MR0)')
    tag(ax[2], 'c  Interval calibration')
    for a in ax:
        a.grid(axis='y', visible=False)
    save(fig, 'FigB3_data_sensitivity', 'Meta: 3-level REML with shared-control covariance, CR1 CI. CV: nested, grouped by dependency cluster, seed 11 (seeds 11/22 for the first two yield scenarios). Dotted lines = V5 default; biomass has no box-plot rows, so that scenario equals the default. '
         'Subset scenarios (one per control, author SD only, known definitions) change the study composition; within each scenario Ridge, MR0 and the mean use '
         'identical rows. Imputed variances are not author-reported.')


def b4():
    A = pd.read_csv(RES / 'simulation/simulation_summary_pooled.csv'); Pp = pd.read_csv(RES / 'simulation/simulation_summary_prediction.csv')
    col = {'CC': P['orange'], 'V5': P['blue'], 'V5_DIAG': P['violet'], 'UNW': P['grey']}
    lab = {'CC': 'complete case', 'V5': 'V5 (CV̄ + shared cov.)', 'V5_DIAG': 'CV̄, no covariance', 'UNW': 'unweighted study means'}
    fig, ax = plt.subplots(1, 3, figsize=(W, 2.85), gridspec_kw=dict(wspace=0.40))
    fig.subplots_adjust(top=0.76, bottom=0.29, left=0.09, right=0.985)
    head(fig, '4 · Does the procedure work when the truth is known?', '200 simulated meta-analyses per cell: 60 studies, shared controls, missing SDs, τ = between-study SD')
    for m in ['CC', 'V5', 'V5_DIAG', 'UNW']:
        for mech, ls in [('MNAR', '-'), ('MCAR', ':')]:
            d = A[(A.method == m) & (A.tau_b == 0.3) & ((A.mech == mech) | (A.p_miss == 0))].sort_values('p_miss')
            ax[0].plot(100 * d.p_miss, d.bias, ls, marker='o', color=col[m], ms=3, lw=1.3, label=lab[m] if mech == 'MNAR' else None)
            ax[1].plot(100 * d.p_miss, d.coverage, ls, marker='o', color=col[m], ms=3, lw=1.3)
    ax[0].axhline(0, color=INK, lw=0.7); ax[0].set_xlabel('studies without SD (%)'); ax[0].set_ylabel('bias of pooled lnRR')
    ax[0].legend(frameon=False, fontsize=5.5, loc='lower left'); tag(ax[0], 'a  Bias (— MNAR, ··· MCAR; τ = 0.3)')
    ax[1].axhline(0.95, color=INK, lw=0.7, ls='--'); ax[1].set_xlabel('studies without SD (%)'); ax[1].set_ylabel('95 % CI coverage'); tag(ax[1], 'b  CI coverage')
    a = ax[2]
    for m, c_, lb in [('V5_pooled', P['grey'], 'pooled mean'), ('V5_MR_moderator', P['teal'], 'meta-regression + moderator')]:
        d = Pp[(Pp.method == m) & (Pp.p_miss == 0.3) & (Pp.mech == 'MCAR')].sort_values('tau_b')
        a.plot(d.tau_b, d.rmse_new, '-o', color=c_, ms=3.5, lw=1.4, label=lb)
        for x, yv, cv_ in zip(d.tau_b, d.rmse_new, d.pi_coverage):
            a.annotate(f'{cv_:.2f}', (x, yv), xytext=(0, 5 if m == 'V5_pooled' else -9), textcoords='offset points', ha='center', fontsize=5.3, color=c_)
    a.set_xlabel('between-study SD τ  (labels = PI coverage)'); a.set_ylabel('RMSE for new-study contrasts'); a.legend(frameon=False, loc='upper left', fontsize=5.6)
    tag(a, 'c  New studies')
    save(fig, 'FigB4_simulation', 'True mean lnRR 0.375 (moderator effect 0.15). MNAR: studies with larger true effects omit SDs more often. Complete-case analysis is '
         'unbiased under MCAR but loses precision, and under MNAR is biased (−0.05…−0.44) with CI coverage 0.03–0.60. CV̄ imputation keeps every study: bias ≤ 0.010, '
         'coverage 0.92–0.975 in all cells. Ignoring the shared-control covariance changes almost nothing; unweighted study means perform similarly because τ '
         'dominates the sampling variance. A true moderator of 0.15 lowers new-study RMSE by only 1–4 %, as in the real data.')


if __name__ == '__main__':
    import sys
    for f in (sys.argv[1:] or ['b1', 'b2', 'b3', 'b4']):
        globals()[f]()
