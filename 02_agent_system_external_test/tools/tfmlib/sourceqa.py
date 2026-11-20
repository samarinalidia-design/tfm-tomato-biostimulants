"""Original-file inventory, deterministic views and immutable evidence receipts.
A receipt proves the bytes/view, not the correctness of an agent's interpretation.
"""
from __future__ import annotations
import csv, hashlib, json, re
from pathlib import Path
from .db import rows, now, sha256_file, tx

def expected(cfg):
    with (cfg.root/cfg.get('scope.source_manifest','manifests/source_manifest_A_462.csv')).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def frozen_ids(cfg):
    with (cfg.root/cfg.get('scope.manifest','manifests/scope_A_399.csv')).open(encoding='utf-8-sig',newline='') as f:
        return {r['study_id'] for r in csv.DictReader(f)}

def index_sources(con,cfg):
    roots=[p for p in (cfg.p('fulltext_root'),cfg.p('supplements_root')) if p and p.is_dir()]
    paths=sorted({p.resolve() for root in roots for p in root.rglob('*') if p.is_file()})
    indexed=[]
    with tx(con):
        for r in expected(cfg):
            fid=r['active_file_id']; name=r['active_file_name']
            hits=[p for p in paths if p.name==name or fid in p.name or fid in p.parts]
            # A Drive filename can contain just the first 8 ID characters, but use that only
            # with exact active filename or an unambiguous study prefix, never arbitrary fuzzy IDs.
            if not hits:
                short=fid[:8]
                sid=r['study_id']; sp=sid.zfill(4) if sid.isdigit() else sid
                token=re.compile(r'(?<![A-Za-z0-9])'+re.escape(sp)+r'(?![A-Za-z0-9])')
                hits=[p for p in paths if short in p.name and token.search(p.name)]
            unique={sha256_file(p):p for p in hits}
            status='OK' if len(unique)==1 else ('MISSING' if not hits else 'AMBIGUOUS')
            path=next(iter(unique.values())) if status=='OK' else None
            sha=next(iter(unique)) if status=='OK' else None
            old=con.execute('SELECT sha256 FROM wf_sources WHERE source_file_id=?',(fid,)).fetchone()
            if old and old[0] and sha and old[0]!=sha:
                status='CHANGED'; path=None
            con.execute('INSERT INTO wf_sources(source_file_id,study_id,role,file_name,path,sha256,status,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_file_id) DO UPDATE SET path=excluded.path,sha256=COALESCE(wf_sources.sha256,excluded.sha256),status=excluded.status,updated_at=excluded.updated_at',
                        (fid,r['study_id'],r['role'],name,str(path) if path else None,sha,status,now()))
            indexed.append({'source_file_id':fid,'study_id':r['study_id'],'status':status,'matches':len(hits)})
    return {'expected':len(indexed),'ok':sum(r['status']=='OK' for r in indexed),'problems':[r for r in indexed if r['status']!='OK']}

from functools import lru_cache
@lru_cache(maxsize=4096)
def _hash_cached(path,mtime,size):
    return sha256_file(Path(path))
def current_hash(path):
    p=Path(path);stat=p.stat()
    return _hash_cached(str(p),stat.st_mtime_ns,stat.st_size)

def get_source(con,cfg,fid):
    r=(rows(con,'SELECT * FROM wf_sources WHERE source_file_id=?',(fid,)) or [None])[0]
    if not r or r['status']!='OK' or not r['path']:
        raise ValueError(f'original source {fid} not indexed/available; run source-index')
    p=Path(r['path'])
    if not p.is_file() or current_hash(p)!=r['sha256']:
        raise ValueError(f'original source {fid} changed or unavailable')
    return r,p

def libreoffice_binary():
    import shutil,os
    found=shutil.which('soffice') or shutil.which('libreoffice')
    if found:return found
    candidates=[Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')]
    for key in ('PROGRAMFILES','PROGRAMFILES(X86)'):
        if os.environ.get(key):candidates.append(Path(os.environ[key])/'LibreOffice/program/soffice.exe')
    return str(next((p for p in candidates if p.is_file()),'')) or None

def converted_pdf(original,dest):
    import subprocess
    binary=libreoffice_binary()
    if not binary:raise ValueError('LibreOffice is required for the original legacy DOC supplement; install it once and rerun preflight')
    pdf=dest/(original.stem+'.pdf')
    if not pdf.exists():
        import shutil,tempfile,time
        # The project path contains an apostrophe and the corpus path Cyrillic text, so
        # LibreOffice works on a temporary ASCII copy; the original stays untouched.
        with tempfile.TemporaryDirectory(prefix='tfm_lo_') as td:
            work=Path(td);source=work/('source'+original.suffix.lower());shutil.copyfile(original,source)
            profile=work/'lo_profile';(profile/'user').mkdir(parents=True,exist_ok=True)
            (profile/'user/registrymodifications.xcu').write_text('<oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item></oor:items>',encoding='utf-8')
            console=Path(binary).with_suffix('.com')
            cmd=[str(console) if console.is_file() else binary,'-env:UserInstallation='+profile.resolve().as_uri(),'--headless','--convert-to','pdf','--outdir',str(work),str(source)]
            run=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            made=work/'source.pdf';deadline=time.time()+60
            while not made.exists() and time.time()<deadline:time.sleep(1)
            if not made.exists():raise ValueError(f'read-only original-to-PDF conversion failed: exit={run.returncode} '+(run.stderr or run.stdout)[-500:])
            shutil.copyfile(made,pdf)
    return pdf

def _sheet_by_index(path,suffix,index):
    """Resolve a 1-based sheet number: some sheet names hold characters the command guard rejects."""
    if suffix=='.xls':
        import xlrd
        wb=xlrd.open_workbook(path,on_demand=True);names=wb.sheet_names();wb.release_resources()
    elif suffix in ('.xlsx','.xlsm'):
        from openpyxl import load_workbook
        wb=load_workbook(path,read_only=True);names=list(wb.sheetnames);wb.close()
    else:raise ValueError('--sheet-index applies only to workbooks')
    if not 1<=int(index)<=len(names):raise ValueError('sheet index out of range; available='+str(names))
    return names[int(index)-1]

IMAGE_SUFFIXES=('.tif','.tiff','.png','.jpg','.jpeg')

def view(con,cfg,fid,page=None,sheet=None,cell_range=None,dpi=180,sheet_index=None):
    if not 72<=int(dpi)<=600:raise ValueError('render DPI must be between 72 and 600')
    r,p=get_source(con,cfg,fid)
    suffix=p.suffix.lower()
    if sheet_index is not None:sheet=_sheet_by_index(p,suffix,sheet_index)
    viewkey=f'{fid}|{r["sha256"]}|{page}|{sheet}|{cell_range}|{int(dpi)}'
    receipt='SRC-'+hashlib.sha256(viewkey.encode()).hexdigest()[:24]
    dest=cfg.work_dir/'source_views'/receipt; dest.mkdir(parents=True,exist_ok=True)
    text=''; assets=[];conversion=None
    render_path=p
    if suffix=='.doc' or (suffix=='.docx' and page is not None):
        render_path=converted_pdf(p,dest);assets.append(str(render_path));conversion={'method':'LibreOffice read-only copy to PDF','converted_sha256':sha256_file(render_path)}
    # Maintenance 2026-11-15: an original that is a plain-text table saved with a legacy .xls name
    # (no OLE2 header) is read read-only as tab-separated text; the bytes are not altered.
    text_table=False
    if suffix=='.xls':
        with p.open('rb') as fh:head=fh.read(8)
        text_table=head!=b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    if suffix in IMAGE_SUFFIXES:
        # Maintenance 2026-11-15: original raster supplements (TIFF/PNG/JPEG) open as image pages in
        # PyMuPDF (multi-page TIFF -> one page per frame) and render like PDF pages.
        conversion={'method':'PyMuPDF read-only image page render','converted_sha256':None}
    if suffix=='.pdf' or conversion:

        import fitz
        if not page or page<1: raise ValueError('PDF view requires --page >= 1 (physical PDF page)')
        with fitz.open(render_path) as pdf:
            if page>len(pdf): raise ValueError('page beyond PDF length')
            pg=pdf[page-1]
            im=dest/f'page-{page}.png'; pg.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False).save(im)
            text=pg.get_text(); assets.append(str(im))
    elif suffix in ('.xlsx','.xlsm','.xls') and not text_table:
        from openpyxl import load_workbook
        if not sheet or not cell_range: raise ValueError('supplement workbook requires --sheet and --range')
        from openpyxl.utils.cell import range_boundaries
        x1,y1,x2,y2=range_boundaries(cell_range)
        if (x2-x1+1)*(y2-y1+1)>5000: raise ValueError('view <=5000 cells; do not materialize omics arrays')
        if suffix=='.xls':
            import xlrd
            wb=xlrd.open_workbook(p,on_demand=True)
            if sheet not in wb.sheet_names():raise ValueError('unknown legacy sheet; available='+str(wb.sheet_names()))
            ws=wb.sheet_by_name(sheet)
            values=[[ws.cell_value(y,x) if y<ws.nrows and x<ws.ncols else None for x in range(x1-1,x2)] for y in range(y1-1,y2)];wb.release_resources()
        else:
            wb=load_workbook(p,read_only=True,data_only=True)
            if sheet not in wb.sheetnames:raise ValueError('unknown sheet; available='+str(wb.sheetnames))
            values=[[c.value for c in row] for row in wb[sheet].iter_rows(min_col=x1,max_col=x2,min_row=y1,max_row=y2)];wb.close()
        text=json.dumps({'sheet':sheet,'range':cell_range,'values':values},ensure_ascii=False,default=str)
    elif suffix in ('.csv','.tsv') or text_table:
        if not cell_range or not re.fullmatch(r'\d+:\d+',cell_range): raise ValueError('CSV/TSV (and text-table .xls) requires --range start_row:end_row (1 based)')
        a,b=map(int,cell_range.split(':'))
        if a<1 or b<a or b-a>100: raise ValueError('select <=101 rows; omics matrices are not extraction targets')
        raw=p.read_bytes()
        for enc in ('utf-8-sig','cp1252','latin-1'):
            try:decoded=raw.decode(enc);break
            except UnicodeDecodeError:continue
        import io
        delim='\t' if (suffix=='.tsv' or text_table) else ','
        data=[row for i,row in enumerate(csv.reader(io.StringIO(decoded,newline=''),delimiter=delim),1) if a<=i<=b]
        if text_table:conversion={'method':'read-only text-table read of legacy-named .xls (no OLE2 header), tab-separated, encoding '+enc,'converted_sha256':None}
        text=json.dumps(data,ensure_ascii=False)
    elif suffix=='.docx':
        from docx import Document
        d=Document(p); parts=[x.text for x in d.paragraphs]
        for i,t in enumerate(d.tables,1):
            parts.append(f'TABLE {i}')
            parts.extend('\t'.join(c.text for c in row.cells) for row in t.rows)
        text='\n'.join(parts)
        if len(text)>250000: raise ValueError('large DOCX: export original to PDF for bounded views')
    else:
        raise ValueError('unsupported original format; convert a read-only copy to PDF/XLSX and register conversion with original hash')
    txt=dest/'original_view.txt';txt.write_text(text,encoding='utf-8');assets.append(str(txt))
    payload={'receipt_id':receipt,'study_id':r['study_id'],'source_file_id':fid,'source_sha256':r['sha256'],'page':page,'sheet':sheet,'cell_range':cell_range,'render_dpi':int(dpi),'assets':assets,'asset_sha256':{a:sha256_file(Path(a)) for a in assets},'conversion':conversion,'note':'Read the PNG for PDF; extracted text alone is not a visual verification.'}
    (dest/'receipt.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    with tx(con):
        con.execute('INSERT OR REPLACE INTO wf_source_receipts(receipt_id,study_id,source_file_id,source_sha256,page,sheet,cell_range,payload,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (receipt,r['study_id'],fid,r['sha256'],page,sheet,cell_range,json.dumps(payload,ensure_ascii=False),now()))
    return payload

def check_receipt(con,cfg,study,fid,rid,page=None):
    r=(rows(con,'SELECT * FROM wf_source_receipts WHERE receipt_id=?',(rid,)) or [None])[0]
    if not r or r['study_id']!=study or r['source_file_id']!=fid:
        raise ValueError('receipt must match this study and original source_file_id')
    src,p=get_source(con,cfg,fid)
    if r['source_sha256']!=src['sha256']: raise ValueError('receipt is stale')
    payload=json.loads(r['payload'])
    for path,digest in payload.get('asset_sha256',{}).items():
        if not Path(path).is_file() or current_hash(Path(path))!=digest:raise ValueError('receipt view was changed or lost; re-render and reverify')
    if page is not None and r['page'] is not None and int(page)!=int(r['page']): raise ValueError('receipt physical page mismatch')
    return r
