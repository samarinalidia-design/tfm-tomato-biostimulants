"""Updates the GitHub links of the TFM document after the V6-V8 folders and the release data-v6-v8 were published.

1. Adds the folders 06_database_corrections_v6, 07_train_improvement_v7, 08_chlorophyll_target and the release data-v6-v8 to the
   two data-availability paragraphs (Methods 3.18 and 'Data and code availability').
2. Turns every repository path that is written as plain text (00_... to 08_...) into a hyperlink to the file or folder on GitHub
   (blob/main for files, tree/main for folders; for paths with wildcards, the deepest existing folder), formatted like the
   existing path links (Consolas, dark blue, underlined). Paths that do not exist in the repository are left unlinked and listed.
Usage: python c20_tfm_github_links.py <docx>   (modified in place)
"""
import sys, re, copy, pathlib
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.opc.constants import RELATIONSHIP_TYPE as RT

REPO = pathlib.Path(__file__).resolve().parents[2]
GH = 'https://github.com/samarinalidia-design/tfm-tomato-biostimulants'
REL = GH + '/releases/tag/data-v6-v8'
DOCX = sys.argv[1]
D = docx.Document(DOCX)
PAT = re.compile(r'(?<![\w/.\-])(0[0-8]_[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_.\-]+)*)')
missing, n_links = [], 0


def url_for(path):
    path = path.rstrip('.,;:)')
    parts = path.split('/')
    while parts and not (REPO / '/'.join(parts)).exists():
        parts = parts[:-1]
    if not parts:
        missing.append(path); return None, path
    p = '/'.join(parts)
    return f"{GH}/{'blob' if (REPO / p).is_file() else 'tree'}/main/{p}", path


def link_rpr(base, code=True):
    r = copy.deepcopy(base) if base is not None else OxmlElement('w:rPr')
    for tag in ('w:rFonts', 'w:color', 'w:u', 'w:sz'):
        for e in r.findall(qn(tag)):
            r.remove(e)
    sz_cs = r.find(qn('w:szCs'))
    base_sz = int(base.find(qn('w:sz')).get(qn('w:val'))) if base is not None and base.find(qn('w:sz')) is not None else 21
    if code:
        f = OxmlElement('w:rFonts')
        for a in ('ascii', 'hAnsi'):
            f.set(qn(f'w:{a}'), 'Consolas')
        f.set(qn('w:eastAsia'), 'Times New Roman'); f.set(qn('w:cs'), 'Times New Roman'); r.insert(0, f)
    c = OxmlElement('w:color'); c.set(qn('w:val'), '1F4E79'); r.append(c)
    if code:
        s = OxmlElement('w:sz'); s.set(qn('w:val'), str(16 if base_sz <= 19 else base_sz - 2))
        (sz_cs.addprevious(s) if sz_cs is not None else r.append(s))
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); r.append(u)
    return r


def make_run(text, rpr):
    r = OxmlElement('w:r')
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = OxmlElement('w:t'); t.set(qn('xml:space'), 'preserve'); t.text = text; r.append(t)
    return r


def make_link(part, url, text, rpr):
    rid = part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement('w:hyperlink'); h.set(qn('r:id'), rid); h.set(qn('w:history'), '1')
    h.append(make_run(text, rpr)); return h


def linkify_paragraph(p_el, part):
    global n_links
    for r in list(p_el.findall(qn('w:r'))):
        ts = r.findall(qn('w:t'))
        if not ts:
            continue
        text = ''.join(t.text or '' for t in ts)
        if not PAT.search(text):
            continue
        rpr = r.find(qn('w:rPr')); pieces = []; pos = 0
        for m in PAT.finditer(text):
            u, shown = url_for(m.group(1))
            if u is None:
                continue
            pieces.append(('t', text[pos:m.start()])); pieces.append(('l', shown, u)); pos = m.start() + len(shown)
        if not pieces:
            continue
        pieces.append(('t', text[pos:]))
        anchor = r
        for pc in pieces:
            if pc[0] == 't':
                if pc[1]:
                    el = make_run(pc[1], rpr)
                else:
                    continue
            else:
                el = make_link(part, pc[2], pc[1], link_rpr(rpr)); n_links += 1
            anchor.addnext(el); anchor = el
        p_el.remove(r)


def all_paragraphs():
    for p in D.paragraphs:
        yield p
    for t in D.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    yield p


def append_sentence(p, segments):
    """segments: list of (text, url or None); plain text in the paragraph's body format."""
    base = None
    for r in p._p.findall(qn('w:r')):
        rp = r.find(qn('w:rPr'))
        if rp is None or rp.find(qn('w:u')) is None:
            base = rp; break
    for text, url in segments:
        if url:
            p._p.append(make_link(D.part, url, text, link_rpr(base, code=not url.startswith(GH + '/releases'))))
        else:
            p._p.append(make_run(text, base))


def find(prefix):
    for p in D.paragraphs:
        if p.text.startswith(prefix) and not p.style.name.startswith('TFM Contents'):
            return p
    raise KeyError(prefix)


# ---- 1. data-availability paragraphs (only once)
p = find('All code, frozen databases and analysis outputs are openly available')
if 'data-v6-v8' not in p.text:
    append_sentence(p, [(' Later stages are in ', None), ('06_database_corrections_v6', None), (' (V6 corrections of the database and analysis tables), ', None),
                        ('07_train_improvement_v7', None), (' (exploratory analysis of the prediction limits) and ', None),
                        ('08_chlorophyll_target', None), (' (leaf chlorophyll as a third target, V8); the corrected V6 databases and the TRAIN_DEV '
                                                        'database with the chlorophyll tables are attached to the release data-v6-v8 (', None),
                        (REL, REL), (').', None)])
p = find('Data and code availability.')
if 'data-v6-v8' not in p.text:
    append_sentence(p, [(' Three further folders document the work after V5: ', None), ('06_database_corrections_v6', None),
                        (' (V6: errors found by re-checking the database against the full texts, corrected analysis tables and a cell-level change log), ', None),
                        ('07_train_improvement_v7', None), (' (exploratory analysis of why the models do not beat the mean) and ', None),
                        ('08_chlorophyll_target', None), (' (V8: extraction protocol and agent prompts, chlorophyll analysis tables, comparable '
                                                        'cross-validation of four targets, model freeze, TEST evaluation, meta-analysis and figures). The V6 '
                                                        'databases and the TRAIN_DEV database with the chlorophyll tables are attached to the release ', None),
                        (REL, REL), ('.', None)])

# ---- 2. plain repository paths -> links
for p in all_paragraphs():
    linkify_paragraph(p._p, D.part)

D.save(DOCX)
print('links added:', n_links, '| unresolved paths:', sorted(set(missing)))
