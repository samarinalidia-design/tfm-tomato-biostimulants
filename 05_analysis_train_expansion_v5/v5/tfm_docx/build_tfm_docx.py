# -*- coding: utf-8 -*-
"""Replace sections 3 (Methodology) and 4 (Results) of the TFM draft with the English V5 text, figures and tables.
Formatting is cloned from the existing draft (body text, captions, equations, headings). A backup of the original is kept."""
import copy, re, shutil, sys, pathlib, datetime
import docx
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
MASTER = HERE.parents[2]
sys.path.insert(0, str(HERE))
from content_methods import METHODS
from content_results import RESULTS

SRC = MASTER / 'TFM_Agrobiologia_Ambiental.docx'
BACKUP = MASTER / 'TFM_Agrobiologia_Ambiental_BACKUP_before_methods_results_20261120.docx'
OUT = SRC
MAX_W, MAX_H = 15.0, 20.5   # cm


def numbering(items):
    figs, tabs = {}, {}
    for it in items:
        if it[0] == 'fig':
            figs[it[2]] = len(figs) + 1
        elif it[0] == 'tab':
            tabs[it[1]] = len(tabs) + 2          # Table 1 is in the Introduction
    return figs, tabs


def subst(text, figs, tabs):
    text = re.sub(r'\{F:(\w+)\}', lambda m: f'Figure {figs[m.group(1)]}', text)
    return re.sub(r'\{T:(\w+)\}', lambda m: f'Table {tabs[m.group(1)]}', text)


TOKEN = re.compile(r'(https://[^\s;,()]+[^\s;,().]|`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)')


def add_hyperlink(par, url, size):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    rid = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement('w:hyperlink'); h.set(qn('r:id'), rid)
    r = OxmlElement('w:r'); rpr = OxmlElement('w:rPr')
    c = OxmlElement('w:color'); c.set(qn('w:val'), '1F4E79'); rpr.append(c)
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); rpr.append(u)
    if size:
        sz = OxmlElement('w:sz'); sz.set(qn('w:val'), str(int(size * 2))); rpr.append(sz)
    f = OxmlElement('w:rFonts'); f.set(qn('w:ascii'), 'Times New Roman'); f.set(qn('w:hAnsi'), 'Times New Roman'); rpr.append(f)
    r.append(rpr); t = OxmlElement('w:t'); t.text = url; t.set(qn('xml:space'), 'preserve'); r.append(t); h.append(r)
    par._p.append(h)


def add_runs(par, text, rpr_tpl, size=None, italic_all=False):
    for part in TOKEN.split(text):
        if not part:
            continue
        bold = italic = mono = False
        if part.startswith('https://'):
            add_hyperlink(par, part, size); continue
        if part.startswith('`'):
            part, mono = part[1:-1], True
        elif part.startswith('**'):
            part, bold = part[2:-2], True
        elif part.startswith('*') and part.endswith('*') and len(part) > 2:
            part, italic = part[1:-1], True
        r = par.add_run(part)
        if rpr_tpl is not None:
            r._r.insert(0, copy.deepcopy(rpr_tpl))
        if bold:
            r.bold = True
        if italic or italic_all:
            r.italic = True
        if mono:
            r.font.name = 'Consolas'; r._r.get_or_add_rPr().get_or_add_rFonts().set(qn('w:hAnsi'), 'Consolas')
            r.font.size = Pt((size or 10.5) - 1.5)
        elif size:
            r.font.size = Pt(size)
    return par


class Builder:
    def __init__(self, doc, anchor):
        self.doc, self.anchor = doc, anchor
        P = doc.paragraphs
        find = lambda pred: next(p for p in P if pred(p))
        self.tpl_body = find(lambda p: p.style.name == 'normal' and p.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY and p.runs and p.runs[0].font.name == 'Times New Roman' and len(p.text) > 200)
        self.tpl_cap = find(lambda p: p.text.startswith('Figura 1.'))
        self.tpl_eq = find(lambda p: p.text.strip().startswith('SD = SE'))
        self.tpl_h1 = find(lambda p: p.style.name == 'Heading 1' and p.text.startswith('4. Resultados'))
        self.tpl_h2 = find(lambda p: p.style.name == 'Heading 2' and p.text.startswith('4.1.'))
        self.snap = {k: (copy.deepcopy(v._p.pPr), copy.deepcopy(v.runs[0]._r.rPr) if v.runs and v.runs[0]._r.rPr is not None else None)
                     for k, v in [('body', self.tpl_body), ('cap', self.tpl_cap), ('eq', self.tpl_eq), ('h1', self.tpl_h1), ('h2', self.tpl_h2)]}

    def new_par(self, kind, style=None):
        p_el = OxmlElement('w:p')
        self.anchor._p.addprevious(p_el)
        par = Paragraph(p_el, self.anchor._parent)
        pPr, rPr = self.snap[kind]
        if pPr is not None:
            p_el.insert(0, copy.deepcopy(pPr))
        if style:
            par.style = self.doc.styles[style]
        return par, rPr

    def heading(self, level, text):
        kind = {1: 'h1', 2: 'h2', 3: 'h2'}[level]
        par, rPr = self.new_par(kind, {1: 'Heading 1', 2: 'Heading 2', 3: 'Heading 3'}[level])
        par.add_run(text)

    def body(self, text, ref=False):
        par, rPr = self.new_par('body')
        if '`' in text or 'https://' in text or ref:                     # long file paths / URLs: avoid stretched justified lines
            par.alignment = WD_ALIGN_PARAGRAPH.LEFT
        add_runs(par, text, rPr, size=10.5 if not ref else 10)

    def eq(self, text):
        par, rPr = self.new_par('eq')
        add_runs(par, text, rPr)

    def caption(self, label, title, desc):
        par, rPr = self.new_par('cap')
        r = par.add_run(f'{label}. {title} ')
        if rPr is not None:
            r._r.insert(0, copy.deepcopy(rPr))
        r.bold, r.italic = True, True
        add_runs(par, desc, rPr, size=9.5, italic_all=True)
        par.paragraph_format.keep_with_next = label.startswith('Table')
        return par

    def figure(self, path, label, title, desc):
        img = MASTER / path.replace('05_analysis_train_expansion_v5/', 'TFM_TRAIN_EXPANSION/', 1)
        nocap = img.with_name(img.stem + '_nocap.png')
        if nocap.exists():                       # figure without the caption embedded in the image
            img = nocap
        im = Image.open(img).convert('RGB')      # trim white margins (copy in tfm_docx/_img, originals untouched)
        from PIL import ImageChops
        bbox = ImageChops.difference(im, Image.new('RGB', im.size, 'white')).getbbox()
        if bbox:
            pad = 20
            im = im.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, im.width), min(bbox[3] + pad, im.height)))
        (HERE / '_img').mkdir(exist_ok=True)
        img = HERE / '_img' / img.name; im.save(img, dpi=(300, 300))
        w, h = im.size
        width = MAX_W; height = width * h / w
        if height > MAX_H:
            width = MAX_W * MAX_H / height
        par, _ = self.new_par('eq')
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(img), width=Cm(width))
        self.caption(label, title, desc)

    def table(self, label, title, header, rows, widths):
        self.caption(label, title, '')
        t = self.doc.add_table(rows=1 + len(rows), cols=len(header))
        self.anchor._p.addprevious(t._tbl)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblPr = t._tbl.tblPr
        borders = OxmlElement('w:tblBorders')
        for edge, sz in [('top', 8), ('bottom', 8), ('insideH', 2)]:
            e = OxmlElement(f'w:{edge}'); e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), str(sz)); e.set(qn('w:color'), '7F7F7F')
            borders.append(e)
        tblPr.append(borders)
        lay = OxmlElement('w:tblLayout'); lay.set(qn('w:type'), 'fixed'); tblPr.append(lay)
        for r_ in t.rows:
            trPr = r_._tr.get_or_add_trPr(); cs = OxmlElement('w:cantSplit'); trPr.append(cs)
        hdr = t.rows[0]._tr.get_or_add_trPr(); th = OxmlElement('w:tblHeader'); hdr.append(th)
        scale = 15.0 / sum(widths)
        for i, row in enumerate([header] + rows):
            for j, txt in enumerate(row):
                cell = t.rows[i].cells[j]
                cell.width = Cm(widths[j] * scale)
                p = cell.paragraphs[0]
                pf = p.paragraph_format
                pf.space_before = Pt(1); pf.space_after = Pt(1); pf.line_spacing = 1.0
                pf.keep_with_next = i < len(rows)          # keep short tables on one page
                add_runs(p, str(txt), None, size=8.5)
                for r in p.runs:
                    r.font.name = r.font.name or 'Arial'
                    if i == 0:
                        r.bold = True
                if i == 0:
                    tcPr = cell._tc.get_or_add_tcPr(); sh = OxmlElement('w:shd')
                    sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), 'E7ECF2'); tcPr.append(sh)
        for j, wcm in enumerate(widths):
            t.columns[j].width = Cm(wcm * scale)
        sp, _ = self.new_par('body')   # spacer after table


def main():
    if not BACKUP.exists():
        shutil.copy2(SRC, BACKUP)
    doc = docx.Document(str(BACKUP))
    P = doc.paragraphs
    start = next(p for p in P if p.text.strip().startswith('3. Metodolog'))
    end = next(p for p in P if p.style.name == 'Heading 1' and p.text.strip().startswith('5. Discus'))
    B = Builder(doc, end)
    # remove old sections 3-4 (paragraphs, tables, images)
    body = doc.element.body
    el, rm = start._p, []
    while el is not None and el is not end._p:
        rm.append(el); el = el.getnext()
    items = METHODS + RESULTS
    figs, tabs = numbering(items)
    for e in rm:
        body.remove(e)
    for it in items:
        kind = it[0]
        if kind == 'h1':
            B.heading(1, it[1])
        elif kind == 'h2':
            B.heading(2, it[1])
        elif kind == 'h3':
            B.heading(3, it[1])
        elif kind == 'p':
            B.body(subst(it[1], figs, tabs))
        elif kind == 'ref':
            B.body(it[1], ref=True)
        elif kind == 'eq':
            B.eq(it[1])
        elif kind == 'fig':
            _, path, key, title, desc = it
            B.figure(path, f'Figure {figs[key]}', subst(title, figs, tabs), subst(desc, figs, tabs))
        elif kind == 'tab':
            _, key, title, header, rows, widths = it
            B.table(f'Table {tabs[key]}', subst(title, figs, tabs), header, [[subst(c, figs, tabs) for c in r] for r in rows], widths)
    doc.save(str(OUT))
    print('figures', len(figs), 'tables', len(tabs), '->', OUT)


if __name__ == '__main__':
    main()
