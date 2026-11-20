"""English schematic figures for the TFM Methods section: workflow, experimental contrasts / effect sizes, validation design."""
import pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FIG = pathlib.Path(__file__).resolve().parents[1] / 'figures'
INK, MUTED = '#1f2937', '#6b7280'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none'})


def box(ax, x, y, w, h, title, body, fc, ec):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.012,rounding_size=0.02', fc=fc, ec=ec, lw=1.1))
    ax.text(x + 0.012, y + h - 0.025, title, fontsize=7.6, fontweight='bold', color=INK, va='top')
    ax.text(x + 0.012, y + h - 0.075, body, fontsize=6.2, color=INK, va='top', linespacing=1.35)


def arrow(ax, a, b, col=MUTED):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=10, lw=1.1, color=col))


def save(fig, name):
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(FIG / f'{name}.{ext}', dpi=300 if ext == 'png' else None, facecolor='white')
    plt.close(fig); print('saved', name)


def workflow():
    fig, ax = plt.subplots(figsize=(7.0, 6.2)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    B, G, O, P, Y = ('#eff6ff', '#2563eb'), ('#f0fdf4', '#16a34a'), ('#fff7ed', '#ea580c'), ('#f5f3ff', '#7c3aed'), ('#fefce8', '#ca8a04')
    box(ax, 0.02, 0.83, 0.46, 0.15, '1  Literature search and screening', 'Crossref, Europe PMC, OpenAlex\n39 627 records → 12 141 unique → 766 full texts\nclass A (tomato + stress + biostimulant): 399 studies', *B)
    box(ax, 0.52, 0.83, 0.46, 0.15, '1b  External test corpus', 'publications first online 2024-2026\nsame screening protocol, collected separately\n108 records → 80 in scope → 58 closed', *O)
    box(ax, 0.02, 0.62, 0.96, 0.17, '2  Extraction and verification (relational database)', 'Docling text/table extraction → structured extraction of experiments, arms, stress, products and measurements\n'
        '→ targeted human/AI verification of critical fields against page images (source receipts) → every value linked to its page/table/figure.\n'
        'Two frozen databases: TRAIN_DEV (≤ 2023, frozen 13 Nov 2026) and EXTERNAL_TEST (2024-2026, frozen 18 Nov 2026)', *G)
    box(ax, 0.02, 0.41, 0.96, 0.17, '3  Analysis tables (V5, identical rules for TRAIN and TEST)', 'source-verified corrections (size fractions, measurement year, stress classes, unknown hybrid status) → effect sizes lnRR\n'
        '→ missing SDs imputed from the mean CV of TRAIN studies (Nakagawa et al. 2023) → shared controls and dependency clusters\n'
        'TRAIN: yield 831 contrasts / 76 studies; dry biomass 1452 / 172.  TEST: yield 117 / 16; dry biomass 378 / 31', *Y)
    box(ax, 0.02, 0.14, 0.46, 0.23, '4a  Meta-analysis (average effects)', 'three-level random-effects model\n(study / experiment / contrast)\npooled effect, heterogeneity, subgroups,\nmeta-regression, stress gradient,\ninteractions S×B and A×B,\npublication bias, influence', *P)
    box(ax, 0.52, 0.14, 0.46, 0.23, '4b  Prediction (new studies)', 'baselines vs Ridge / Random Forest / stacks\nnested CV grouped by dependency cluster\npre-specified selection rule\nMODEL FREEZE → one TEST evaluation\n(POST_HOC_TEST_REUSE)', *P)
    box(ax, 0.02, 0.0, 0.96, 0.115, '5  Additional checks (TRAIN only or simulated data)', 'learning curves · applicability domain · selective prediction · choice between biostimulants\nsensitivity to data-preparation decisions · simulation with known truth', *B)
    for a, b in [((0.25, 0.83), (0.25, 0.79)), ((0.75, 0.83), (0.75, 0.79)), ((0.5, 0.62), (0.5, 0.58)), ((0.25, 0.41), (0.25, 0.37)),
                 ((0.75, 0.41), (0.75, 0.37)), ((0.25, 0.14), (0.25, 0.11)), ((0.75, 0.14), (0.75, 0.11))]:
        arrow(ax, a, b)
    save(fig, 'FigM1_workflow')


def contrasts():
    fig, ax = plt.subplots(figsize=(7.0, 3.6)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    arms = {'C': (0.08, 0.72, 'Control\nno stress, no product', '#f3f4f6'), 'B': (0.08, 0.22, 'B\nbiostimulant only', '#ecfdf5'),
            'S': (0.40, 0.72, 'S\nstress only', '#fef2f2'), 'SB': (0.40, 0.22, 'SB\nstress + biostimulant', '#eff6ff')}
    for k, (x, y, t, fc) in arms.items():
        ax.add_patch(FancyBboxPatch((x, y), 0.18, 0.16, boxstyle='round,pad=0.01,rounding_size=0.03', fc=fc, ec='#9ca3af', lw=1))
        ax.text(x + 0.09, y + 0.08, t, ha='center', va='center', fontsize=7.2, color=INK)
    def lab(a, b, txt, col, off=(0, 0)):
        arrow(ax, a, b, col); ax.text((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1], txt, fontsize=6.8, color=col, ha='center', va='center',
                                      bbox=dict(fc='white', ec='none', pad=1))
    lab((0.26, 0.80), (0.40, 0.80), 'ln(S/C)\nstress damage D', '#dc2626', (0, 0.07))
    lab((0.49, 0.72), (0.49, 0.38), 'ln(SB/S)\nMAIN TARGET', '#2563eb', (0.08, 0))
    lab((0.17, 0.72), (0.17, 0.38), 'ln(B/C)\neffect without stress', '#16a34a', (-0.0, 0))
    ax.text(0.30, 0.08, 'S×B interaction = ln(SB/S) − ln(B/C)', fontsize=7, color=INK, ha='center')
    ax.text(0.665, 0.90, 'Effect size (log response ratio)', fontsize=8.2, fontweight='bold', color=INK)
    ax.text(0.665, 0.84, 'lnRR = ln(mean treated / mean reference)\neffect (%) = 100 × (e^lnRR − 1)\n'
            'lnRR = 0.37 ≈ +45 %;  lnRR = −0.22 ≈ −20 %\n\nsampling variance\nv = CV_t²/n_t + CV_c²/n_c   (CV = SD/mean)', fontsize=6.2, color=INK, va='top', linespacing=1.4)
    ax.text(0.665, 0.40, 'Two biostimulants A and B', fontsize=8.2, fontweight='bold', color=INK)
    ax.text(0.665, 0.34, 'A×B = ln(AB) − ln(A) − ln(B) + ln(C)\n> 0 synergy · ≈ 0 additive · < 0 antagonism\n\nContrasts used for prediction:\nSB vs S (stressed) and B vs C (no stress)', fontsize=6.2,
            color=INK, va='top', linespacing=1.4)
    save(fig, 'FigM2_contrasts_effect_sizes')


def validation():
    fig, ax = plt.subplots(figsize=(7.0, 3.3)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    cols = ['#93c5fd'] * 5
    ax.text(0.01, 0.95, 'Outer loop: 5 folds of dependency clusters (studies sharing controls/authors kept together), × 3 random seeds', fontsize=7, color=INK)
    for r in range(5):
        for c in range(5):
            ax.add_patch(plt.Rectangle((0.02 + c * 0.085, 0.80 - r * 0.11), 0.08, 0.08, fc='#fdba74' if c == r else '#bfdbfe', ec='white'))
        ax.text(0.46, 0.84 - r * 0.11, f'fold {r + 1}', fontsize=6.3, color=MUTED, va='center')
    ax.text(0.02, 0.17, 'orange = validation studies (never seen in training)\nblue = training studies', fontsize=6.4, color=MUTED)
    ax.add_patch(FancyBboxPatch((0.55, 0.52), 0.42, 0.38, boxstyle='round,pad=0.01,rounding_size=0.02', fc='#f5f3ff', ec='#7c3aed'))
    ax.text(0.565, 0.86, 'Inside each training part (inner loop)', fontsize=7.6, fontweight='bold', color=INK, va='top')
    ax.text(0.565, 0.80, '3 inner folds by cluster: choose hyper-parameters,\nencoders, stack weights and interval width\nweights 1/(v + τ²); no information from\nthe validation studies is used', fontsize=6.6, color=INK, va='top', linespacing=1.4)
    ax.add_patch(FancyBboxPatch((0.55, 0.06), 0.42, 0.38, boxstyle='round,pad=0.01,rounding_size=0.02', fc='#fff7ed', ec='#ea580c'))
    ax.text(0.565, 0.40, 'Freeze → one external test', fontsize=7.6, fontweight='bold', color=INK, va='top')
    ax.text(0.565, 0.34, 'selection rule fixed in advance (lowest CV error,\nsimpler model within 1 %) → refit on all TRAIN →\nMODEL_FREEZE (SHA-256) → TEST 2024-2026 evaluated\nonce: POST_HOC_TEST_REUSE (corpus used before)', fontsize=6.6, color=INK, va='top', linespacing=1.4)
    arrow(ax, (0.47, 0.60), (0.55, 0.70)); arrow(ax, (0.76, 0.52), (0.76, 0.44))
    save(fig, 'FigM3_validation_design')


if __name__ == '__main__':
    workflow(); contrasts(); validation()


def schema():
    fig, ax = plt.subplots(figsize=(7.0, 4.6)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    S = [('Identity / corpus', 'studies · files · screening\nextraction queue · source receipts', 0.02, 0.74, '#eff6ff', '#2563eb'),
         ('Experimental design', 'experiments · experiment_context\nstudy_relations (shared data)', 0.35, 0.74, '#f0fdf4', '#16a34a'),
         ('Intervention', 'arms · arm_components\nstress_factors · application', 0.68, 0.74, '#fefce8', '#ca8a04'),
         ('Observations', 'measurements · raw_observations\noutcome dictionary', 0.18, 0.44, '#fdf2f8', '#db2777'),
         ('Data assets', 'omics matrices · raw files\n(registered, not exploded into rows)', 0.52, 0.44, '#f5f3ff', '#7c3aed'),
         ('Quality control', 'provenance_qa · risk_of_bias\nverification status · patches', 0.18, 0.14, '#f3f4f6', '#6b7280'),
         ('Effects / dependence', 'contrasts · covariance\nshared_control_id · dependency_cluster_id', 0.52, 0.14, '#eff6ff', '#2563eb')]
    for t, b, x, y, fc, ec in S:
        box(ax, x, y, 0.30, 0.20, t, b, fc, ec)
    for a, b in [((0.32, 0.84), (0.35, 0.84)), ((0.65, 0.84), (0.68, 0.84)), ((0.45, 0.74), (0.35, 0.64)), ((0.80, 0.74), (0.70, 0.64)),
                 ((0.33, 0.44), (0.33, 0.34)), ((0.67, 0.44), (0.67, 0.34)), ((0.48, 0.24), (0.52, 0.24))]:
        arrow(ax, a, b)
    ax.text(0.5, 0.04, 'Raw source values are never overwritten; units, SDs, categories and contrasts are derived, versioned layers.\n'
            'Exports: contrast_candidates / marts (CSV + Parquet + SQLite) with data dictionary, QA report and SHA-256 manifest.', ha='center', fontsize=6.6, color=MUTED)
    save(fig, 'FigM4_relational_schema')


def extraction():
    fig, ax = plt.subplots(figsize=(7.0, 2.5)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    steps = [('1 Frozen corpus', 'manifest of full texts\nand supplements;\nstudy_id / file_id', '#eff6ff', '#2563eb'),
             ('2 Local extraction', 'Docling (tables),\nPyMuPDF, RapidOCR*,\npandas/openpyxl\n*only if no text layer', '#f0fdf4', '#16a34a'),
             ('3 Study package', 'text, tables, figures,\nquantitative candidates,\nlocators (page/table/\nfigure/cell)', '#fefce8', '#ca8a04'),
             ('4 Structuring','experiments, arms,\nstress, products, doses,\nmeasurements (JSON\nschema V4.4)', '#fdf2f8', '#db2777'),
             ('5 Verification', 'critical fields checked\nagainst page images;\nconflicts → human\nreview; patches logged', '#f5f3ff', '#7c3aed')]
    for i, (t, b, fc, ec) in enumerate(steps):
        x = 0.01 + i * 0.198
        box(ax, x, 0.22, 0.18, 0.70, t, '\n\n' + b if '\n' in t else b, fc, ec)
        if i < 4:
            arrow(ax, (x + 0.182, 0.57), (x + 0.198, 0.57))
    ax.text(0.5, 0.07, 'Source priority: machine-readable supplement > supplementary table > main-text table > value in text > calibrated figure digitisation.\n'
            'Values shown only in graphs are digitised with axis calibration; uncalibrated visual estimates are never accepted.', ha='center', fontsize=6.4, color=MUTED)
    save(fig, 'FigM5_extraction_pipeline')


if __name__ == '__main__':
    schema(); extraction()
