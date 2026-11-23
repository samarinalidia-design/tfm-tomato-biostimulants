"""Edits the TFM document in place: adds leaf chlorophyll (V8) as a third target.

* Figures 10, 16, 17, 20, 21, 22, 23: image replaced by the original V5 figure + a row of chlorophyll panels (c17 output);
  captions extended with the new panel letters. Original panels are unchanged, so the existing text stays valid.
* New paragraphs in Methods 3.7, 3.17; Results 4.1, 4.3, 4.4, 4.8-4.13; new 4.15; Discussion 5.9; Conclusion 8;
  abstract, Catalan summary, keywords, cover subtitle; Tables 11, 12, 14, 15 (new rows), Table 16 (new columns).
* Annex D with the chlorophyll-only figures (D1-D5) and Table D1; contents list extended.
Usage: python c18_update_tfm_docx.py <in.docx> <out.docx>
"""
import sys, copy, pathlib, json
import numpy as np
import pandas as pd
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from docx.shared import Emu
from PIL import Image

OUT = pathlib.Path(__file__).resolve().parents[1]
FIG = OUT / 'figures_TFM_V8'
R = OUT / 'results'
M8 = OUT / 'v8_meta' / 'results' / 'meta'
TEXT = json.loads((OUT / 'scripts' / 'c18_text.json').read_text(encoding='utf-8'))
SRC, DST = sys.argv[1], sys.argv[2]
D = docx.Document(SRC)
P0 = list(D.paragraphs)
pc = lambda x: 100 * (np.exp(x) - 1)


def find(prefix, toc=False):
    for p in D.paragraphs:
        if p.text.startswith(prefix) and p.style.name.startswith('TFM Contents') == toc:
            return p
    raise KeyError(prefix)


def strip_content(p_el):
    for el in list(p_el):
        if el.tag != qn('w:pPr'):
            p_el.remove(el)


def add_run(p_el, text, rpr=None):
    r = OxmlElement('w:r')
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = OxmlElement('w:t'); t.set(qn('xml:space'), 'preserve'); t.text = text; r.append(t)
    p_el.append(r)
    return r


def first_rpr(p):
    r = p._p.find(qn('w:r'))
    return None if r is None else r.find(qn('w:rPr'))


BODY_T = find('Most evidence concerns three groups')         # Results body paragraph (Normal + TNR runs)
TFMBODY_T = find('The synthesis supports a positive average')  # Discussion body (TFMBody style)
CAP_T = find('Figure 9. Evidence landscape')
FIGP_T = P0[[x._p for x in P0].index(CAP_T._p) - 1]
H2_T = find('4.4. Overall effects and heterogeneity')
H1_T = find('Annex C Scope of the factorial')
SIG_RPR = None
for r in find('Significance. The matrix is a practical map').runs:
    if r.bold:
        SIG_RPR = r._r.rPr
        break


def para_after(anchor, text, template=None, bold_lead=None):
    template = template or BODY_T
    el = copy.deepcopy(template._p); strip_content(el)
    rpr = first_rpr(template)
    if bold_lead:
        b = copy.deepcopy(rpr) if rpr is not None else OxmlElement('w:rPr')
        if b.find(qn('w:b')) is None:
            b.insert(0, OxmlElement('w:b'))
        add_run(el, bold_lead, b)
    add_run(el, text, rpr)
    anchor._p.addnext(el)
    return Paragraph(el, anchor._parent)


def caption_after(anchor, label, rest):
    el = copy.deepcopy(CAP_T._p); strip_content(el)
    runs = CAP_T._p.findall(qn('w:r'))
    add_run(el, label + ' ', runs[0].find(qn('w:rPr'))); add_run(el, rest, runs[1].find(qn('w:rPr')))
    anchor._p.addnext(el)
    return Paragraph(el, anchor._parent)


def heading_after(anchor, text, template, bm):
    el = copy.deepcopy(template._p); strip_content(el)
    bs = OxmlElement('w:bookmarkStart'); bs.set(qn('w:id'), str(9000 + bm[1])); bs.set(qn('w:name'), bm[0]); el.append(bs)
    add_run(el, text, first_rpr(template))
    be = OxmlElement('w:bookmarkEnd'); be.set(qn('w:id'), str(9000 + bm[1])); el.append(be)
    anchor._p.addnext(el)
    return Paragraph(el, anchor._parent)


def set_extent(inline, path, cx=5400000, max_cy=7600000):
    w, h = Image.open(path).size; cy = int(cx * h / w)
    if cy > max_cy:
        cx, cy = int(max_cy * w / h), max_cy
    for tag in ('wp:extent',):
        e = inline.find(qn(tag)); e.set('cx', str(cx)); e.set('cy', str(cy))
    for e in inline.iter(qn('a:ext')):
        if e.get('cx') is not None:
            e.set('cx', str(cx)); e.set('cy', str(cy))


def figure_after(anchor, path):
    tmp = D.add_paragraph(); run = tmp.add_run(); run.add_picture(str(path), width=Emu(5400000))
    el = tmp._p; old = el.find(qn('w:pPr'))
    if old is not None:
        el.remove(old)
    el.insert(0, copy.deepcopy(FIGP_T._p.find(qn('w:pPr'))))
    set_extent(el.find('.//' + qn('wp:inline')), path)
    anchor._p.addnext(el)
    return Paragraph(el, anchor._parent)


def replace_figure(caption_prefix, path, caption_add):
    cap = find(caption_prefix); figp = D.paragraphs[[p._p for p in D.paragraphs].index(cap._p) - 1]
    blip = figp._p.find('.//' + qn('a:blip')); rid = blip.get(qn('r:embed'))
    part = D.part.related_parts[rid]; part._blob = pathlib.Path(path).read_bytes()
    set_extent(figp._p.find('.//' + qn('wp:inline')), path)
    last = cap._p.findall(qn('w:r'))[-1]
    add_run(cap._p, ' ' + caption_add, last.find(qn('w:rPr')))
    return cap


def append_text(p, text):
    last = p._p.findall(qn('w:r'))[-1]; add_run(p._p, text, last.find(qn('w:rPr')))


def table_after_caption(caption_prefix):
    cap = find(caption_prefix); el = cap._p.getnext()
    while el is not None and el.tag != qn('w:tbl'):
        el = el.getnext()
    for t in D.tables:
        if t._tbl is el:
            return t
    raise KeyError(caption_prefix)


def set_cell(tc, text):
    ps = tc.findall(qn('w:p')); p = ps[0]
    for extra in ps[1:]:
        tc.remove(extra)
    runs = p.findall(qn('w:r')); rpr = runs[0].find(qn('w:rPr')) if runs else None
    for el in list(p):
        if el.tag != qn('w:pPr'):
            p.remove(el)
    add_run(p, text, rpr)


def add_rows(table, rows, template_row=-1):
    tpl = table.rows[template_row]._tr
    for vals in rows:
        tr = copy.deepcopy(tpl)
        for tc, v in zip(tr.findall(qn('w:tc')), vals):
            set_cell(tc, v)
        table._tbl.append(tr)


# ============================================================== numbers from the result files
POOL = pd.read_csv(M8 / 'pooled_effects.csv').set_index(['endpoint', 'set'])
TM = pd.read_csv(R / 'c12_test_metrics.csv').set_index(['endpoint', 'model'])
CV = {t: pd.read_csv(R / f'c09_cv_summary_{t}.csv').set_index('model') for t in ('chlorophyll', 'chl_index')}
UNC = {t: pd.read_csv(R / f'c15_uncertainty_{t}.csv').set_index('model') for t in ('chlorophyll', 'chl_index')}


def eff(ep, s):
    q = POOL.loc[(ep, s)]
    return f'{pc(q.mu):+.0f} [{pc(q.ci_lo):+.0f}, {pc(q.ci_hi):+.0f}]'.replace('-', '−'), f'{pc(q.pi_lo):.0f} to +{pc(q.pi_hi):.0f}'.replace('-', '−'), int(q.studies), int(q.k)


# ============================================================== cover, abstract, keywords
p = find('Fruit yield and terminal dry biomass')
for r in p.runs:
    r.text = r.text.replace('Fruit yield and terminal dry biomass', 'Fruit yield, terminal dry biomass and leaf chlorophyll')
append_text(find('Biostimulants can improve tomato performance under stress'), ' ' + TEXT['abstract_add'])
append_text(find("Els bioestimulants poden millorar la resposta"), ' ' + TEXT['resum_add'])
for kw in (find('Keywords:'), find('Paraules clau:')):
    last = kw.runs[-1]
    last.text = last.text.rstrip('.') + ('; leaf chlorophyll; SPAD.' if kw.text.startswith('Keywords') else '; clorofil·la foliar; SPAD.')

# ============================================================== methods
a = para_after(find('Yield definitions (V5).'), TEXT['m37'], bold_lead='Leaf chlorophyll (V8 extension). ')
a = para_after(find('Deviation from the original protocol.'), TEXT['m317'], bold_lead='Chlorophyll targets (V8). ')
t11 = table_after_caption('Table 11.')
add_rows(t11, [['08_chlorophyll_target/scripts (c02–c18)', 'Chlorophyll extraction packets, reconciliation, contrasts, analysis tables, comparable CV, freeze, TEST, meta-analysis, extra analyses and figures',
                'data/*chl*_V8.parquet, results/c09–c16*, freeze/MODEL_FREEZE_CHL.json, figures_TFM_V8/*']])

# ============================================================== 4.1 Table 12
t12 = table_after_caption('Table 12.')
add_rows(t12, [['TRAIN — leaf chlorophyll content', '607', '94', '93', '399 / 208', '161 (27%)'],
               ['TRAIN — chlorophyll index (SPAD)', '610', '55', '54', '363 / 247', '396 (65%)'],
               ['TEST — leaf chlorophyll content', '63', '15', '15', '30 / 33', '—'],
               ['TEST — chlorophyll index (SPAD)', '108', '10', '10', '66 / 42', '—']])
append_text(find('Table 12.'), 'Chlorophyll rows: V8 extension (Section 3.7).')

# ============================================================== 4.3 landscape
para_after(find('Significance. The matrix is a practical map'), TEXT['r43'])

# ============================================================== 4.4 meta
cap = replace_figure('Figure 10. Meta-analytic summary.', FIG / 'TFM_Fig10_meta_summary_with_chlorophyll.png',
                     '(e, f) The same summary for leaf chlorophyll content and the chlorophyll index (V8; same model and code).')
para_after(find('Figure 10a also shows that pooling TRAIN and TEST'), TEXT['r44'])
t14 = table_after_caption('Table 14.')
rows = []
for ep, lab in [('chlorophyll', 'Chl content'), ('chl_index', 'Chl index (SPAD)')]:
    for s, sl in [('TRAIN_primary', 'TRAIN (primary)'), ('TEST', 'TEST 2024–2026')]:
        e, pi, st, k = eff(ep, s); rows.append([f'{lab} — {sl}', str(st), f'{k:,}', e, pi])
add_rows(t14, rows)
para_after(find('For biomass (Figure 12a), the CI of 106'), TEXT['r44b'])

# ============================================================== 4.8 model selection + 4.8 uncertainty
replace_figure('Figure 16. Model selection on TRAIN', FIG / 'TFM_Fig16_model_selection_with_chlorophyll.png',
               '(e) Leaf chlorophyll content and (f) chlorophyll index: change in CV RMSE relative to the mean with 95% study-bootstrap CI, '
               'coloured = folds by dependency cluster, grey = folds by research group (studies sharing authors kept together); numbers = CV RMSE; ◀ = pre-declared models (V8).')
para_after(find('Among the a-priori yield models, the Ridge + Random Forest stack'), TEXT['r48'])
t15 = table_after_caption('Table 15.')
rows = []
for ep, t, lab, ms in [('CHL_CONTENT', 'chlorophyll', 'Chl content', [('BASELINE_mean', 'Mean (baseline)'), ('MR0', 'Three-level mean (MR0, primary)'), ('RF_REF_wn', 'RF, equal study weight (ML candidate)')]),
                       ('CHL_INDEX', 'chl_index', 'Chl index', [('BASELINE_mean', 'Mean (baseline)'), ('MR0', 'Three-level mean (MR0)'), ('RF_REF_wivw_re', 'RF, ivw weights (primary)')])]:
    for m, ml in ms:
        c = CV[t].loc[m]; q = TM.loc[(ep, m)]
        rows.append([lab, ml, 'A', f'{c.RMSE:.3f}', f'{c.R2:.2f}'.replace('-', '−'), f'{q.RMSE:.3f} [{q.RMSE_ci_lo:.2f}, {q.RMSE_ci_hi:.2f}]', f'{q.coverage95:.2f}'])
add_rows(t15, rows)
append_text(find('Table 15.'), 'Chlorophyll rows: comparable CV of Section 3.17 (V8), models frozen before the chlorophyll TEST extraction (not a re-use).')
replace_figure('Figure 17. Uncertainty in cross-validation.', FIG / 'TFM_Fig17_uncertainty_with_chlorophyll.png',
               '(d, e) The same for leaf chlorophyll content and the chlorophyll index (V8 models; colour = ML models, grey = mean, blue = MR0); (f) CI versus PI for the chlorophyll targets.')
para_after(find('For yield, the three-level mean had both the highest coverage'), TEXT['r48u'])

# ============================================================== 4.9 TEST
replace_figure('Figure 20. Summary of the pre-specified TEST criteria.', FIG / 'TFM_Fig20_TEST_criteria_with_chlorophyll.png',
               '(c, d) The same for the chlorophyll targets, whose models were frozen before any chlorophyll value of the TEST corpus was extracted; '
               'the ML candidate for chlorophyll content was declared before TEST (V8).')
a = para_after(find('Figure 19a plots the 378 TEST biomass contrasts'), TEXT['r49'])
t16 = table_after_caption('Table 16.')
tbl = t16._tbl; grid = tbl.find(qn('w:tblGrid')); gcs = grid.findall(qn('w:gridCol'))
widths = [1500000, 975000, 975000, 975000, 975000]
for _ in range(2):
    grid.append(copy.deepcopy(gcs[-1]))
for gc, w in zip(grid.findall(qn('w:gridCol')), widths):
    gc.set(qn('w:w'), str(int(w / 635)))
T16 = {0: ['Leaf chlorophyll content', 'Chlorophyll index (SPAD)'],
       1: ['MR0 (primary); RF, equal study weight (ML candidate)', 'RF, ivw weights'],
       2: ['MR0: not met (0.359 vs 0.357); RF: met (0.310 vs 0.357; −13% [−23, −0.6])', 'Not met (0.387 vs 0.348; +11% [+7, +31])'],
       3: ['Met (MR0 0.359 ≤ 0.389; RF 0.310 ≤ 0.399)', 'Not met (0.387 > 0.255)'],
       4: ['Met (MR0 0.921; RF 0.952)', 'Met (0.926)'],
       5: ['Not applicable (no conditional model)', 'Not applicable'],
       6: ['PARTIAL (MR0); CONFIRMED (RF candidate)', 'PARTIAL']}
for i, tr in enumerate(tbl.findall(qn('w:tr'))):
    tcs = tr.findall(qn('w:tc'))
    for v in T16[i]:
        tc = copy.deepcopy(tcs[-1]); set_cell(tc, v); tr.append(tc)
    for tc, w in zip(tr.findall(qn('w:tc')), widths):
        tcw = tc.find(qn('w:tcPr')).find(qn('w:tcW'))
        if tcw is not None:
            tcw.set(qn('w:w'), str(int(w / 635))); tcw.set(qn('w:type'), 'dxa')
append_text(find('Table 16.'), 'Chlorophyll columns: V8, models frozen before the chlorophyll TEST extraction.')
para_after(find('Figure 20a summarises Table 16'), TEXT['r49b'])
para_after(find('Significance. The test confirms the main biological message'), TEXT['r49sig'], bold_lead='Significance (chlorophyll). ')

# ============================================================== 4.10-4.12
replace_figure('Figure 21. Grouped learning curves (TRAIN).', FIG / 'TFM_Fig21_learning_curves_with_chlorophyll.png',
               '(c) Leaf chlorophyll content and (d) chlorophyll index, with the pre-declared Random Forest in place of Ridge (V8).')
para_after(find('In both panels the three-level mean (MR0) followed'), TEXT['r410'])
replace_figure('Figure 22. Applicability domain.', FIG / 'TFM_Fig22_applicability_domain_with_chlorophyll.png',
               '(d–f) The same for the chlorophyll targets, in the feature space of the frozen Random Forest candidates (V8).')
para_after(find('For yield, the distances of CV and TEST contrasts lay mostly'), TEXT['r411'])
replace_figure('Figure 23. Selective prediction (TRAIN, nested cross-validation).', FIG / 'TFM_Fig23_selective_prediction_with_chlorophyll.png',
               '(g–i) Leaf chlorophyll content and (j–l) chlorophyll index, with the pre-declared Random Forest in place of Ridge (V8).')
para_after(find('Under random abstention the Ridge error stayed between'), TEXT['r412'])

# ============================================================== 4.13 robustness
p = find('4.14. Additional analyses of practical interest')
prev = D.paragraphs[[x._p for x in D.paragraphs].index(p._p) - 1]
para_after(prev, TEXT['r413'])

# ============================================================== new 4.15 (after the last paragraph of 4.14.2)
anchor = find('5. Discussion'); prev = D.paragraphs[[x._p for x in D.paragraphs].index(anchor._p) - 1]
while not prev.text.strip():
    prev = D.paragraphs[[x._p for x in D.paragraphs].index(prev._p) - 1]
h = heading_after(prev, '4.15. Leaf chlorophyll as a third target: how much does a biostimulant change chlorophyll under different stresses?', H2_T, ('TFM_V8_415', 1))
x = h
for k in ('r415a', 'r415b'):
    x = para_after(x, TEXT[k])
x = para_after(x, TEXT['r415sig'], bold_lead='Significance. ')

# ============================================================== discussion 5.9
anchor = find('6. Conclusions'); prev = D.paragraphs[[x._p for x in D.paragraphs].index(anchor._p) - 1]
while not prev.text.strip():
    prev = D.paragraphs[[x._p for x in D.paragraphs].index(prev._p) - 1]
x = heading_after(prev, '5.9. Why leaf chlorophyll and SPAD are more predictable than yield and biomass', H2_T, ('TFM_V8_59', 2))
for k in sorted(k for k in TEXT if k.startswith('d59_')):
    x = para_after(x, TEXT[k], template=TFMBODY_T)

# ============================================================== conclusions
c7 = find('7. The positive average response was stable')
para_after(c7, TEXT['c8'], template=c7)

# ============================================================== Annex D
last = D.paragraphs[-1]
while not last.text.strip():
    last = D.paragraphs[[x._p for x in D.paragraphs].index(last._p) - 1]
x = heading_after(last, 'Annex D Leaf chlorophyll (V8): additional figures and table', H1_T, ('TFM_V8_AD', 3))
pb = OxmlElement('w:pageBreakBefore'); x._p.find(qn('w:pPr')).append(pb)
x = para_after(x, TEXT['annexD_intro'], template=TFMBODY_T)
for f, lab, title in [('Fig09_evidence_landscape_chlorophyll_nocap.png', 'Figure D1.', TEXT['capD1']),
                      ('Fig12b_forest_chlorophyll_nocap.png', 'Figure D2.', TEXT['capD2']),
                      ('Fig19b_chlorophyll_TEST_nocap.png', 'Figure D3.', TEXT['capD3']),
                      ('Fig24b_influence_chlorophyll_nocap.png', 'Figure D4.', TEXT['capD4']),
                      ('Fig25b_publication_bias_chlorophyll_nocap.png', 'Figure D5.', TEXT['capD5'])]:
    x = figure_after(x, FIG / f)
    x = caption_after(x, lab, title)
# Table D1 (clone of Table 13)
t13 = table_after_caption('Table 13.'); cap13 = find('Table 13.')
capD = copy.deepcopy(cap13._p); x._p.addnext(capD); capD = Paragraph(capD, x._parent)
for r in capD.runs:
    r.text = ''
capD.runs[0].text = 'Table D1. Leaf chlorophyll content: effect of biostimulant classes by stress type (SB vs S, TRAIN, cells with ≥ 3 independent studies; three-level REML per cell, robust t CI).'
newt = copy.deepcopy(t13._tbl); capD._p.addnext(newt)
cells = pd.read_csv(R / 'c10_cells_chlorophyll.csv'); cells = cells[cells.k >= 3].sort_values('k', ascending=False)
SL = {'SALINITY': 'Salinity', 'DROUGHT': 'Drought'}
CL = {'DJ_BENEFICIAL_BACTERIA': 'bacteria (PGPR)', 'DJ_BENEFICIAL_FUNGI': 'fungi (AMF, Trichoderma)', 'DJ_PROTEIN_N': 'protein hydrolysates',
      'DJ_SEAWEED_BOTANICAL': 'seaweed / botanical', 'DJ_INORGANIC': 'inorganic (Si, Se, nano)', 'DJ_OTHER_NON_DUJARDIN': 'other (non-du Jardin)',
      'DJ_CHITOSAN_BIOPOLYMER': 'chitosan / biopolymers'}
trs = newt.findall(qn('w:tr')); hdr, tpl = trs[0], trs[1]
for tr in trs[1:]:
    newt.remove(tr)
set_cell(hdr.findall(qn('w:tc'))[4], 'Contrasts')
for c in cells.itertuples():
    tr = copy.deepcopy(tpl)
    vals = [f'{SL.get(c.stress, c.stress.title())} × {CL.get(c.biostimulant, c.biostimulant)}', str(int(c.k)),
            f'{c.pct:+.0f} [{c.ci_low:+.0f}, {c.ci_high:+.0f}]'.replace('-', '−') + (' *' if c.tentative == 1 else ''),
            f'{c.pi_low:.0f} to +{c.pi_high:.0f}'.replace('-', '−'), str(int(c.n))]
    for tc, v in zip(tr.findall(qn('w:tc')), vals):
        set_cell(tc, v)
    newt.append(tr)
nt = OxmlElement('w:p'); newt.addnext(nt); x = Paragraph(nt, capD._parent)
x = para_after(x, TEXT['tabD1_note'], template=TFMBODY_T)
x.alignment = 0

# ============================================================== contents list
def toc_after(prefix, text, anchor_name, style_src_prefix):
    src = find(style_src_prefix, toc=True); ref = find(prefix, toc=True)
    el = copy.deepcopy(src._p); hl = el.find(qn('w:hyperlink')); hl.set(qn('w:anchor'), anchor_name)
    hl.find('.//' + qn('w:t')).text = text
    el.findall(qn('w:r'))[-1].find(qn('w:t')).text = '?'
    ref._p.addnext(el)


toc_after('4.14.2. Does the analytical procedure work when the truth is known?\t', '4.15. Leaf chlorophyll as a third target: how much does a biostimulant change chlorophyll under different stresses?', 'TFM_V8_415', '4.14. Additional analyses of practical interest\t')
toc_after('5.8. Implications for research and evidence-based applications\t', '5.9. Why leaf chlorophyll and SPAD are more predictable than yield and biomass', 'TFM_V8_59', '5.8. Implications for research')
toc_after('Annex C Scope of the factorial interaction evidence\t', 'Annex D Leaf chlorophyll (V8): additional figures and table', 'TFM_V8_AD', 'Annex C Scope of the factorial interaction evidence\t')

D.save(DST)
print('saved', DST)
