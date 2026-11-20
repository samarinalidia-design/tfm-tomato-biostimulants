# -*- coding: utf-8 -*-
"""Editorial pass on the user's 'ready to submit' TFM: replace local paths by GitHub repository paths and links,
remove drafting leftovers, fix internal inconsistencies, add a data/code availability paragraph and a data citation,
and leave the remaining recommendations as Word comments. The input file is not modified."""
import copy, re, pathlib
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.text.paragraph import Paragraph

M = pathlib.Path(r"C:\Users\lenovo\Desktop\master's")
SRC = M / 'TFM_Agrobiologia_Ambiental_ready_to_submit (1).docx'
OUT = M / 'TFM_Agrobiologia_Ambiental_ready_to_submit_EDITED_github.docx'
REPO = M / 'TFM_GITHUB_REPO'
GH = 'https://github.com/samarinalidia-design/tfm-tomato-biostimulants'
REL = f'{GH}/releases/tag/data-freeze-v5'
AUTHOR, INI = 'Claude (editor)', 'CE'
log = []

# ---------- sentence-level edits (applied first, on the original wording) ----------
SENT = [
    ("All file paths in this chapter are relative to the project folder C:\\Users\\lenovo\\Desktop\\master's.",
     f"All code, frozen databases and analysis outputs are openly available in the GitHub repository {GH}; the complete SQLite databases are "
     f"attached to its release data-freeze-v5 ({REL}). All file paths given in this chapter are relative to the root of that repository."),
    ("(wf_source_receipts; images in TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/work/source_views)",
     "(wf_source_receipts; the page images are kept locally and are not redistributed because the articles are copyrighted)"),
    ("The frozen databases are TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z/"
     "TFM_DATABASE_CLASS_A_FINAL.sqlite (TRAIN_DEV) and TFM_TEST_2024_2026_Agent_System/exports/DATA_FREEZE_20261118T105532769144Z/"
     "TFM_DATABASE_CLASS_A_FINAL.sqlite (EXTERNAL_TEST).",
     f"The frozen databases (TFM_DATABASE_CLASS_A_FINAL.sqlite, TRAIN_DEV and EXTERNAL_TEST) are attached to the release {REL}; "
     "their exported tables are in 03_data_freeze."),
    (" This figure replaces the Spanish infographic of the earlier draft.", ""),
    ("Update: the historical PRISMA snapshot shown in earlier drafts has been replaced by the current flow diagram of studies and contrasts for both TRAIN and TEST, reported in Section 4.1",
     "The flow diagram of studies and contrasts for both TRAIN and TEST is reported in Section 4.1"),
    ("Update (test corpus). ", "External test corpus. "),
    ("Update (yield definitions, V5). ", "Yield definitions (V5). "),
    ("Update: source-verified corrections in the V5 analysis tables. ", "Source-verified corrections in the V5 analysis tables. "),
    ("Contrasts without reported variance (update)", "Contrasts without reported variance"),
    ("Meta-analysis (update). ", "Meta-analysis. "),
    ("Update (V5 analysis tables). ", "V5 analysis tables. "),
    ("Candidate models (update). ", "Candidate models. "),
    ("Update: a systematic sensitivity analysis", "In addition, a systematic sensitivity analysis"),
    ("Semantic verification consists of one main structured pass and a targeted review of the critical fields:",
     "Semantic verification combines the two independent extraction passes described in Section 3.6 with a targeted review of the critical fields:"),
    ("compares the observed effect of the combination with the effect expected if the two products acted additively.",
     "compares the observed effect of the combination with the effect expected if the two products acted independently "
     "(multiplicative reference on the original scale, i.e. additive on the log scale; Section 3.9)."),
    ("combining two biostimulants rarely produced more than the sum of their effects;",
     "combining two biostimulants rarely produced more than expected from the separate products under the multiplicative reference;"),
    ("The intervals remained close to their nominal coverage, so the uncertainty statements can be trusted.",
     "Interval coverage (0.897 for yield, 0.899 for biomass) stayed close to, but just below, the predefined 0.90 threshold, so the "
     "uncertainty statements are approximately, but not fully, calibrated for later studies."),
    ("Average effects, factorial interactions, model accuracy, interval coverage, applicability and treatment choice are evaluated as different properties of the evidence.",
     "Average effects, factorial interactions, model accuracy, interval coverage, applicability and treatment choice are evaluated as different properties of the evidence. "
     "The evidence database, the extraction system and the analysis code are openly available (Samarina, 2026; Section 3.18)."),
]
# ---------- path mapping (local project folder -> repository) ----------
PATHS = [
    ('TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z', '03_data_freeze/train_dev_DATA_FREEZE_20261113T112939135807Z'),
    ('TFM_TEST_2024_2026_Agent_System/exports/DATA_FREEZE_20261118T105532769144Z', '03_data_freeze/external_test_DATA_FREEZE_20261118T105532769144Z'),
    ('TFM_A399_Agent_System_v2_2_2026-10-19/SynerPlant_Yield_V4_HARMONIZATION', '04_analysis_history/SynerPlant_Yield_V4_HARMONIZATION'),
    ('TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2', '01_agent_system_train_dev'),
    ('TFM_TEST_2024_2026_Agent_System', '02_agent_system_external_test'),
    ('TFM_TRAIN_EXPANSION/v5', '05_analysis_train_expansion_v5/v5'),
]


def runs_text(p):
    return ''.join(r.text for r in p.runs)


def replace_across_runs(p, old, new):
    """Replace one occurrence of `old` spanning any runs; new text inherits the first touched run's formatting."""
    full = runs_text(p)
    i = full.find(old)
    if i < 0:
        return False
    j, pos = i + len(old), 0
    first = True
    for r in p.runs:
        a, b = pos, pos + len(r.text)
        pos = b
        if b <= i or a >= j:
            continue
        s, e = max(i, a) - a, min(j, b) - a
        if first:
            r.text = r.text[:s] + new + r.text[e:]
            first = False
        else:
            r.text = r.text[:s] + r.text[e:]
    return True


def all_paragraphs(doc):
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    yield p


def repo_url(path):
    q = path.strip().split(' ')[0].rstrip('/.,;:)')
    if '*' in q or not q.startswith('0'):
        return None
    f = REPO / q
    if f.is_dir():
        return f'{GH}/tree/main/{q}'
    if f.is_file():
        return f'{GH}/blob/main/{q}'
    return None


def make_link(par, r, url, text):
    """Insert a hyperlink (copying the run formatting, blue + underlined) before run r."""
    rid = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement('w:hyperlink'); h.set(qn('r:id'), rid)
    nr = copy.deepcopy(r._r)
    for t in nr.findall(qn('w:t')):
        nr.remove(t)
    rpr = nr.find(qn('w:rPr'))
    if rpr is None:
        rpr = OxmlElement('w:rPr'); nr.insert(0, rpr)
    for tag in ('w:color', 'w:u'):
        for e in rpr.findall(qn(tag)):
            rpr.remove(e)
    c = OxmlElement('w:color'); c.set(qn('w:val'), '1F4E79'); rpr.append(c)
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); rpr.append(u)
    t = OxmlElement('w:t'); t.text = text; t.set(qn('xml:space'), 'preserve'); nr.append(t)
    h.append(nr)
    r._r.addprevious(h)


def plain_run_before(r, text):
    nr = copy.deepcopy(r._r)
    for t in nr.findall(qn('w:t')):
        nr.remove(t)
    t = OxmlElement('w:t'); t.text = text; t.set(qn('xml:space'), 'preserve'); nr.append(t)
    r._r.addprevious(nr)


URL_RE = re.compile(r'https://[^\s;,()]+[^\s;,().]')
PATH_RE = re.compile(r'0[0-5]_[A-Za-z0-9_./\-]+')


def linkify(par):
    n = 0
    for r in list(par.runs):
        txt = r.text
        if not txt:
            continue
        pieces, last = [], 0
        for m in sorted(list(URL_RE.finditer(txt)) + [x for x in PATH_RE.finditer(txt) if repo_url(x.group(0))], key=lambda m: m.start()):
            if m.start() < last:
                continue
            url = m.group(0) if m.group(0).startswith('https://') else repo_url(m.group(0))
            pieces.append((txt[last:m.start()], None)); pieces.append((m.group(0).rstrip('.'), url))
            last = m.start() + len(m.group(0).rstrip('.'))
        if not pieces:
            continue
        pieces.append((txt[last:], None))
        for text, url in pieces:
            if not text:
                continue
            if url:
                make_link(par, r, url, text); n += 1
            else:
                plain_run_before(r, text)
        r._r.getparent().remove(r._r)
    return n


def clone_paragraph_after(p, text):
    new = copy.deepcopy(p._p)
    for child in list(new):
        if child.tag != qn('w:pPr'):
            new.remove(child)
    p._p.addnext(new)
    np_ = Paragraph(new, p._parent)
    tpl = p.runs[0]._r
    nr = copy.deepcopy(tpl)
    for t in nr.findall(qn('w:t')):
        nr.remove(t)
    t = OxmlElement('w:t'); t.text = text; t.set(qn('xml:space'), 'preserve'); nr.append(t)
    new.append(nr)
    return np_


def main():
    doc = docx.Document(str(SRC))
    # 1. sentence-level edits
    for old, new in SENT:
        hits = sum(replace_across_runs(p, old, new) for p in all_paragraphs(doc) if old in runs_text(p))
        log.append(('sentence', old[:70], hits))
    # 1b. table-of-contents entry (text sits inside field/hyperlink runs)
    for p in doc.paragraphs:
        if p.style.name.startswith('TFM Contents'):
            for t in p._p.iter(qn('w:t')):
                if t.text and ' (update)' in t.text:
                    t.text = t.text.replace(' (update)', ''); log.append(('toc entry', t.text, 1))
    # 2. table 11 cell where '*' was lost by the earlier markup conversion
    for p in all_paragraphs(doc):
        if runs_text(p) == 'results/v5_cv_.csv, v5_cv_oof_.parquet':
            for r in p.runs[1:]:
                r.text = ''
            p.runs[0].text = 'results/v5_cv_*.csv, v5_cv_oof_*.parquet'; p.runs[0].italic = False
            log.append(('table11 wildcard fix', '', 1))
    # 3. path mapping
    for p in all_paragraphs(doc):
        for r in p.runs:
            for a, b in PATHS:
                if a in r.text:
                    r.text = r.text.replace(a, b)
    # 4. data and code availability paragraph after the first paragraph of 3.18
    P = doc.paragraphs
    i318 = next(i for i, p in enumerate(P) if p.style.name.startswith('Heading') and p.text.startswith('3.18.'))
    avail = clone_paragraph_after(P[i318 + 1],
        'The repository ' + GH + ' contains the following folders: 00_extraction_notebooks_v4_3 (deterministic document-extraction layer V4.3); '
        '01_agent_system_train_dev (multi-agent extraction and verification system used for TRAIN_DEV: agent definitions, guard hooks, the validating '
        'command-line tool, configuration, JSON schemas and tests); 02_agent_system_external_test (the same system for EXTERNAL_TEST); 03_data_freeze '
        '(frozen exports of both databases: analysis marts, evidence_long, contrast_candidates, covariance of shared controls, QA tables and freeze '
        'manifests with SHA-256); 04_analysis_history (earlier analysis stages V2 and V4); and 05_analysis_train_expansion_v5/v5 (V5 analysis: scripts, '
        'analysis tables, frozen models, results and figures). The complete relational databases (SQLite and Excel, TRAIN_DEV and EXTERNAL_TEST) are '
        f'attached to the release {REL}. Full texts, supplements and page images of the source articles are not redistributed; every value can be '
        'located in the original publication through its DOI, page and locator.')
    lab = copy.deepcopy(avail.runs[0]._r); avail.runs[0]._r.addprevious(lab)
    lab_run = avail.runs[0]; lab_run.text = 'Data and code availability. '; lab_run.bold = True
    log.append(('availability paragraph', '', 1))
    # 5. data citation in the reference list (alphabetical: before Sariñana-Aldaco)
    ref = next(p for p in doc.paragraphs if p.style.name == 'TFM Reference' and p.text.startswith('Sariñana-Aldaco'))
    prev = ref._p.getprevious()
    prev_par = Paragraph(prev, ref._parent)
    clone_paragraph_after(prev_par, 'Samarina, L. (2026). tfm-tomato-biostimulants: evidence database, AI-assisted extraction system and analysis code '
                          f'for biostimulant efficacy in tomato under stress (data freeze V5) [Data set and software]. GitHub. {GH}')
    log.append(('reference added', 'Samarina 2026', 1))
    # 6. hyperlinks for URLs and repository paths (body, tables; references keep their own DOIs as text)
    nl = 0
    for p in all_paragraphs(doc):
        if p.style.name == 'TFM Reference' and 'samarinalidia' not in p.text:
            continue
        if 'github.com' in p.text or PATH_RE.search(p.text):
            nl += linkify(p)
    log.append(('hyperlinks inserted', '', nl))
    # 7. editorial comments
    def comment(pred, text):
        p = next((p for p in doc.paragraphs if pred(p)), None)
        if p is None or not p.runs:
            log.append(('comment NOT placed', text[:50], 0)); return
        doc.add_comment(p.runs[0], text=text, author=AUTHOR, initials=INI); log.append(('comment', text[:60], 1))
    comment(lambda p: p.text.startswith('Biostimulants can improve tomato performance'),
            'Suggestion: the abstract does not mention the AI-assisted (Claude multi-agent) extraction and verification system or that data and code are '
            'open. If the word limit allows, add one sentence, e.g. "The evidence base was built with a verified multi-agent extraction pipeline and is openly '
            'available with all code (GitHub, release data-freeze-v5)."')
    comment(lambda p: p.style.name == 'TFM Front Heading' and p.text.strip() == 'Contents',
            'Update the table of contents (right-click → Update field → entire table): one heading changed (3.9.1, "(update)" removed) and page numbers '
            'shift after the edits.')
    comment(lambda p: p.text.startswith('Of 39 627 records identified'),
            'Number style is inconsistent: Methods/Results use thin-space thousands and a space before % ("39 627", "1 452", "95 %"), while Abstract, '
            'Introduction and Discussion use commas and no space ("1,452", "45%"); Section 3.6 also uses "12,011". UK/English style: "1,452" and "45%". '
            'Recommend unifying throughout (Find & Replace).')
    comment(lambda p: p.text.startswith('This methodology describes a reproducible pipeline'),
            'Formatting: Sections 3–4 use the style "normal" with 10.5 pt text, whereas Sections 1–2 and 5–7 use "TFM Body" (11 pt). Consider applying '
            '"TFM Body" to the body paragraphs of Sections 3–4 (not to captions or equations) so that the whole thesis has the same font size and spacing.')
    comment(lambda p: p.text.startswith('Document management used Google Drive'),
            'Software citations are missing from the reference list: R Core Team (2025) R: A language and environment for statistical computing; '
            'Pustejovsky clubSandwich package; Docling (Auer et al., 2024, arXiv:2408.09869); PyMuPDF; and the language models used for extraction '
            '(Anthropic, Claude Opus / Sonnet, model versions and dates as recorded in wf_runs). Consider adding them.')
    comment(lambda p: p.text.startswith('Semantic verification combines the two independent'),
            'Edited: the previous wording ("one main structured pass") contradicted Section 3.6, which describes two independent passes (A and B) '
            'reconciled in code.')
    comment(lambda p: 'acted independently (multiplicative reference' in p.text,
            'Edited: "additively" was inconsistent with the multiplicative reference used in Sections 1.4, 3.9, 5.4 and Annex C.')
    comment(lambda p: 'Interval coverage (0.897 for yield' in p.text,
            'Edited: the previous sentence ("can be trusted") overstated the result; coverage narrowly failed the predefined 0.90 criterion (Section 5.6).')
    doc.save(str(OUT))
    for row in log:
        print(row)


if __name__ == '__main__':
    main()
