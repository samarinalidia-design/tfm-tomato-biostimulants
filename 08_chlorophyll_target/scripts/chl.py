"""Chlorophyll pilot - command-line tools for extraction agents (source access with receipts and calibrated digitisation).

Every number an agent reports must come from (i) a printed table/text cell it has viewed on a rendered page, or (ii) the
`fit` command applied to pixel/PDF coordinates it located on a rendered figure. Values are never typed in from memory.

  python chl.py packet  <study_id>                          study packet (files, chlorophyll locators, arms of the frozen design)
  python chl.py render  <study_id> <file_name> <page> [--dpi 220]   render a PDF page; returns image path and receipt id
  python chl.py text    <study_id> <file_name> <page>              text layer of a page (to read printed numbers; confirm on the image)
  python chl.py probe   <study_id> <file_name> <page> [--bbox x0,y0,x1,y1]   vector shapes/texts of a figure (pdf_pt coordinates)
  python chl.py grid    <image> [--bbox x0,y0,x1,y1] [--step 25] [--zoom 2]  zoomed crop with a labelled pixel grid
  python chl.py snap    <image> '<json points [{"x":..,"y":..,"offset":8}]>'  refine bar tops / caps to the nearest edge
  python chl.py fit     <panels.json>                       axis calibration (>= 3 ticks) -> values; writes <panels>.fit.json
  python chl.py check   <outbox.json>                       validate an extraction file against the pilot schema
Work dir: C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work (override with env CHL_WORK).
"""
import sys, os, json, hashlib, pathlib, datetime, argparse

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))
PASS = os.environ.get('CHL_PASS', 'X')          # A, B or ADJ: keeps the passes' files apart
A399_TOOLS = pathlib.Path(r"C:/Users/lenovo/Desktop/master's/TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/tools")
sys.path.insert(0, str(A399_TOOLS))
from tfmlib.figures import fit_axis, point_values, calibration_status, grid_overlay, snap_vertical, vector_probe, CalibrationError  # noqa: E402

MEASURES = {'CHL_TOTAL', 'CHL_A', 'CHL_B', 'CHL_A_PLUS_B_PRINTED', 'SPAD', 'OTHER_CHL_INDEX'}
BASIS = {'FRESH_MASS', 'DRY_MASS', 'LEAF_AREA', 'EXTRACT_VOLUME', 'INDEX', 'UNSPECIFIED'}
DISP = {'SD', 'SE', 'CI95', 'UNLABELLED', 'NOT_REPORTED', 'OTHER'}
SOURCE = {'TABLE', 'FIGURE', 'TEXT'}


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def packet(study):
    p = WORK / 'packets' / f'{study}.json'
    if not p.exists():
        sys.exit(f'no packet for {study}')
    return json.loads(p.read_text(encoding='utf-8'))


def file_of(study, name):
    pk = packet(study)
    f = next((f for f in pk['files'] if f['file_name'] == name), None)
    if f is None:
        sys.exit(f'{name} is not a registered file of {study}: ' + ', '.join(x['file_name'] for x in pk['files']))
    path = pathlib.Path(f['local_path'])
    if sha(path) != f['sha256']:
        sys.exit(f'SHA-256 mismatch for {path}')
    return path, f


def out(x):
    print(json.dumps(x, indent=1, ensure_ascii=False, default=str))


def cmd_packet(a):
    out(packet(a.study))


def cmd_render(a):
    import fitz
    path, f = file_of(a.study, a.file_name)
    doc = fitz.open(str(path))
    if not 1 <= a.page <= len(doc):
        sys.exit(f'page {a.page} outside 1..{len(doc)}')
    pg = doc[a.page - 1]
    dest = WORK / 'views' / PASS / a.study
    dest.mkdir(parents=True, exist_ok=True)
    img = dest / f'{pathlib.Path(a.file_name).stem[:40]}_p{a.page}_{a.dpi}.png'
    pix = pg.get_pixmap(dpi=a.dpi)
    pix.save(str(img))
    rec = {'receipt_id': f'RC{PASS}-' + hashlib.sha1(f'{f["sha256"]}|{a.page}|{a.dpi}'.encode()).hexdigest()[:12], 'pass': PASS,
           'study_id': a.study, 'file_name': a.file_name, 'file_sha256': f['sha256'], 'page': a.page, 'dpi': a.dpi,
           'image': str(img), 'image_sha256': sha(img), 'width': pix.width, 'height': pix.height,
           'pdf_page_size_pt': [round(pg.rect.width, 2), round(pg.rect.height, 2)],
           'px_per_pt': round(a.dpi / 72, 4), 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}
    with open(WORK / f'receipts_{PASS}.jsonl', 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(rec) + '\n')
    out(rec)


def cmd_text(a):
    import fitz
    path, _ = file_of(a.study, a.file_name)
    doc = fitz.open(str(path))
    print(doc[a.page - 1].get_text())


def cmd_probe(a):
    path, _ = file_of(a.study, a.file_name)
    bbox = [float(x) for x in a.bbox.split(',')] if a.bbox else None
    res = vector_probe(path, a.page, bbox)
    dest = WORK / 'probes' / PASS / a.study
    dest.mkdir(parents=True, exist_ok=True)
    fn = dest / f'p{a.page}_{"full" if not bbox else "_".join(str(int(v)) for v in bbox)}.json'
    fn.write_text(json.dumps(res, indent=1), encoding='utf-8')
    out({'written': str(fn), 'texts': len(res['texts']), 'rects': len(res['rects']), 'lines': len(res['lines']),
         'coord_space': 'pdf_pt (multiply by dpi/72 for rendered pixels)', 'hint': res['hint']})


def cmd_grid(a):
    bbox = tuple(int(float(x)) for x in a.bbox.split(',')) if a.bbox else None
    img = pathlib.Path(a.image)
    o = img.with_name(img.stem + f'_grid_{"full" if not bbox else "_".join(map(str, bbox))}.png')
    out(grid_overlay(img, o, a.step, a.zoom, bbox))


def cmd_snap(a):
    out(snap_vertical(pathlib.Path(a.image), json.loads(a.points)))


def cmd_fit(a):
    """panels.json: {"panels":[{"panel":"Fig 2a","coord_space":"pixel|pdf_pt","receipt_id":"RC-..","axis":{"scale":"linear",
    "ticks":[{"px":812,"value":0},{"px":612,"value":1},...]},"points":[{"arm_key":"E1.SB","px_mean":540,"px_err_hi":520,"px_err_lo":560}]}]}"""
    src = pathlib.Path(a.file)
    data = json.loads(src.read_text(encoding='utf-8-sig'))
    res = []
    for p in data.get('panels', []):
        try:
            cal = fit_axis(p['axis']['ticks'], p['axis'].get('scale', 'linear'))
        except CalibrationError as exc:
            res.append({'panel': p.get('panel'), 'error': str(exc)}); continue
        st = calibration_status(cal, 3, 3, 0.015)
        pts = []
        for pt in p['points']:
            m, e, info = point_values(pt['px_mean'], pt.get('px_err_hi'), pt.get('px_err_lo'), cal)
            rel = (abs(cal['b']) * 1.0) / max(abs(m), 1e-12)          # value of one coordinate unit relative to the mean
            pts.append({**{k: v for k, v in pt.items() if not k.startswith('px')}, 'mean': round(m, 6),
                        'err_halfwidth': None if e is None else round(e, 6), 'rel_value_per_unit': round(rel, 5), **info})
        res.append({'panel': p.get('panel'), 'receipt_id': p.get('receipt_id'), 'coord_space': p.get('coord_space'),
                    'calibration': {k: (round(v, 6) if isinstance(v, float) else v) for k, v in cal.items()}, 'status': st, 'points': pts})
    dst = src.with_suffix('.fit.json')
    dst.write_text(json.dumps(res, indent=1), encoding='utf-8')
    out({'written': str(dst), 'panels': res})


def validate(doc):
    errs = []
    for k in ['study_id', 'pass', 'status', 'values']:
        if k not in doc:
            errs.append(f'missing {k}')
    if doc.get('pass') not in ('A', 'B', 'ADJ'):
        errs.append('pass must be A, B or ADJ')
    if doc.get('status') not in ('DONE', 'NO_CHLOROPHYLL_DATA', 'BLOCKED'):
        errs.append('status must be DONE, NO_CHLOROPHYLL_DATA or BLOCKED')
    receipts = set()
    for rp in WORK.glob('receipts_*.jsonl'):
        receipts |= {json.loads(l)['receipt_id'] for l in rp.read_text(encoding='utf-8').splitlines() if l.strip()}
    for i, v in enumerate(doc.get('values', [])):
        tag = f'values[{i}]'
        for k in ['experiment_key', 'arm_key', 'measure', 'basis', 'unit_raw', 'timepoint_label', 'mean', 'dispersion_type',
                  'source_kind', 'file_name', 'page', 'locator', 'receipt_id']:
            if k not in v:
                errs.append(f'{tag}: missing {k}')
        if v.get('measure') not in MEASURES: errs.append(f'{tag}: measure {v.get("measure")}')
        if v.get('basis') not in BASIS: errs.append(f'{tag}: basis {v.get("basis")}')
        if v.get('dispersion_type') not in DISP: errs.append(f'{tag}: dispersion_type {v.get("dispersion_type")}')
        if v.get('source_kind') not in SOURCE: errs.append(f'{tag}: source_kind {v.get("source_kind")}')
        if v.get('receipt_id') not in receipts: errs.append(f'{tag}: receipt_id {v.get("receipt_id")} not issued by render')
        if not isinstance(v.get('mean'), (int, float)): errs.append(f'{tag}: mean must be a number')
        if v.get('source_kind') == 'FIGURE' and not v.get('fit_file'):
            errs.append(f'{tag}: FIGURE values need fit_file (output of chl.py fit)')
        if v.get('source_kind') in ('TABLE', 'TEXT') and not v.get('verbatim'):
            errs.append(f'{tag}: TABLE/TEXT values need the verbatim printed cell')
    return errs


def cmd_check(a):
    doc = json.loads(pathlib.Path(a.file).read_text(encoding='utf-8-sig'))
    e = validate(doc)
    out({'file': a.file, 'valid': not e, 'errors': e[:50], 'n_values': len(doc.get('values', []))})
    sys.exit(0 if not e else 1)


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('packet'); s.add_argument('study'); s.set_defaults(f=cmd_packet)
    s = sp.add_parser('render'); s.add_argument('study'); s.add_argument('file_name'); s.add_argument('page', type=int); s.add_argument('--dpi', type=int, default=220); s.set_defaults(f=cmd_render)
    s = sp.add_parser('text'); s.add_argument('study'); s.add_argument('file_name'); s.add_argument('page', type=int); s.set_defaults(f=cmd_text)
    s = sp.add_parser('probe'); s.add_argument('study'); s.add_argument('file_name'); s.add_argument('page', type=int); s.add_argument('--bbox'); s.set_defaults(f=cmd_probe)
    s = sp.add_parser('grid'); s.add_argument('image'); s.add_argument('--bbox'); s.add_argument('--step', type=int, default=25); s.add_argument('--zoom', type=float, default=2.0); s.set_defaults(f=cmd_grid)
    s = sp.add_parser('snap'); s.add_argument('image'); s.add_argument('points'); s.set_defaults(f=cmd_snap)
    s = sp.add_parser('fit'); s.add_argument('file'); s.set_defaults(f=cmd_fit)
    s = sp.add_parser('check'); s.add_argument('file'); s.set_defaults(f=cmd_check)
    a = ap.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
