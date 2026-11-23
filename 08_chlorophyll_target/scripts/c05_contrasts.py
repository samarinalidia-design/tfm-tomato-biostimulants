"""Chlorophyll pilot: effect sizes from the reconciled values (same conventions as the yield/biomass marts).

Arms and roles (C, S, B, SB) come from the frozen A399 design in the packets, plus new arms accepted by the adjudicator
(work/outbox/ADJ/<study>.json, design_check.new_arms).
Measures: primary CHL_TOTAL (printed total, or CHL_A + CHL_B computed here when no total is printed for the same arm,
time point, unit and basis; variance of the sum not computed - covariance unknown); secondary SPAD / OTHER_CHL_INDEX.
Time point: per arm pair, the latest common time point not flagged as outside the stress period.
Contrasts (within experiment): SB vs S (same stress code, biostimulant present), B vs C, S vs C (stress damage).
lnRR = ln(mean_t / mean_c) for positive means; SD from SD, SE x sqrt(n), UNLABELLED treated as SE (project assumption,
flag USER_ASSUMED_SE); missing variances imputed from the mean CV of the arms with SD (CV-bar, Nakagawa et al. 2023).
Usage: python c05_contrasts.py
"""
import json, math, os, pathlib
import numpy as np
import pandas as pd

WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))
OUT = pathlib.Path(__file__).resolve().parents[1]
TAG = os.environ.get('CHL_TAG', 'pilot')


def arms_table():
    rows = []
    for f in (WORK / 'packets').glob('*.json'):
        pk = json.loads(f.read_text(encoding='utf-8'))
        for a in pk['design_from_A399']['arms']:
            rows.append({**a, 'study_id': pk['study_id'], 'arm_source': 'A399'})
        adj = WORK / 'outbox' / 'ADJ' / f'{pk["study_id"]}.json'
        if adj.exists():
            for a in json.loads(adj.read_text(encoding='utf-8')).get('design_check', {}).get('new_arms', []) or []:
                rows.append({**a, 'study_id': pk['study_id'], 'arm_source': 'NEW_ADJUDICATED'})
    return pd.DataFrame(rows).drop_duplicates(['study_id', 'arm_key'], keep='last')


def sd_of(r):
    t, v, n = r.dispersion_type, r.dispersion_value, r.n
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return np.nan, 'MISSING'
    if t == 'SD':
        return float(v), 'SD'
    if t in ('SE', 'UNLABELLED') and pd.notna(n) and n > 0:
        return float(v) * math.sqrt(n), 'SE' if t == 'SE' else 'USER_ASSUMED_SE'
    if t == 'CI95' and pd.notna(n) and n > 1:
        return float(v) / 1.96 * math.sqrt(n), 'CI95_NORMAL'
    return np.nan, 'NO_N'


def main():
    V = pd.read_csv(OUT / 'data' / f'{TAG}_values_reconciled.csv')
    if V.empty:
        print('no reconciled values'); return
    V['tp'] = V.timepoint_days.astype(str).where(V.timepoint_days.notna(), V.timepoint_label.astype(str))
    # computed total = a + b
    key = ['study_id', 'experiment_key', 'arm_key', 'tp', 'unit_raw', 'basis']
    tot = V[V.measure == 'CHL_TOTAL'].set_index(key).index
    a, b = V[V.measure == 'CHL_A'].set_index(key), V[V.measure == 'CHL_B'].set_index(key)
    both = a.index.intersection(b.index).difference(tot)
    # a + b only when the a/b ratio is physiologically plausible (0.5-10); otherwise the two components are probably on
    # different scales (e.g. a mislabelled unit) and no total is computed (full run, study D_a7d48f360dddfde0)
    ratio = a.loc[both, 'mean'].astype(float).values / b.loc[both, 'mean'].astype(float).replace(0, float('nan')).values
    skipped = both[~((ratio >= 0.5) & (ratio <= 10))]
    both = both[(ratio >= 0.5) & (ratio <= 10)]
    if len(skipped):
        pd.DataFrame(list(skipped), columns=key).to_csv(OUT / 'results' / f'{TAG}_a_plus_b_skipped_ratio.csv', index=False)
    comp = a.loc[both].reset_index().copy()
    comp['mean'] = a.loc[both, 'mean'].values + b.loc[both, 'mean'].values
    comp['measure'] = 'CHL_TOTAL'; comp['computed'] = 'A_PLUS_B'; comp['dispersion_type'] = 'NOT_REPORTED'; comp['dispersion_value'] = np.nan
    V['computed'] = ''
    V = pd.concat([V, comp], ignore_index=True)
    V['endpoint'] = np.where(V.measure == 'CHL_TOTAL', 'CHL_CONTENT', np.where(V.measure.isin(['SPAD', 'OTHER_CHL_INDEX']), 'CHL_INDEX', 'CHL_COMPONENT'))
    sd = V.apply(sd_of, axis=1)
    V['sd'] = [s[0] for s in sd]; V['sd_basis'] = [s[1] for s in sd]
    R = arms_table()
    V = V.merge(R[['study_id', 'arm_key', 'role', 'stress_code', 'bio_code', 'arm_source']], on=['study_id', 'arm_key'], how='left')
    cvbar = (V.sd / V['mean']).replace([np.inf, -np.inf], np.nan)
    cv_by_ep = V.assign(cv=cvbar).groupby('endpoint').cv.mean().to_dict()
    nbar = V.n.median()
    if os.environ.get('CHL_SPLIT', 'TRAIN') == 'TEST':      # TEST: variance imputation constants learnt on TRAIN (frozen)
        fz = json.loads((OUT / 'freeze' / 'MODEL_FREEZE_CHL.json').read_text(encoding='utf-8'))['variance_imputation_from_train']
        cv_by_ep, nbar = fz['cv_bar_by_endpoint'], fz['median_n']
    C = []
    for (sid, ek, ep, meas, unit, basis), g in V[V.endpoint.isin(['CHL_CONTENT', 'CHL_INDEX'])].groupby(
            ['study_id', 'experiment_key', 'endpoint', 'measure', 'unit_raw', 'basis'], dropna=False):
        pairs = []
        S = g[g.role == 'S']; SB = g[g.role == 'SB']; Cc = g[g.role == 'C']; Bb = g[g.role == 'B']
        for _, t in SB.iterrows():
            for _, c in S[S.stress_code == t.stress_code].iterrows():
                pairs.append(('SB_vs_S', t, c))
        for _, t in Bb.iterrows():
            for _, c in Cc.iterrows():
                pairs.append(('B_vs_C', t, c))
        for _, t in S.iterrows():
            for _, c in Cc.iterrows():
                pairs.append(('S_vs_C', t, c))
        for ctype, t, c in pairs:
            # common time point: latest not outside the stress period
            tt = g[(g.arm_key == t.arm_key)]; cc = g[(g.arm_key == c.arm_key)]
            common = sorted(set(tt.tp) & set(cc.tp))
            if not common:
                continue
            # the stress-period rule concerns stressed contrasts only; for B_vs_C (no stress) every common time point is valid
            # (agents code during_stress inconsistently for unstressed arms)
            if ctype == 'B_vs_C':
                ok = list(common)
            else:
                ok = [x for x in common if not ((tt[tt.tp == x].during_stress == False).all())]
            use = ok or common
            outside = not ok
            def order(x):
                try:
                    return float(x)
                except ValueError:
                    return -1
            tp = sorted(use, key=order)[-1]
            rt, rc = tt[tt.tp == tp].iloc[0], cc[cc.tp == tp].iloc[0]
            if not (rt['mean'] > 0 and rc['mean'] > 0):
                continue
            def var_part(r):
                if pd.notna(r.sd) and pd.notna(r.n) and r.n > 0:
                    return r.sd ** 2 / (r.n * r['mean'] ** 2), 'REPORTED' if r.sd_basis in ('SD', 'SE', 'CI95_NORMAL') else 'USER_ASSUMED_SE'
                cv = cv_by_ep.get(ep, np.nan); n = r.n if pd.notna(r.n) else nbar
                return (cv ** 2 / n if pd.notna(cv) and pd.notna(n) else np.nan), 'IMPUTED_CVBAR'
            vt, st = var_part(rt); vc, sc = var_part(rc)
            C.append(dict(study_id=sid, experiment_key=ek, endpoint=ep, measure=meas, contrast_type=ctype, arm_key_t=t.arm_key, arm_key_c=c.arm_key,
                          stress_code=t.stress_code, bio_code=t.bio_code, timepoint=tp, unit_raw=unit, basis=basis,
                          mean_t=rt['mean'], mean_c=rc['mean'], n_t=rt.n, n_c=rc.n, lnRR=math.log(rt['mean'] / rc['mean']),
                          var_lnRR=vt + vc if pd.notna(vt) and pd.notna(vc) else np.nan, variance_status=f'{st}|{sc}',
                          computed=(rt.computed or '') + ('|' + rc.computed if rc.computed else ''),
                          source_t=rt.source_kind, source_c=rc.source_kind, tp_outside_stress=outside, reconcile=f'{rt.reconcile}|{rc.reconcile}'))
    Cd = pd.DataFrame(C)
    V.to_csv(OUT / 'data' / f'{TAG}_values_with_roles.csv', index=False)
    Cd.to_csv(OUT / 'data' / f'{TAG}_contrasts.csv', index=False)
    if Cd.empty:
        print('no contrasts'); return
    print(Cd.groupby(['endpoint', 'contrast_type']).agg(contrasts=('lnRR', 'size'), studies=('study_id', 'nunique'),
                                                         mean_lnRR=('lnRR', 'mean')).round(3).to_string())


if __name__ == '__main__':
    main()
