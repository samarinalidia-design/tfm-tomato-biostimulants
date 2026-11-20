# -*- coding: utf-8 -*-
"""Final 'ready to submit' version: all edits of edit_ready_to_submit.py (without reviewer comments) plus
number style, body font/spacing of chapters 3-4, software citations, abstract sentence and licence statement.
Input (unchanged): TFM_Agrobiologia_Ambiental_ready_to_submit (1).docx -> TFM_Agrobiologia_Ambiental_READY_TO_SUBMIT.docx.
The static table of contents is renumbered afterwards from the Word-exported PDF (update_toc.ps1 / update_toc.py)."""
import re, sys, pathlib
import docx
from docx.shared import Pt
from docx.document import Document as _Doc

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_ready_to_submit as E

FINAL = E.M / 'TFM_Agrobiologia_Ambiental_READY_TO_SUBMIT.docx'
NUM = re.compile(r'(?<![\d.,])(\d{1,3})[    ](\d{3})(?![\d])')
PCT = re.compile(r'(\d)[    ]%')

TEXT_EDITS = [
    ('PDFs are processed with Docling (high-accuracy table mode) and PyMuPDF for text,',
     'PDFs are processed with Docling (Auer et al., 2024; high-accuracy table mode) and PyMuPDF (Artifex Software, 2025) for text,'),
    ('built on Claude large language models (Anthropic; Claude Opus',
     'built on Claude large language models (Anthropic, 2026; Claude Opus'),
    ('and R 4.5.0 with metafor 5.2.1 and clubSandwich.',
     'and R 4.5.0 (R Core Team, 2025) with metafor 5.2.1 (Viechtbauer, 2010) and clubSandwich 0.7.0 (Pustejovsky, 2025).'),
    ('lnRR is convenient for biologists because it expresses', 'lnRR is convenient because it expresses'),
    ('from 16 and 31 studies, respectively. Pooled effects',
     'from 16 and 31 studies, respectively. The evidence was extracted with a verified multi-agent pipeline based on large language models, '
     'and the database and code are openly available. Pooled effects'),
    ('de 16 i 31 estudis, respectivament. Els efectes',
     "de 16 i 31 estudis, respectivament. L'evidència es va extreure amb un sistema multiagent verificat basat en models de llenguatge, "
     'i la base de dades i el codi són de lliure accés. Els efectes'),
    ('every value can be located in the original publication through its DOI, page and locator.',
     'every value can be located in the original publication through its DOI, page and locator. The code is released under the MIT licence and '
     'the data under the Creative Commons Attribution 4.0 International licence (CC BY 4.0).'),
]
REFS = [  # (new reference, text of the reference it must precede)
    ('Anthropic (2026). Claude Opus 5.5 and Claude Sonnet 5.5 [Large language models]. Anthropic PBC. https://www.anthropic.com/claude', 'Asif, A.'),
    ('Artifex Software (2025). PyMuPDF 1.26 [Software]. https://github.com/pymupdf/PyMuPDF', 'Asif, A.'),
    ('Auer, C., Lysak, M., Nassar, A., Dolfi, M., Livathinos, N., Vagenas, P., et al. (2024). Docling Technical Report. arXiv:2408.09869. '
     'https://doi.org/10.48550/arXiv.2408.09869', 'Begg, C. B.'),
    ('Pustejovsky, J. E. (2025). clubSandwich: Cluster-robust (sandwich) variance estimators with small-sample corrections (version 0.7.0) '
     '[R package]. https://CRAN.R-project.org/package=clubSandwich', 'Pustejovsky, J. E., & Tipton'),
    ('R Core Team (2025). R: A language and environment for statistical computing (version 4.5.0). R Foundation for Statistical Computing, '
     'Vienna, Austria. https://www.R-project.org/', 'Rethlefsen, M. L.'),
]


def fix_numbers(doc):
    n = 0
    for t in doc.element.body.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
        if t.text:
            s = NUM.sub(r'\1,\2', t.text)
            s = PCT.sub(r'\1%', s)
            if s != t.text:
                n += 1; t.text = s
    return n


def unify_body(doc):
    P = doc.paragraphs
    i3 = next(i for i, p in enumerate(P) if p.style.name == 'Heading 1' and p.text.startswith('3.'))
    i5 = next(i for i, p in enumerate(P) if p.style.name == 'Heading 1' and p.text.startswith('5.'))
    st = doc.styles['TFM Body'].paragraph_format
    n = 0
    for p in P[i3:i5]:
        if p.style.name != 'normal' or not p.text.strip() or p.alignment == 1 or re.match(r'(Figure|Table) \d+\.', p.text):
            continue
        p.paragraph_format.line_spacing = st.line_spacing
        p.paragraph_format.space_after = st.space_after
        for r in p.runs:
            if r.font.size and abs(r.font.size.pt - 10.5) < 0.01:
                r.font.size = Pt(11)
            elif r.font.size and abs(r.font.size.pt - 9.0) < 0.01:
                r.font.size = Pt(9.5)
        for h in p._p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hyperlink'):
            for sz in h.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sz'):
                v = int(sz.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val'))
                sz.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', str({21: 22, 18: 19}.get(v, v)))
        n += 1
    return n


def main():
    _Doc.add_comment = lambda self, *a, **k: None          # final version: no reviewer comments
    E.OUT = FINAL
    E.main()
    doc = docx.Document(str(FINAL))
    for old, new in TEXT_EDITS:
        hits = sum(E.replace_across_runs(p, old, new) for p in E.all_paragraphs(doc) if old in E.runs_text(p))
        print('edit', hits, old[:60])
    for ref, before in REFS:
        tgt = next(p for p in doc.paragraphs if p.style.name == 'TFM Reference' and p.text.startswith(before))
        newp = E.clone_paragraph_after(tgt, ref)      # same formatting as the target reference
        tgt._p.addprevious(newp._p)                   # move it before the target
        print('reference', ref[:45])
    print('number runs changed', fix_numbers(doc))
    print('body paragraphs unified', unify_body(doc))
    doc.save(str(FINAL))
    print('->', FINAL)


if __name__ == '__main__':
    main()
