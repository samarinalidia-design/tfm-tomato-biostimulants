"""V1 <-> V2 comparison by identifiers/values and the compact HUMAN AUDIT package for every V2-changed contrast.

Author decision 2026-11-18 #2: V2 corrections carry AUTO_VERIFIED_V2 only; a new compact human-audit package is
prepared for changed contrasts. Verdict columns are left EMPTY - no agent ever fills them.
Required sample (TFM 3.10 rule reused): k = min(N, max(20, ceil(0.15 N))), stratified by change type, seed fixed.
"""
from __future__ import annotations
import json, math
import numpy as np, pandas as pd
from v2_common import OUT, AUDIT, V1_ML, now, write_json

DATA = OUT / "data"


def main():
    reg = pd.read_csv(DATA / "v2_yield_contrast_register.csv", low_memory=False)
    v1 = pd.read_csv(V1_ML / "data/input/A_yield_primary.csv", low_memory=False,
                     usecols=["contrast_id", "study_id", "lnRR", "mean_sb", "mean_s", "biostimulant_class",
                              "stress_family", "yield_definition_tier"])
    prim = pd.read_csv(DATA / "PRIMARY_EXPANDED.csv", low_memory=False,
                       usecols=["contrast_id", "lnRR", "mean_t", "mean_c", "biostimulant_class", "stress_family",
                                "yield_tier", "class_override"])
    m = v1.merge(prim, on="contrast_id", how="outer", suffixes=("_v1", "_v2"), indicator=True)
    m = m.merge(reg[["contrast_id", "study_id", "status", "status_reason", "doi", "locator_t", "locator_c"]],
                on="contrast_id", how="left", suffixes=("", "_reg"))
    m["study_id"] = m.study_id.fillna(m.study_id_reg)
    m["change"] = np.select(
        [m._merge == "left_only", m._merge == "right_only",
         (m.lnRR_v1 - m.lnRR_v2).abs() > 1e-9,
         (m.mean_sb - m.mean_t).abs() > 1e-9,
         m.biostimulant_class_v1.fillna("NA") != m.biostimulant_class_v2.fillna("NA"),
         m.stress_family_v1.fillna("NA") != m.stress_family_v2.fillna("NA")],
        ["REMOVED_FROM_PRIMARY", "ADDED_TO_PRIMARY", "LNRR_CHANGED", "MEANS_CHANGED_LNRR_SAME",
         "CLASS_CHANGED", "STRESS_FAMILY_CHANGED"], "UNCHANGED")
    m.drop(columns=["_merge", "study_id_reg"]).to_csv(DATA / "v1_v2_comparison.csv", index=False)
    summary = m.change.value_counts().to_dict()

    ch = m[m.change != "UNCHANGED"].copy()
    N = len(ch)
    k = min(N, max(20, math.ceil(0.15 * N)))
    rng = np.random.default_rng(20261118)
    # largest-remainder allocation: sums exactly to k, at least one per stratum
    cnt = ch.change.value_counts()
    raw = cnt / N * k
    alloc = np.floor(raw).astype(int).clip(lower=1)
    for c in (raw - np.floor(raw)).sort_values(ascending=False).index:
        if alloc.sum() >= k:
            break
        if alloc[c] < cnt[c]:
            alloc[c] += 1
    while alloc.sum() > k:
        alloc[alloc.idxmax()] -= 1
    # keep rows already required in an existing package (their human verdicts stay valid); top up only
    path0 = AUDIT / "HUMAN_AUDIT_V2_PACKAGE.xlsx"
    prior = set()
    if path0.exists():
        o = pd.read_excel(path0, sheet_name="audit", dtype=str)
        prior = set(o[o.required_sample.str.upper() == "TRUE"].contrast_id) & set(ch.contrast_id)
    picked = []
    for c, n in alloc.items():
        ids = sorted(ch[ch.change == c].contrast_id)
        keep = [i for i in ids if i in prior][:n]
        rest = [i for i in ids if i not in keep]
        add = n - len(keep)
        picked += keep + (list(rng.choice(rest, size=min(add, len(rest)), replace=False)) if add > 0 else [])
    ch["required_sample"] = ch.contrast_id.isin(picked)
    decisions = json.loads((AUDIT / "corrections_register.json").read_text(encoding="utf-8"))
    ev = {}
    for sec, items in decisions.items():
        if sec.startswith("_"):
            continue
        for it in items:
            if it.get("study_id"):
                ev.setdefault(it["study_id"], []).append(f"{it.get('id', '')}: {it.get('evidence', it.get('finding', ''))[:400]}")
    ch["evidence_v2"] = ch.study_id.map(lambda s: " | ".join(ev.get(s, [])))
    ch["auto_status"] = "AUTO_VERIFIED_V2"
    ch["human_verdict (CORRECT / INCORRECT / UNSURE)"] = ""
    ch["reviewer_name"] = ""
    ch["reviewer_notes"] = ""
    cols = ["required_sample", "change", "contrast_id", "study_id", "doi", "status", "status_reason", "lnRR_v1",
            "lnRR_v2", "mean_sb", "mean_s", "mean_t", "mean_c", "biostimulant_class_v1", "biostimulant_class_v2",
            "stress_family_v2", "yield_tier", "locator_t", "locator_c", "evidence_v2", "auto_status",
            "human_verdict (CORRECT / INCORRECT / UNSURE)", "reviewer_name", "reviewer_notes"]
    ch = ch[cols].sort_values(["required_sample", "change", "study_id"], ascending=[False, True, True])
    path = AUDIT / "HUMAN_AUDIT_V2_PACKAGE.xlsx"
    # NEVER erase human input: carry existing verdicts over (only for unchanged content of the same contrast)
    kept = 0
    hum = ["human_verdict (CORRECT / INCORRECT / UNSURE)", "reviewer_name", "reviewer_notes"]
    if path.exists():
        old = pd.read_excel(path, sheet_name="audit", dtype=str)
        old = old[old[hum].notna().any(axis=1)]
        if len(old):
            key = ["contrast_id", "lnRR_v2", "mean_t", "mean_c", "status"]
            def norm(v):
                try:
                    f = float(v)
                    return "NA" if np.isnan(f) else f"{f:.6g}"
                except (TypeError, ValueError):
                    return "NA" if v is None or str(v).strip() in ("", "nan", "None") else str(v).strip()
            sig = lambda df: df[key].apply(lambda col: col.map(norm)).agg("|".join, axis=1)
            o = old.assign(_s=sig(old)).set_index("_s")[hum]
            s_new = sig(ch.astype(str))
            for c in hum:
                ch[c] = s_new.map(o[c]).fillna("").to_numpy()
            kept = int(s_new.isin(o.index).sum())
            stale = old[~sig(old).isin(set(s_new))]
            if len(stale):   # content changed since the verdict: keep a record, verdict no longer applies
                stale.to_csv(AUDIT / "human_audit_v2_stale_verdicts.csv", index=False)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame({"instructions": [
            "Human audit of contrasts changed by SynerPlant Yield V2 (agent status AUTO_VERIFIED_V2, never HUMAN_VERIFIED).",
            f"Changed contrasts N={N}; required stratified sample k={k} (rows with required_sample=TRUE, sheet 'audit').",
            "For each required row open the DOI/PDF at the locator, check the two means, the arm pairing (same stress, "
            "no biostimulant in the control), the yield definition and the V2 decision in 'evidence_v2'.",
            "Write CORRECT / INCORRECT / UNSURE in the verdict column, your name and notes. Agents never fill these.",
            "Evidence images for P0/P1 decisions: audit/evidence/<study_id>/ ."]}).to_excel(w, sheet_name="README", index=False)
        ch.to_excel(w, sheet_name="audit", index=False)
    rep = {"generated_at": now(), "v1_v2_change_summary": summary, "changed_N": N, "required_k": k,
           "package": str(path), "human_verdicts_preserved": kept}
    write_json(AUDIT / "human_audit_v2_package.json", rep)
    return rep


if __name__ == "__main__":
    print(main())
