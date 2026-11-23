"""Expected change of the target by stress type x biostimulant class (SB_vs_S, default rows), for chlorophyll, yield and dry
biomass with the same method, so that the three targets can be compared cell by cell.

Method: three-level meta-analysis (contrast / experiment / study random effects; V5 metalib.ThreeLevelMeta) fitted separately
in every cell (h_stress_class x h2_dujardin, harmonised by the V5 feature code), and for every row / column margin.
A cell is reported when it has >= 3 studies; otherwise it is shown as 'too few studies'. For each cell: k studies, n contrasts,
pooled % change [95 % CI], 95 % prediction interval for a NEW study (tau-based), and the cell's I2-like share of study variance.
Inference: study-clustered robust SE with t(k - 1) (metalib sandwich; small-sample CR2 not applied); a cell with < 5 studies is labelled 'tentative'.
Usage: python c10_stress_by_biostimulant.py
Output: results/c10_cells_<target>.csv, results/c10_margins_<target>.csv, figures/c10_heatmap_three_targets.png/.svg
"""
import sys, pathlib, json
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'scripts'))
from metalib import ThreeLevelMeta

TARGETS = {
    'chlorophyll': (OUT / 'data' / 'train_chlorophyll_V8.parquet', 'in_default'),
    'yield': (REPO / '06_database_corrections_v6' / 'data' / 'train_yield_V6.parquet', 'in_default_v6'),
    'biomass': (REPO / '06_database_corrections_v6' / 'data' / 'train_dry_biomass_V6.parquet', 'in_default_v6'),
}
DJ_LABEL = {'DJ_BENEFICIAL_BACTERIA': 'Bacteria (PGPR)', 'DJ_BENEFICIAL_FUNGI': 'Fungi (AMF, Trichoderma)', 'DJ_INORGANIC': 'Inorganic (Si, Se, nano)',
            'DJ_SEAWEED_BOTANICAL': 'Seaweed / botanical', 'DJ_PROTEIN_N': 'Protein hydrolysates / N compounds',
            'DJ_HUMIC_FULVIC': 'Humic / fulvic', 'DJ_CHITOSAN_BIOPOLYMER': 'Chitosan / biopolymers',
            'DJ_OTHER_NON_DUJARDIN': 'Other (hormone-like, etc.)', 'DJ_MIXTURE': 'Mixtures', 'DJ_UNCLASSIFIED': 'Unclassified',
            'DJ_MICROBIAL_UNSPECIFIED': 'Microbial, unspecified'}
pct = lambda x: 100 * (np.exp(x) - 1)


def pool(g):
    k = g.study_id.nunique()
    if k < 3:
        return dict(k=k, n=len(g))
    X = np.ones((len(g), 1))
    m = ThreeLevelMeta().fit(g.effect.values.astype(float), g.var_lnrr_imp.values.astype(float), X, g.study_id.values,
                             (g.study_id + '|' + g.experiment_key.astype(str)).values)
    from scipy.stats import t as tdist
    mu = float(m.b[0]); se = float(np.sqrt(m.vcov_robust[0, 0])); s2 = float(np.sum(m.sigma2))
    q = float(tdist.ppf(0.975, m.df_robust))          # cluster-robust (study) SE with t(k - 1)
    return dict(k=k, n=len(g), pct=pct(mu), ci_low=pct(mu - q * se), ci_high=pct(mu + q * se),
                pi_low=pct(mu - 1.96 * np.sqrt(s2 + se ** 2)), pi_high=pct(mu + 1.96 * np.sqrt(s2 + se ** 2)),
                tau_total=float(np.sqrt(s2)), tentative=int(k < 5))


def main():
    res = {}
    for t, (path, col) in TARGETS.items():
        T = pd.read_parquet(path)
        T = T[(T[col] == 1) & (T.contrast_type == 'SB_vs_S')].copy()
        T['study_id'] = T.study_id.astype(str)
        T = T[T.effect.notna() & T.var_lnrr_imp.notna() & (T.var_lnrr_imp > 0)]
        cells = []
        for (s, d), g in T.groupby(['h_stress_class', 'h2_dujardin']):
            cells.append(dict(target=t, stress=s, biostimulant=d, **pool(g)))
        margins = [dict(target=t, margin='ALL', level='ALL', **pool(T))]
        for s, g in T.groupby('h_stress_class'):
            margins.append(dict(target=t, margin='stress', level=s, **pool(g)))
        for d, g in T.groupby('h2_dujardin'):
            margins.append(dict(target=t, margin='biostimulant', level=d, **pool(g)))
        C, M = pd.DataFrame(cells), pd.DataFrame(margins)
        C.to_csv(OUT / 'results' / f'c10_cells_{t}.csv', index=False); M.to_csv(OUT / 'results' / f'c10_margins_{t}.csv', index=False)
        res[t] = (C, M)
        print(t, 'rows', len(T), 'studies', T.study_id.nunique()); print(M.round(1).to_string(index=False))
    figure(res)


def figure(res):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    stresses = ['SALINITY', 'DROUGHT', 'HEAT', 'COLD', 'NUTRIENT', 'HEAVY_METAL', 'BIOTIC', 'COMBINED']
    djs = ['DJ_BENEFICIAL_BACTERIA', 'DJ_BENEFICIAL_FUNGI', 'DJ_INORGANIC', 'DJ_SEAWEED_BOTANICAL', 'DJ_PROTEIN_N',
           'DJ_HUMIC_FULVIC', 'DJ_CHITOSAN_BIOPOLYMER', 'DJ_OTHER_NON_DUJARDIN', 'DJ_MIXTURE']
    fig, axes = plt.subplots(1, 3, figsize=(17, 6.8), sharey=True)
    fig.subplots_adjust(bottom=0.24, wspace=0.06)
    norm = TwoSlopeNorm(vmin=-30, vcenter=0, vmax=100)
    for ax, t in zip(axes, ['chlorophyll', 'yield', 'biomass']):
        C = res[t][0].set_index(['stress', 'biostimulant'])
        Z = np.full((len(djs), len(stresses)), np.nan); txt = [['' for _ in stresses] for _ in djs]
        for i, d in enumerate(djs):
            for j, s in enumerate(stresses):
                if (s, d) in C.index:
                    r = C.loc[(s, d)]
                    if pd.notna(r.get('pct')):
                        Z[i, j] = r.pct
                        txt[i][j] = f"{r.pct:+.0f}%\nk={int(r.k)}" + ('*' if r.ci_low > 0 or r.ci_high < 0 else '')
                    else:
                        txt[i][j] = f"k={int(r.k)}"
        im = ax.imshow(Z, cmap='RdBu_r', norm=norm, aspect='auto')
        for i in range(len(djs)):
            for j in range(len(stresses)):
                v = Z[i, j]
                ax.text(j, i, txt[i][j], ha='center', va='center', fontsize=7.5,
                        color='white' if (not np.isnan(v) and v > 55) else '#222')
        ax.set_xticks(range(len(stresses))); ax.set_xticklabels([s.title().replace('_', ' ') for s in stresses], rotation=40, ha='right', fontsize=8.5)
        ax.set_yticks(range(len(djs))); ax.set_yticklabels([DJ_LABEL[d] for d in djs], fontsize=8.5)
        ax.tick_params(length=0)
        name = {'chlorophyll': 'Leaf chlorophyll content', 'yield': 'Fruit yield', 'biomass': 'Dry biomass'}[t]
        ax.set_title(f'{name}\n(stress + biostimulant vs stress)', fontsize=10)
        for s in ax.spines.values():
            s.set_visible(False)
    cb = fig.colorbar(im, ax=axes, shrink=0.75, pad=0.01); cb.set_label('Pooled change, % (3-level model; colour capped at +100 %)')
    fig.text(0.01, 0.015, 'Cells with >= 3 studies are pooled; k = studies; * 95 % CI excludes 0; empty = no studies. '
             'Classes: harmonised stress class and du Jardin (2015) biostimulant category of the V5 feature code.', fontsize=8)
    (OUT / 'figures').mkdir(exist_ok=True)
    for ext in ('png', 'svg'):
        fig.savefig(OUT / 'figures' / f'c10_heatmap_three_targets.{ext}', dpi=200, bbox_inches='tight')


if __name__ == '__main__':
    main()
