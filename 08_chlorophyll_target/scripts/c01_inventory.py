"""Chlorophyll content as a new target: inventory of the source assets in the frozen TRAIN_DEV and EXTERNAL_TEST databases.

The frozen databases hold no chlorophyll VALUES (physiological panels were out of the v2.2 extraction scope), but every
figure/table/text asset of every study was listed and described by the agents in `asset_inventory` (locator + reason).
This script finds the assets that describe chlorophyll CONTENT (chlorophyll a, b, total, a+b; SPAD as a separate proxy;
fluorescence-only assets are excluded) and joins the study status and the coded design (does an experiment have a
stressed control S and a stressed + biostimulant arm SB?).

Usage: python c01_inventory.py <TRAIN sqlite> <TEST sqlite>
Output: 08_chlorophyll_target/data/chlorophyll_assets.csv, chlorophyll_studies.csv; results/inventory_summary.json
Counts are based on the agents' asset descriptions: assets that print values only in running text may be missing.
"""
import sys, re, json, sqlite3, pathlib
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
(OUT / 'data').mkdir(parents=True, exist_ok=True); (OUT / 'results').mkdir(parents=True, exist_ok=True)

PAT = {
    'chl_a': r'chl(orophyll)?[\s.\-_]*a\b|chlorophyll a\b|chl\.?\s?a\b',
    'chl_b': r'chl(orophyll)?[\s.\-_]*b\b|chlorophyll b\b|chl\.?\s?b\b',
    'chl_total': r'total chlorophyll|chlorophyll (content|concentration|a\s*\+\s*b)|chl\s*(a\s*\+\s*b|t\b|total)|chlorophyll index|leaf chlorophyll|photosynthetic pigment',
    'spad': r'\bspad\b|chlorophyll meter|ccm-200|atleaf',
}
FLUO_ONLY = r'fluorescence|fv/fm|fv\s*/\s*fm|psii|φpsii|npq'


CONTENT_CUE = r'content|concentration|mg\s*g|mg/g|µg|ug/|μg|mg 100|total chl|chl\.?\s?a\s*\+|pigment|a, b'


def classify(text):
    t = text.lower()
    if re.search(r'fluorescence|fv/fm|psii', t) and not re.search(CONTENT_CUE, t) and not re.search(r'spad', t):
        return {k: False for k in PAT}                       # fluorescence panel, not chlorophyll content
    t = re.sub(r'chlorophyll a fluorescence', ' ', t)
    hits = {k: bool(re.search(p, t)) for k, p in PAT.items()}
    if re.search(r'a,\s*b|a\s*and\s*b|a\s*\+\s*b', t) and re.search(r'chl', t):
        hits['chl_a'] = hits['chl_b'] = True
    # 'chlorophyll' alone (not fluorescence) is read as a chlorophyll-content mention
    if re.search(r'chlorophyll', t) and not any(hits.values()):
        if not re.search(r'chlorophyll fluorescence', t):
            hits['chl_total'] = True
    return hits


def design(arms):
    """Per study: experiments with S (stress, no biostimulant) and SB (same stress, biostimulant) arms."""
    a = arms.copy()
    a['s'] = a.stress_code.fillna('NONE').astype(str); a['b'] = a.bio_code.fillna('NONE').astype(str)
    out = {}
    for sid, g in a.groupby('study_id'):
        n_exp = 0
        for ek, e in g.groupby('experiment_key'):
            sc = set(e.loc[(e.s != 'NONE') & (e.b == 'NONE'), 's']); sbc = set(e.loc[(e.s != 'NONE') & (e.b != 'NONE'), 's'])
            if sc & sbc:
                n_exp += 1
        has_c = ((g.s == 'NONE') & (g.b == 'NONE')).any(); has_b = ((g.s == 'NONE') & (g.b != 'NONE')).any()
        out[sid] = dict(experiments_with_SB_S=n_exp, has_unstressed_C=bool(has_c), has_unstressed_B=bool(has_b))
    return out


def run(path, role):
    c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    ai = pd.read_sql('select study_id, asset_key, source_file_id, locator, relevance, disposition, reason from asset_inventory', c)
    st = pd.read_sql('select study_id, doi, title, year from studies', c)
    status = pd.read_sql('select * from wf_study_status', c) if 'wf_study_status' in [r[0] for r in c.execute("select name from sqlite_master")] else pd.DataFrame()
    arms = pd.read_sql('select study_id, experiment_key, arm_key, stress_code, bio_code from arms', c)
    txt = (ai.locator.fillna('') + ' | ' + ai.reason.fillna(''))
    cls = txt.map(classify).apply(pd.Series)
    ai = pd.concat([ai, cls], axis=1)
    ai['fluorescence_only'] = txt.str.lower().str.contains(FLUO_ONLY) & ~ai[list(PAT)].any(axis=1)
    chl = ai[ai[['chl_a', 'chl_b', 'chl_total', 'spad']].any(axis=1)].copy()
    chl['role'] = role
    chl['source_unavailable'] = (chl.locator.fillna('') + ' ' + chl.reason.fillna('')).str.lower().str.contains(
        r'not registered in (the )?frozen corpus|not in (the )?corpus|unavailable|not provided')
    chl['baseline_only'] = (chl.locator.fillna('') + ' ' + chl.reason.fillna('')).str.lower().str.contains(r'baseline|t0|pre-treatment|pre-stress|pre-drought')
    des = design(arms)
    stat_col = next((x for x in ['state', 'status', 'final_state'] if x in status.columns), None)
    stat = status.set_index('study_id')[stat_col].to_dict() if stat_col else {}
    S = chl.groupby('study_id').agg(assets=('asset_key', 'size'), chl_a=('chl_a', 'any'), chl_b=('chl_b', 'any'),
                                     chl_total=('chl_total', 'any'), spad=('spad', 'any'),
                                     locators=('locator', lambda x: ' || '.join(x.astype(str))[:600]),
                                     all_unavailable=('source_unavailable', 'all'), all_baseline=('baseline_only', 'all')).reset_index()
    S['content_not_spad'] = S[['chl_a', 'chl_b', 'chl_total']].any(axis=1)
    S = S.merge(st, on='study_id', how='left')
    S['workflow_status'] = S.study_id.map(stat)
    for k in ['experiments_with_SB_S', 'has_unstressed_C', 'has_unstressed_B']:
        S[k] = S.study_id.map(lambda s: des.get(s, {}).get(k))
    S['design_coded'] = S.study_id.isin(des)
    S['role'] = role
    return chl, S, len(st)


def main():
    chl_tr, S_tr, n_tr = run(sys.argv[1], 'TRAIN')
    chl_te, S_te, n_te = run(sys.argv[2], 'TEST')
    A = pd.concat([chl_tr, chl_te], ignore_index=True); S = pd.concat([S_tr, S_te], ignore_index=True)
    A.to_csv(OUT / 'data' / 'chlorophyll_assets.csv', index=False)
    S.to_csv(OUT / 'data' / 'chlorophyll_studies.csv', index=False)
    summ = {}
    for role, s, n in [('TRAIN', S_tr, n_tr), ('TEST', S_te, n_te)]:
        coded = s[s.design_coded]
        summ[role] = {
            'studies_in_db': n, 'studies_with_chlorophyll_asset': int(len(s)),
            'content_a_b_total (not SPAD only)': int(s.content_not_spad.sum()), 'spad_only': int((~s.content_not_spad & s.spad).sum()),
            'with_chl_a': int(s.chl_a.sum()), 'with_chl_b': int(s.chl_b.sum()), 'with_total': int(s.chl_total.sum()), 'with_spad': int(s.spad.sum()),
            'assets': int(s.assets.sum()),
            'usable_candidates (content, source available, not only baseline)': int((s.content_not_spad & ~s.all_unavailable & ~s.all_baseline).sum()),
            'design_coded_in_db': int(len(coded)), 'coded_with_SB_vs_S_pair': int((coded.experiments_with_SB_S > 0).sum()),
            'coded_with_unstressed_C_and_B': int((coded.has_unstressed_C & coded.has_unstressed_B).sum()),
            'design_not_coded (no yield/biomass target)': int((~s.design_coded).sum()),
            'workflow_status': s.workflow_status.value_counts(dropna=False).to_dict(),
        }
    (OUT / 'results' / 'inventory_summary.json').write_text(json.dumps(summ, indent=1, default=str), encoding='utf-8')
    print(json.dumps(summ, indent=1, default=str))


if __name__ == '__main__':
    main()
