"""Chlorophyll pilot: reconcile pass A and pass B, write the adjudication queue and the agreed values.

Matching key: study, arm_key, measure, time point (timepoint_days when both passes give it, otherwise the normalised
label). Agreement rules (A399 conventions):
  TABLE/TEXT  means equal within half a unit of the last printed digit; dispersion type equal; n equal (or both null)
  FIGURE      |A - B| <= max(5 % of the mean, 2 % of the calibrated axis range) for the mean; two readings within the
              tolerance are averaged (author decision of 2026-11-05, no. 1); error half-widths within 15 %
Everything else (value conflicts, values found by one pass only, different study status, new arms) goes to
work/adjudication/<study_id>.json. If an adjudicated file work/outbox/ADJ/<study_id>.json exists it replaces the
conflicting items for that study.
Usage: python c04_reconcile.py
"""
import json, math, os, re, pathlib
import pandas as pd

WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))
OUT = pathlib.Path(__file__).resolve().parents[1]
TAG = os.environ.get('CHL_TAG', 'pilot')   # output prefix: pilot (50 studies) or all (pilot + full run)


def load(p):
    rows, meta = [], {}
    for f in sorted((WORK / 'outbox' / p).glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8-sig'))
        meta[d['study_id']] = d
        for i, v in enumerate(d.get('values', [])):
            rows.append({**v, 'study_id': d['study_id'], 'pass': p, 'idx': i})
    return pd.DataFrame(rows), meta


def tp_key(v):
    if v.get('timepoint_days') not in (None, '') and not (isinstance(v.get('timepoint_days'), float) and math.isnan(v['timepoint_days'])):
        return f"d{float(v['timepoint_days']):g}"
    return re.sub(r'[^a-z0-9]', '', str(v.get('timepoint_label', '')).lower())


def decimals(s):
    m = re.search(r'(\d+)[.,](\d+)', str(s))
    return len(m.group(2)) if m else 0


def axis_range(fit_file, arm):
    try:
        res = json.loads(pathlib.Path(fit_file).read_text(encoding='utf-8'))
        for p in res:
            if any(pt.get('arm_key') == arm for pt in p.get('points', [])):
                return p['calibration']['axis_range']
    except Exception:
        return None
    return None


def unstressed_arms():
    """(study, arm_key) of arms without stress (role C or B), from the packets and the new arms of every pass. Agents code
    during_stress inconsistently for these arms (per time point or per arm), so the flag is not compared for them."""
    out = set()
    for f in (WORK / 'packets').glob('*.json'):
        pk = json.loads(f.read_text(encoding='utf-8'))
        out |= {(pk['study_id'], a['arm_key']) for a in pk['design_from_A399']['arms'] if a.get('role') in ('C', 'B')}
    for p in ('A', 'B', 'ADJ'):
        for f in (WORK / 'outbox' / p).glob('*.json'):
            d = json.loads(f.read_text(encoding='utf-8-sig'))
            out |= {(d['study_id'], a.get('arm_key')) for a in (d.get('design_check', {}).get('new_arms') or []) if a.get('role') in ('C', 'B')}
    return out


UNSTRESSED = None


def agree(a, b):
    if a['source_kind'] != b['source_kind'] and 'FIGURE' in (a['source_kind'], b['source_kind']):
        tol_kind = 'FIGURE'
    else:
        tol_kind = 'FIGURE' if a['source_kind'] == 'FIGURE' else 'TABLE'
    ma, mb = float(a['mean']), float(b['mean'])
    if tol_kind == 'TABLE':
        dec = max(decimals(a.get('verbatim')), decimals(b.get('verbatim')))
        ok_mean = abs(ma - mb) <= 0.5 * 10 ** (-dec) + 1e-9
    else:
        rng = axis_range(a.get('fit_file'), a['arm_key']) or axis_range(b.get('fit_file'), b['arm_key'])
        tol = max(0.05 * max(abs(ma), abs(mb)), 0.02 * rng if rng else 0)
        ok_mean = abs(ma - mb) <= tol
    da, db = a.get('dispersion_type'), b.get('dispersion_type')
    ok_dtype = da == db
    va, vb = a.get('dispersion_value'), b.get('dispersion_value')
    if va is None or vb is None or (isinstance(va, float) and math.isnan(va)) or (isinstance(vb, float) and math.isnan(vb)):
        ok_dval = (va is None or (isinstance(va, float) and math.isnan(va))) == (vb is None or (isinstance(vb, float) and math.isnan(vb)))
    else:
        ok_dval = abs(float(va) - float(vb)) <= (0.15 if tol_kind == 'FIGURE' else 0.005) * max(abs(float(va)), abs(float(vb)), 1e-9) + 1e-9
    na, nb = a.get('n'), b.get('n')
    nan = lambda x: x is None or (isinstance(x, float) and math.isnan(x))
    ok_n = (nan(na) and nan(nb)) or (not nan(na) and not nan(nb) and float(na) == float(nb))
    ok_basis = a.get('basis') == b.get('basis')
    ds_a, ds_b = a.get('during_stress'), b.get('during_stress')
    ok_ds = (nan(ds_a) and nan(ds_b)) or (not nan(ds_a) and not nan(ds_b) and bool(ds_a) == bool(ds_b))
    if not ok_ds and (a.get('study_id'), a.get('arm_key')) in UNSTRESSED:
        ok_ds = True
    return dict(mean=ok_mean, dispersion_type=ok_dtype, dispersion_value=ok_dval, n=ok_n, basis=ok_basis, during_stress=ok_ds, kind=tol_kind)


def main():
    global UNSTRESSED
    UNSTRESSED = unstressed_arms()
    A, mA = load('A'); B, mB = load('B'); ADJ, mJ = load('ADJ')
    studies = sorted(set(mA) | set(mB))
    agreed, queue, stats = [], {}, []
    for sid in studies:
        if sid in mJ:                                   # adjudicated study: the adjudicator's file is final for it
            for v in mJ[sid].get('values', []):
                agreed.append({**v, 'study_id': sid, 'reconcile': 'ADJUDICATED'})
            stats.append(dict(study_id=sid, status_A=mA.get(sid, {}).get('status'), status_B=mB.get(sid, {}).get('status'),
                              status_final=mJ[sid].get('status'), matched=None, agreed=None, conflicts=None, only_A=None, only_B=None,
                              adjudicated=True))
            continue
        a = A[A.study_id == sid].copy() if len(A) else pd.DataFrame(); b = B[B.study_id == sid].copy() if len(B) else pd.DataFrame()
        items = []
        if sid not in mA or sid not in mB:
            stats.append(dict(study_id=sid, status_A=mA.get(sid, {}).get('status'), status_B=mB.get(sid, {}).get('status'), pending=True))
            continue
        sa, sb = mA[sid]['status'], mB[sid]['status']
        if sa != sb:
            items.append({'issue': 'STATUS_DIFFERS', 'A': sa, 'B': sb, 'notes_A': mA[sid].get('notes'), 'notes_B': mB[sid].get('notes')})
        newA = mA[sid].get('design_check', {}).get('new_arms') or []; newB = mB[sid].get('design_check', {}).get('new_arms') or []
        if newA or newB:
            items.append({'issue': 'NEW_ARMS_PROPOSED', 'A': newA, 'B': newB})
        for df in (a, b):
            if len(df):
                df['k'] = df.apply(lambda r: (r.arm_key, r.measure, tp_key(r)), axis=1)
        used_b = set(); n_match = n_agree = 0
        for _, ra in a.iterrows() if len(a) else []:
            cand = b[(b.k == ra.k) & ~b.idx.isin(used_b)] if len(b) else pd.DataFrame()
            if cand.empty:
                items.append({'issue': 'ONLY_A', 'A': ra.drop(labels=['k']).to_dict()}); continue
            rb = cand.iloc[(cand['mean'].astype(float) - float(ra['mean'])).abs().argsort().iloc[0]]
            used_b.add(rb.idx); n_match += 1
            ag = agree(ra, rb)
            if all(ag[x] for x in ('mean', 'dispersion_type', 'dispersion_value', 'n', 'basis', 'during_stress')):
                n_agree += 1
                v = ra.drop(labels=['k', 'pass', 'idx']).to_dict()
                if ag['kind'] == 'FIGURE':
                    v['mean'] = (float(ra['mean']) + float(rb['mean'])) / 2
                    if ra.get('dispersion_value') is not None and rb.get('dispersion_value') is not None:
                        try:
                            v['dispersion_value'] = (float(ra['dispersion_value']) + float(rb['dispersion_value'])) / 2
                        except (TypeError, ValueError):
                            pass
                    v['fit_file_B'] = rb.get('fit_file')
                v['receipt_id_B'] = rb.get('receipt_id'); v['reconcile'] = 'AGREED_' + ag['kind']
                agreed.append(v)
            else:
                items.append({'issue': 'VALUE_CONFLICT', 'checks': ag, 'A': ra.drop(labels=['k']).to_dict(), 'B': rb.drop(labels=['k']).to_dict()})
        # second stage: values left unmatched only because the passes named an unstated time point differently
        # (no timepoint_days on at least one side) are paired on arm and measure, nearest mean first
        only_a = [i for i, it in enumerate(items) if it['issue'] == 'ONLY_A']
        drop = set()
        for i in only_a:
            ra = pd.Series(items[i]['A'])
            no_days_a = pd.isna(ra.get('timepoint_days')) if 'timepoint_days' in ra else True
            cand = b[(b.arm_key == ra.arm_key) & (b.measure == ra.measure) & ~b.idx.isin(used_b)] if len(b) else pd.DataFrame()
            if cand.empty:
                continue
            if not no_days_a:
                cand = cand[cand.timepoint_days.isna()]
                if cand.empty:
                    continue
            rb = cand.iloc[(cand['mean'].astype(float) - float(ra['mean'])).abs().argsort().iloc[0]]
            used_b.add(rb.idx); n_match += 1; drop.add(i)
            ag = agree(ra, rb)
            if all(ag[x] for x in ('mean', 'dispersion_type', 'dispersion_value', 'n', 'basis', 'during_stress')):
                n_agree += 1
                v = ra.drop(labels=[c for c in ['pass', 'idx'] if c in ra.index]).to_dict()
                if ag['kind'] == 'FIGURE':
                    v['mean'] = (float(ra['mean']) + float(rb['mean'])) / 2
                v['receipt_id_B'] = rb.get('receipt_id'); v['reconcile'] = 'AGREED_' + ag['kind'] + '_TP_LABEL_DIFF'
                v['timepoint_label_B'] = rb.get('timepoint_label')
                agreed.append(v)
            else:
                items.append({'issue': 'VALUE_CONFLICT', 'checks': ag, 'A': ra.to_dict(), 'B': rb.drop(labels=['k']).to_dict(),
                              'note': 'paired on arm and measure; time point labels differ'})
        items = [it for j, it in enumerate(items) if j not in drop]
        for _, rb in (b[~b.idx.isin(used_b)].iterrows() if len(b) else []):
            items.append({'issue': 'ONLY_B', 'B': rb.drop(labels=['k']).to_dict()})
        if items:
            queue[sid] = items
        stats.append(dict(study_id=sid, status_A=sa, status_B=sb, matched=n_match, agreed=n_agree,
                          conflicts=sum(i['issue'] == 'VALUE_CONFLICT' for i in items),
                          only_A=sum(i['issue'] == 'ONLY_A' for i in items), only_B=sum(i['issue'] == 'ONLY_B' for i in items),
                          other_issues=sum(i['issue'] in ('STATUS_DIFFERS', 'NEW_ARMS_PROPOSED') for i in items), adjudicated=False))
    (WORK / 'adjudication').mkdir(exist_ok=True)
    for sid, items in queue.items():
        (WORK / 'adjudication' / f'{sid}.json').write_text(json.dumps({'study_id': sid, 'items': items}, indent=1, default=str, ensure_ascii=False), encoding='utf-8')
    S = pd.DataFrame(stats)
    S.to_csv(OUT / 'results' / f'{TAG}_reconcile_by_study.csv', index=False)
    pd.DataFrame(agreed).to_csv(OUT / 'data' / f'{TAG}_values_reconciled.csv', index=False)
    tot = S[[c for c in ['matched', 'agreed', 'conflicts', 'only_A', 'only_B', 'other_issues'] if c in S]].sum(numeric_only=True).to_dict()
    print(json.dumps({'studies': len(studies), 'with_both_passes': int((~S.get('pending', pd.Series(False, index=S.index)).fillna(False)).sum()),
                      'to_adjudicate': len(queue), 'agreed_values': len(agreed), **{k: int(v) for k, v in tot.items()}}, indent=1))


if __name__ == '__main__':
    main()
