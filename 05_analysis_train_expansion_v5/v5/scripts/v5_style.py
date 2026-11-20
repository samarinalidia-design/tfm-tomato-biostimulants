"""Shared figure style for the V5 TFM figures (same conventions as figures_TFM_A4_V4: A4 text width 17.8 cm,
DejaVu Sans, PNG 300 dpi + PDF + SVG, caption at the bottom, lower-case panel labels)."""
import pathlib, textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

V5 = pathlib.Path(__file__).resolve().parents[1]
FIG = V5 / 'figures'; FIG.mkdir(exist_ok=True)
RES = V5 / 'results'; DATA = V5 / 'data'
W = 7.0
C = dict(train='#2a6f97', test='#e07a2f', bio='#2e8b57', red='#c0392b', grey='#c9ced6', v1='#9aa5b1', ink='#333333', purple='#7a5195',
         A='#2a6f97', B='#7a5195', base='#9aa5b1')
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7.5, 'axes.titlesize': 8, 'axes.labelsize': 7.5,
                     'xtick.labelsize': 6.8, 'ytick.labelsize': 6.8, 'legend.fontsize': 6.4, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.edgecolor': '#555555', 'axes.linewidth': 0.6, 'svg.fonttype': 'none'})
VERSION_TAG = 'V5 (2026-11-20)'


def pct(x):
    return 100 * (np.exp(x) - 1)


def panel(ax, letter, title):
    ax.set_title(f'{letter}  {title}', loc='left', fontsize=8.5, fontweight='bold')


def save(fig, name, cap, bottom=None):
    """Adds a caption strip BELOW the existing layout (figure is extended, axes keep their size)."""
    fig.savefig(FIG / f'{name}_nocap.png', dpi=300)   # version without embedded caption (for the TFM document)
    txt = textwrap.fill(cap + f'  [{VERSION_TAG}]', 150)
    nl = txt.count('\n') + 1
    w, h = fig.get_size_inches()
    cap_h = 0.105 * nl + 0.12
    for ax in fig.axes:
        p = ax.get_position()
        ax.set_position([p.x0, (p.y0 * h + cap_h) / (h + cap_h), p.width, p.height * h / (h + cap_h)])
    for t in fig.texts:
        x, y = t.get_position(); t.set_position((x, (y * h + cap_h) / (h + cap_h)))
    fig.set_size_inches(w, h + cap_h)
    fig.text(0.01, 0.006, txt, fontsize=5.8, color='#333333', va='bottom')
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(FIG / f'{name}.{ext}', dpi=300 if ext == 'png' else None)
    plt.close(fig)
    print('saved', name, flush=True)


MODEL_LABEL = {'BASELINE_mean': 'Mean (baseline)', 'MR0': '3-level mean (MR0)', 'RIDGE_REF': 'Ridge, design features',
               'RF_REF': 'RF, design features', 'RIDGE_V3TE': 'Ridge, numeric recoding + TE', 'RF_V3TETF': 'RF, recoding + TE + text',
               'STACK_A_REF': 'Stack Ridge+RF (design)', 'STACK_A_V3': 'Stack Ridge+RF (recoding)', 'LSTACK_A': 'Learned stack A',
               'MR2mt': 'MR2 + S_vs_C (conditional)', 'STACK_B_REF': 'Ridge + MR2 (conditional)', 'STACK_B_MR0': 'MR0 + MR2 (conditional)',
               'STACK_B_V3': 'Ridge TE + MR2 (conditional)', 'LSTACK_B': 'Learned stack B (conditional)'}
STRESS_LABEL = {'SALINITY': 'Salinity', 'DROUGHT': 'Drought', 'HEAT': 'Heat', 'COLD': 'Cold', 'NUTRIENT': 'Nutrient', 'BIOTIC': 'Biotic',
                'COMBINED': 'Combined', 'HEAVY_METAL': 'Heavy metal', 'CHEMICAL_TOXICITY': 'Chemical toxicity', 'NONE': 'No stress (B vs C)',
                'ALKALINITY_CALCAREOUS': 'Alkalinity', 'FLOOD_HYPOXIA': 'Flooding/hypoxia', 'OTHER_MANAGEMENT': 'Other (management)',
                'OTHER': 'Other', 'LIGHT_UV_OZONE': 'Light/UV/ozone'}
CLASS_LABEL = {'DJ_BENEFICIAL_BACTERIA': 'Bacteria (PGPR)', 'DJ_BENEFICIAL_FUNGI': 'Fungi (AMF, Trichoderma)', 'DJ_SEAWEED_BOTANICAL': 'Seaweed/botanical',
               'DJ_HUMIC_FULVIC': 'Humic/fulvic', 'DJ_PROTEIN_N': 'Protein/amino acids', 'DJ_CHITOSAN_BIOPOLYMER': 'Chitosan/biopolymers',
               'DJ_INORGANIC': 'Inorganic (Si, Se, nano)', 'DJ_MIXTURE': 'Mixtures', 'DJ_OTHER_NON_DUJARDIN': 'Other (non-du Jardin)',
               'DJ_MICROBIAL_DERIVED_NONLIVING': 'Microbial-derived (non-living)', 'DJ_MICROBIAL_UNSPECIFIED': 'Microbial (unspecified)',
               'DJ_UNCLASSIFIED': 'Unclassified'}


def load(name, role='train'):
    return pd.read_parquet(DATA / f'{role}_{name}.parquet')


def default(x):
    return x[x.in_default == 1]
