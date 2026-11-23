"""Updates the page numbers of the static contents list of the TFM document from a LibreOffice PDF rendering.
Usage: python c19_update_toc.py <docx> <workdir>   (the docx is modified in place)"""
import sys, re, subprocess, pathlib
import fitz
import docx
from docx.oxml.ns import qn

DOCX, WORK = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
SOFFICE = r'C:\Program Files\LibreOffice\program\soffice.exe'
norm = lambda s: re.sub(r'\s+', ' ', s).strip()

for it in range(2):
    subprocess.run([SOFFICE, '--headless', '--convert-to', 'pdf', '--outdir', str(WORK), str(DOCX)], check=True, capture_output=True)
    pdf = fitz.open(WORK / (DOCX.stem + '.pdf'))
    pages = []
    for pg in pdf:
        lines = [l.strip() for l in pg.get_text().split('\n') if l.strip()]
        num = next((l for l in reversed(lines) if re.fullmatch(r'\d+', l)), None)
        pages.append((norm(' '.join(lines)), num))
    from collections import Counter
    off = Counter(i - int(n) for i, (_, n) in enumerate(pages) if n and int(n) < 1000).most_common(1)[0][0]
    pages = [(t, str(i - off) if i - off >= 1 else n) for i, (t, n) in enumerate(pages)]
    d = docx.Document(DOCX)
    toc = [p for p in d.paragraphs if p.style.name.startswith('TFM Contents')]
    toc_end = max(i for i, (t, _) in enumerate(pages) if 'Contents' in t[:200] or i < 3) + 3
    changed = 0
    for p in toc:
        title = norm(p.text.rsplit('\t', 1)[0]); key = title[:45]
        hit = next((n for t, n in pages[toc_end:] if key in t), None)
        if hit is None:
            print('not found:', title); continue
        r = p._p.findall(qn('w:r'))[-1]; t = r.findall(qn('w:t'))[-1]
        if t.text != hit:
            t.text = hit; changed += 1
    d.save(DOCX)
    print('iteration', it, 'changed', changed, 'pages', pdf.page_count)
    pdf.close()
    if changed == 0:
        break
