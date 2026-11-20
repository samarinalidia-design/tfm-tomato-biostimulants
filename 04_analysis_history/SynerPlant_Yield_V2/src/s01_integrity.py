"""Stage I.1 - relational integrity and acceptance checks on the V2 working SQLite.

Read-only. Writes audit/integrity_report.json and audit/integrity_details/*.csv.
Every check returns PASS / WARN / FAIL with a count and an explanation.
"""
from __future__ import annotations
import json, hashlib, math
import numpy as np, pandas as pd
from v2_common import connect, AUDIT, write_json, now

DET = AUDIT / "integrity_details"
DET.mkdir(exist_ok=True)


def rows(con, q, p=()):
    return [dict(r) for r in con.execute(q, p)]


def item_hash(con, cid):
    """Same definition as V1 tools/tfmlib/release.py:audit_item_hash (copied, not imported)."""
    found = rows(con, "SELECT * FROM an_contrasts WHERE contrast_id=?", (cid,))
    if not found:
        return None
    c = found[0]
    payload = {"contrast": {k: v for k, v in c.items() if k != "created_at"}, "values": [],
               "moderators": rows(con, "SELECT feature,value,unit,locator,verbatim,availability,verification,receipt_id,"
                                       "source_file_id FROM wf_moderators WHERE study_id=? ORDER BY feature", (c["study_id"],))}
    for vid in json.loads(c["tv_ids"]):
        v = rows(con, "SELECT * FROM an_target_values WHERE tv_id=?", (vid,))[0]
        payload["values"].append({k: x for k, x in v.items() if k not in ("updated_at", "created_at", "basis_value_ids")})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run() -> dict:
    con = connect(readonly=True)
    checks = []

    def add(name, status, n, detail, df=None):
        checks.append({"check": name, "status": status, "count": int(n), "detail": detail})
        if df is not None and len(df):
            df.to_csv(DET / f"{name}.csv", index=False)

    q = lambda s: pd.read_sql(s, con)
    studies = q("SELECT study_id FROM studies")
    tv = q("SELECT tv_id,study_id,arm_key,experiment_key,endpoint,role,mean,unit_norm,unit_raw,mean_norm,timepoint_key,"
           "record_key,context_key,verification FROM an_target_values")
    arms = q("SELECT study_id,arm_key,experiment_key,role,stress_code,bio_code FROM arms")
    exps = q("SELECT study_id,experiment_key FROM experiments")
    cc = q("SELECT contrast_id,study_id,experiment_key,endpoint,contrast_type,arm_key_t,arm_key_c,tv_ids,mean_t,mean_c,"
           "effect,effect_metric,stress_code,bio_code,shared_control_id,dependency_cluster_id FROM an_contrasts")

    # 1 foreign keys
    s = set(studies.study_id)
    bad = pd.concat([tv[~tv.study_id.isin(s)][["study_id"]].assign(tbl="an_target_values"),
                     arms[~arms.study_id.isin(s)][["study_id"]].assign(tbl="arms"),
                     cc[~cc.study_id.isin(s)][["study_id"]].assign(tbl="an_contrasts")])
    add("fk_study", "PASS" if bad.empty else "FAIL", len(bad), "rows referencing unknown study_id", bad)
    ak = set(zip(arms.study_id, arms.arm_key))
    b2 = tv[[(a, b) not in ak for a, b in zip(tv.study_id, tv.arm_key)]]
    add("fk_value_arm", "PASS" if b2.empty else "FAIL", len(b2), "target values whose arm is not in arms", b2)
    ek = set(zip(exps.study_id, exps.experiment_key))
    b3 = arms[[(a, b) not in ek for a, b in zip(arms.study_id, arms.experiment_key)]]
    add("fk_arm_experiment", "PASS" if b3.empty else "WARN", len(b3),
        "arms whose experiment_key is absent from experiments (design table may use wf_design_experiments)", b3)

    # 2 contrast <-> values consistency
    tvi = tv.set_index("tv_id")
    probs = []
    pair = cc[cc.contrast_type.isin(["SB_vs_S", "B_vs_C", "S_vs_C"])]
    for r in pair.itertuples():
        ids = json.loads(r.tv_ids)
        if len(ids) != 2 or ids[0] not in tvi.index or ids[1] not in tvi.index:
            probs.append((r.contrast_id, "tv_ids missing/not pair")); continue
        t, c = tvi.loc[ids[0]], tvi.loc[ids[1]]
        if t.arm_key != r.arm_key_t or c.arm_key != r.arm_key_c:
            probs.append((r.contrast_id, "arm mismatch"))
        if t.endpoint != c.endpoint or t.endpoint != r.endpoint:
            probs.append((r.contrast_id, "endpoint mismatch"))
        if (t.unit_norm or t.unit_raw) != (c.unit_norm or c.unit_raw):
            probs.append((r.contrast_id, f"unit mismatch {t.unit_norm or t.unit_raw} vs {c.unit_norm or c.unit_raw}"))
        if t.timepoint_key != c.timepoint_key:
            probs.append((r.contrast_id, "timepoint mismatch"))
    pdf = pd.DataFrame(probs, columns=["contrast_id", "problem"])
    add("contrast_value_consistency", "PASS" if pdf.empty else "FAIL", len(pdf),
        "contrast arms/endpoint/unit/timepoint must match its two target values", pdf)

    # 3 lnRR recomputation
    lr = cc[cc.effect.notna() & (cc.effect_metric == "lnRR") & cc.contrast_type.isin(["SB_vs_S", "B_vs_C", "S_vs_C"])].copy()
    lr["re"] = np.log(lr.mean_t / lr.mean_c)
    d = lr[(lr.re - lr.effect).abs() > 1e-6]
    add("lnrr_recompute", "PASS" if d.empty else "FAIL", len(d),
        f"pairwise lnRR contrasts (n={len(lr)}): |effect - ln(mean_t/mean_c)| > 1e-6 (interaction and MD metrics use other formulas)", d)

    # 4 duplicates
    dup_id = cc[cc.contrast_id.duplicated(keep=False)]
    add("duplicate_contrast_id", "PASS" if dup_id.empty else "FAIL", len(dup_id), "duplicated contrast_id", dup_id)
    key = ["study_id", "endpoint", "contrast_type", "arm_key_t", "arm_key_c", "tv_ids"]
    dk = cc[cc.duplicated(key, keep=False)]
    add("duplicate_contrast_definition", "PASS" if dk.empty else "FAIL", len(dk), "identical arm pair + values twice", dk)
    # same numbers re-entered under different IDs (possible double inclusion of one result)
    y = cc[(cc.endpoint == "FRUIT_YIELD") & (cc.contrast_type == "SB_vs_S")].copy()
    y["k"] = y.study_id + "|" + y.mean_t.round(6).astype(str) + "|" + y.mean_c.round(6).astype(str)
    dn = y[y.duplicated("k", keep=False)].sort_values("k")
    add("yield_same_numbers_different_ids", "PASS" if dn.empty else "WARN", len(dn),
        "yield SB_vs_S contrasts with identical (mean_t, mean_c) in one study: check double inclusion", dn)
    # cross-study identical values (duplicate publication)
    tvy = tv[(tv.endpoint == "FRUIT_YIELD") & tv["mean"].notna()]
    g = tvy.groupby(tvy["mean"].round(6)).study_id.nunique()
    cross = tvy[tvy["mean"].round(6).isin(g[g > 1].index) & (tvy["mean"].round(6) != 0)]
    # only flag if >=3 identical values shared by the same pair of studies
    pairs = cross.groupby(cross["mean"].round(6)).study_id.apply(lambda x: tuple(sorted(set(x))))
    pc = pairs.value_counts()
    sus = pc[pc >= 3]
    add("cross_study_duplicate_values", "PASS" if sus.empty else "WARN", len(sus),
        "pairs of studies sharing >=3 identical yield means (possible duplicate publication)",
        sus.rename("n_identical_means").reset_index())

    # 5 Treatment/control role consistency for SB_vs_S
    ar = arms.set_index(["study_id", "arm_key"])
    rp = []
    for r in cc[cc.contrast_type == "SB_vs_S"].itertuples():
        try:
            t, c = ar.loc[(r.study_id, r.arm_key_t)], ar.loc[(r.study_id, r.arm_key_c)]
        except KeyError:
            rp.append((r.contrast_id, "arm missing")); continue
        t = t.iloc[0] if isinstance(t, pd.DataFrame) else t
        c = c.iloc[0] if isinstance(c, pd.DataFrame) else c
        if t.role != "SB" or c.role != "S":
            rp.append((r.contrast_id, f"roles {t.role}/{c.role}"))
        if t.stress_code != c.stress_code:
            rp.append((r.contrast_id, f"stress differs {t.stress_code} vs {c.stress_code}"))
        if str(c.bio_code).upper() not in ("NONE", "", "NAN"):
            rp.append((r.contrast_id, f"control has biostimulant {c.bio_code}"))
    rpd = pd.DataFrame(rp, columns=["contrast_id", "problem"])
    add("sb_vs_s_role_matching", "PASS" if rpd.empty else "WARN", len(rpd),
        "SB_vs_S: SB arm must be SB, control must be S with same stress code and no biostimulant", rpd)

    # 6 positive means for lnRR
    neg = cc[(cc.effect_metric == "lnRR") & cc.effect.notna() & ((cc.mean_t <= 0) | (cc.mean_c <= 0))]
    add("positive_means", "PASS" if neg.empty else "FAIL", len(neg), "lnRR requires positive means", neg)

    # 7 dependency keys
    miss = cc[cc.dependency_cluster_id.isna() | (cc.dependency_cluster_id == "")]
    add("dependency_cluster_present", "PASS" if miss.empty else "FAIL", len(miss), "contrasts without dependency_cluster_id", miss)
    multi = cc.groupby("dependency_cluster_id").study_id.nunique()
    add("cluster_within_one_study", "PASS" if (multi <= 1).all() else "WARN", int((multi > 1).sum()),
        "dependency clusters spanning several studies (expected only for linked publications)")
    sc = cc[cc.contrast_type == "SB_vs_S"].groupby(["study_id", "arm_key_c", "endpoint"]).size()
    add("shared_controls_present", "INFO", int((sc > 1).sum()),
        "control arms shared by >1 SB_vs_S contrast (dependence handled by grouping on study)")

    # 8 stale human audit
    au = q("SELECT contrast_id,verdict,item_hash,checked_at FROM wf_contrast_audit")
    au["current"] = [item_hash(con, c) for c in au.contrast_id]
    stale = au[au.current != au.item_hash]
    add("human_audit_stale_items", "PASS" if stale.empty else "WARN", len(stale),
        "audit verdicts whose contrast/value/moderator content changed after the verdict", stale)
    ts = pd.to_datetime(au.checked_at)
    rate = au.groupby(ts.dt.floor("s")).size()
    add("human_audit_entry_pattern", "INFO", len(au),
        f"{len(au)} verdicts, all '{'/'.join(sorted(au.verdict.unique()))}', entered in {rate.size} distinct seconds "
        f"(max {rate.max()} per second): bulk import; per-item review time cannot be established from the DB")
    legacy = con.execute("SELECT COUNT(*) FROM wf_audit").fetchone()[0]
    add("legacy_wf_audit_table", "INFO", legacy,
        "accuracy() reads the legacy per-value table wf_audit (0 rows), so 'audit.items=0'; the release gate "
        "human_contrast_audit reads wf_contrast_audit. The two numbers measure different tables, not a contradiction.")
    neg_notes = au.merge(q("SELECT contrast_id,notes FROM wf_contrast_audit"), on="contrast_id")
    flagged = neg_notes[neg_notes.notes.fillna("").str.contains(
        r"must be re-digitized|blank although|inconsisten|not supported|error|wrong|incorrect", case=False, regex=True)]
    add("audit_correct_with_problem_notes", "PASS" if flagged.empty else "WARN", len(flagged),
        "verdict CORRECT although the note describes a data problem", flagged[["contrast_id", "notes"]])

    # 9 dataset role / temporal
    yr = q("SELECT study_id,year,dataset_role,first_publication_date FROM studies")
    late = yr[(pd.to_numeric(yr.year, errors="coerce") > 2023) & yr.first_publication_date.isna()]
    ytr = set(cc[(cc.endpoint == "FRUIT_YIELD")].study_id)
    late_y = late[late.study_id.isin(ytr)]
    add("post2023_without_first_online", "PASS" if late_y.empty else "WARN", len(late_y),
        "yield studies with journal year >2023 and no verified first-online date (excluded from TRAIN_DEV)", late_y)

    status = "PASS" if not any(c["status"] == "FAIL" for c in checks) else "FAIL"
    rep = {"generated_at": now(), "overall": status, "checks": checks}
    write_json(AUDIT / "integrity_report.json", rep)
    return rep


if __name__ == "__main__":
    r = run()
    for c in r["checks"]:
        print(f"{c['status']:5} {c['check']:40} {c['count']:6}  {c['detail'][:110]}")
    print("OVERALL", r["overall"])
