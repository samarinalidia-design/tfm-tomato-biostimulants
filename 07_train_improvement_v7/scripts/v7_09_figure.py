"""V7 thesis figure: why do the a-priori models not beat the mean?  (TRAIN, exploratory, after MODEL_FREEZE)
Reads only the out-of-fold predictions / summaries written by v7_02 ... v7_08 (identical folds and evaluation rows);
95 % CI = 2000 bootstrap resamples of studies (OOF squared errors averaged over the 3 seeds per contrast first).
Style = V5 block panels (v5_15_block_panels.py).  Output: 07_train_improvement_v7/figures/FigV7_prediction_limits.{png,pdf,svg}
"""
import sys, pathlib, textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = pathlib.Path(__file__).resolve().parents[1]
RES, FIG = OUT / 'results', OUT / 'figures'
FIG.mkdir(exist_ok=True)
INK, MUTED, GRID = '#1f2937', '#6b7280', '#e5e7eb'
P = dict(blue='#2563eb', green='#16a34a', grey='#9ca3af', orange='#ea580c')
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7.2, 'axes.titlesize': 8, 'axes.labelsize': 7, 'xtick.labelsize': 6.5,
                     'ytick.labelsize': 6.5, 'legend.fontsize': 6.2, 'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'xtick.color': MUTED,
                     'ytick.color': MUTED, 'text.color': INK, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
                     'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'svg.fonttype': 'none',
                     'axes.titleweight': 'bold', 'axes.titlelocation': 'left', 'axes.titlepad': 8})
W = 7.0
RNG = np.random.default_rng(2026)


def gain_vs_mean(oof, cfg, mean_cfg, sel=None, B=2000):
    """% change in RMSE of cfg relative to mean_cfg on identical rows, with study-bootstrap 95 % CI."""
    P_ = oof.copy()
    if sel is not None:
        P_ = P_[sel(P_)]
    P_['e2'] = (P_.y - P_.pred) ** 2
    E = P_[P_.config.isin([cfg, mean_cfg])].groupby(['config', 'contrast_id', 'study_id']).e2.mean().reset_index()
    Wd = E.pivot(index=['contrast_id', 'study_id'], columns='config', values='e2').dropna().reset_index()
    st = Wd.study_id.unique(); idx = {s: np.where(Wd.study_id.values == s)[0] for s in st}
    a, m = Wd[cfg].values, Wd[mean_cfg].values
    est = (np.sqrt(a.mean()) / np.sqrt(m.mean()) - 1) * 100
    bs = []
    for _ in range(B):
        ii = np.concatenate([idx[s] for s in RNG.choice(st, len(st))])
        bs.append((np.sqrt(a[ii].mean()) / np.sqrt(m[ii].mean()) - 1) * 100)
    return est, np.quantile(bs, 0.025), np.quantile(bs, 0.975)


def v702(name):
    P_ = pd.read_parquet(RES / f'v7_cv_oof_{name}.parquet')
    P_['config'] = P_.data + '|' + P_.features + '|' + P_.model
    return P_


def panel_a():
    rows = []
    y = v702('yield')
    for lab, cfg in [('V5 tables', 'V5|REF_V5|RIDGE'), ('V6 corrected', 'V6|REF_V5|RIDGE'),
                     ('+ 9 recovered studies', 'V7_RECOVERED|REF_V5|RIDGE'), ('flagged rows untrained', 'V6_QCORE|REF_V5|RIDGE')]:
        rows.append(('yield', lab) + gain_vs_mean(y, cfg, 'V6|-|BASELINE_mean'))
    t = pd.read_parquet(RES / 'v7_text_parsed_oof_yield.parquet')
    rows.append(('yield', 'text fields dropped') + gain_vs_mean(t, 'REF_CLEAN (text dropped) | RIDGE', 'MEAN'))
    rows.append(('yield', 'text fields parsed') + gain_vs_mean(t, 'ALL_PARSED | RIDGE', 'MEAN'))
    b = pd.read_parquet(RES / 'v7_biomass_oof.parquet')
    for lab, cfg in [('weights 1/(v+τ²) (V5)', 'REF_CLEAN | w=ivw_re | RIDGE'), ('no weights', 'REF_CLEAN | w=none | RIDGE'),
                     ('no weights, per organ', 'SPLIT | REF_CLEAN | w=none | RIDGE'), ('mean per organ', 'MEAN_BY_ORGAN')]:
        rows.append(('biomass', lab) + gain_vs_mean(b, cfg, 'MEAN'))
    return pd.DataFrame(rows, columns=['endpoint', 'label', 'est', 'lo', 'hi'])


SHORT = {'raw numeric environment': 'environment numerics', 'harmonised dose/application': 'dose, rank, n applications',
         'country': 'country', 'harmonised stress intensity': 'stress intensity (harmonised)',
         'harmonised categories': 'harmonised categories', 'raw numeric application': 'dose / applications (raw)',
         'system/substrate text': 'system / substrate text', 'season/soil/fertilisation text': 'season, soil, fertiliser text',
         'product text': 'product text', 'stress text': 'stress text', 'genotype text': 'genotype text',
         'application text': 'application text', 'unit_strings': 'unit strings', 'product type flags': 'product-type flags',
         'raw numeric stress': 'stress numerics (raw)', 'pathogen text': 'pathogen text'}


def panel_b():
    s = pd.read_csv(RES / 'v7_ablation_yield.csv')
    s = s[s.config.str.startswith('DROP | ')].copy()
    s['g'] = s.config.str.replace('DROP | ', '', regex=False)
    s['label'] = s.g.map(lambda g: next((v for k, v in SHORT.items() if g.startswith(k)), g[:28]))
    s = s[s.label != 'pathogen text']
    return s.sort_values('d_vs_REF')


def panel_c():
    a = pd.read_csv(RES / 'v7_env_probe_yield.csv').set_index('config')
    b = pd.read_csv(RES / 'v7_env_v6fill_yield.csv').set_index('config')
    mean_rmse = a.loc['MEAN', 'RMSE']
    pc = lambda r: (r.d_vs_MEAN_pct, 100 * r.d_vs_MEAN_lo / mean_rmse, 100 * r.d_vs_MEAN_hi / mean_rmse)
    rows = [('values + flags,\nas stored (4–36 %)',) + pc(a.loc['ENV_FULL']),
            ('values only',) + pc(a.loc['ENV_VALUES']),
            ('reported flags only',) + pc(a.loc['ENV_REPORTED']),
            ('values completed\nfrom text (7–38 %)',) + pc(b.loc['ENV_FULL_V6'])]
    return pd.DataFrame(rows, columns=['label', 'est', 'lo', 'hi'])


def main():
    A, Bd, Cd = panel_a(), panel_b(), panel_c()
    A.to_csv(RES / 'figV7_panel_a.csv', index=False); Bd.to_csv(RES / 'figV7_panel_b.csv', index=False); Cd.to_csv(RES / 'figV7_panel_c.csv', index=False)
    fig = plt.figure(figsize=(W, 3.3))
    ax = [fig.add_axes([0.185, 0.19, 0.15, 0.58]), fig.add_axes([0.535, 0.19, 0.13, 0.58]), fig.add_axes([0.85, 0.19, 0.135, 0.58])]
    fig.text(0.012, 0.985, 'Why do the a-priori models not beat the mean?', fontsize=10, fontweight='bold', va='top', color=INK)
    fig.text(0.012, 0.925, 'TRAIN, exploratory after MODEL_FREEZE; Ridge, nested CV grouped by cluster, 3 seeds; all variants scored on the same rows',
             fontsize=7, va='top', color=MUTED)
    # a
    n = len(A); yy = np.arange(n)[::-1]
    for i, r in A.iterrows():
        col = P['blue'] if r.endpoint == 'yield' else P['green']
        ax[0].errorbar(r.est, yy[i], xerr=[[r.est - r.lo], [r.hi - r.est]], fmt='o', color=col, ms=3.6, lw=1)
    ax[0].axvline(0, color=INK, lw=0.7, ls='--')
    ax[0].set_yticks(yy); ax[0].set_yticklabels(A.label)
    ny = (A.endpoint == 'yield').sum()
    ax[0].axhline(yy[ny - 1] - 0.5, color=GRID, lw=0.8)
    from matplotlib.lines import Line2D
    ax[0].legend([Line2D([], [], marker='o', color=P['blue'], lw=1, ms=3.6), Line2D([], [], marker='o', color=P['green'], lw=1, ms=3.6)],
                 ['yield', 'biomass'], loc='center right', bbox_to_anchor=(1.02, 0.62), frameon=False, handlelength=1.2, borderaxespad=0.1)
    ax[0].set_xlabel('ΔRMSE vs mean, %')
    ax[0].set_title('a  Data and preparation', fontsize=7.8, color=INK, x=-1.05)
    ax[0].grid(axis='y', visible=False)
    # b
    yb = np.arange(len(Bd))[::-1]
    sig = (Bd.d_vs_REF_lo > 0) | (Bd.d_vs_REF_hi < 0)
    for k, (i, r) in enumerate(Bd.iterrows()):
        col = P['blue'] if r.d_vs_REF > 0 else P['grey']
        ax[1].errorbar(r.d_vs_REF, yb[k], xerr=[[r.d_vs_REF - r.d_vs_REF_lo], [r.d_vs_REF_hi - r.d_vs_REF]], fmt='o',
                       color=col, ms=3.6 if sig.loc[i] else 3.0, lw=1, mfc=col if sig.loc[i] else 'white')
    ax[1].axvline(0, color=INK, lw=0.7, ls='--')
    ax[1].set_yticks(yb); ax[1].set_yticklabels(Bd.label)
    ax[1].set_xlabel('ΔRMSE when removed\n← noise   signal →')
    ax[1].set_title('b  Feature groups (yield)', fontsize=7.8, color=INK, x=-1.55)
    ax[1].grid(axis='y', visible=False)
    # c
    yc = np.arange(len(Cd))[::-1]
    for k, r in Cd.iterrows():
        col = P['orange'] if k == len(Cd) - 1 else P['blue']
        ax[2].errorbar(r.est, yc[k], xerr=[[r.est - r.lo], [r.hi - r.est]], fmt='o', color=col, ms=3.6, lw=1)
    ax[2].axvline(0, color=INK, lw=0.7, ls='--')
    ax[2].set_yticks(yc); ax[2].set_yticklabels(Cd.label)
    ax[2].set_xlabel('ΔRMSE vs mean, %')
    ax[2].set_title('c  Environment block (yield)', fontsize=7.8, color=INK, x=-1.05)
    ax[2].grid(axis='y', visible=False)
    name = 'FigV7_prediction_limits'
    fig.savefig(FIG / f'{name}_nocap.png', dpi=300, facecolor='white')
    note = ('a: yield V5 → V6 corrections; recovered studies (pooled main effects, fruit number × fruit mass) and removal of reliability-flagged '
            'rows act on training only; text = raw free-text fields vs their parsed numeric versions. Biomass: training weights 1/(v + τ²) vs none. '
            'b: filled = 95 % CI excludes 0. c: CORE outcome descriptors + 10 environment numerics; completed = V6 values parsed from the database text.')
    fig.text(0.012, 0.012, textwrap.fill(note, 158), fontsize=5.6, color=MUTED, va='bottom')
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(FIG / f'{name}.{ext}', dpi=300 if ext == 'png' else None, facecolor='white')
    print(A.round(2).to_string()); print(Bd[['label', 'd_vs_REF', 'd_vs_REF_lo', 'd_vs_REF_hi']].round(4).to_string()); print(Cd.round(2).to_string())


if __name__ == '__main__':
    main()
