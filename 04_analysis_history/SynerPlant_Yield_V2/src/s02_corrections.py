"""Stage I.2 - apply source-verified corrections to the V2 working SQLite (idempotent).

* value corrections (corrections_register.value_corrections) -> an_target_values / arm_values_verified,
  then every pairwise lnRR contrast that uses a changed value is recomputed in every table that stores it;
* decision tables v2_changelog, v2_decisions are (re)written from the register;
* nothing is ever marked HUMAN_VERIFIED; changed values get verification='AUTO_VERIFIED_V2'.
The V1 freeze and the V1 system database are never opened for writing.
"""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from v2_common import connect, AUDIT, now, write_json

REG = AUDIT / "corrections_register.json"
PAIRWISE = ("SB_vs_S", "B_vs_C", "S_vs_C")


def contrast_tables(con):
    out = []
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}
        if {"contrast_id", "tv_ids", "mean_t", "mean_c", "effect"} <= cols:
            out.append((t, cols))
    return out


def run() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    con = connect()
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS v2_changelog (change_id TEXT, applied_at TEXT, table_name TEXT, key TEXT, "
                "column_name TEXT, old_value TEXT, new_value TEXT, register_id TEXT, policy TEXT, status TEXT)")
    cur.execute("DROP TABLE IF EXISTS v2_decisions")
    cur.execute("CREATE TABLE v2_decisions (register_id TEXT, section TEXT, policy TEXT, study_id TEXT, payload_json TEXT)")
    for section, items in reg.items():
        if section.startswith("_"):
            continue
        for it in items:
            cur.execute("INSERT INTO v2_decisions VALUES (?,?,?,?,?)",
                        (it.get("id", ""), section, it.get("policy", ""), it.get("study_id", ""),
                         json.dumps(it, ensure_ascii=False)))

    log = []
    for vc in reg["value_corrections"]:
        changed = []
        for tv, new in vc["tv_values"].items():
            tv = int(tv)
            old = cur.execute("SELECT mean, verification FROM an_target_values WHERE tv_id=?", (tv,)).fetchone()
            if old is None:
                raise RuntimeError(f"{vc['id']}: tv_id {tv} not found")
            if abs(old[0] - new) < 1e-12 and old[1] == "AUTO_VERIFIED_V2":
                continue  # already applied (idempotent)
            for t in ("an_target_values", "arm_values_verified"):
                cols = {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}
                sets = ["mean=?"] + (["mean_norm=?"] if "mean_norm" in cols else []) + \
                       (["verification=?"] if "verification" in cols else [])
                vals = [new] + ([new] if "mean_norm" in cols else []) + \
                       (["AUTO_VERIFIED_V2"] if "verification" in cols else [])
                cur.execute(f'UPDATE "{t}" SET {", ".join(sets)} WHERE tv_id=?', (*vals, tv))
            log.append((vc["id"] + f"-tv{tv}", now(), "an_target_values", str(tv), "mean", repr(old[0]), repr(new),
                        vc["id"], vc["policy"], "AUTO_VERIFIED_V2"))
            changed.append(tv)
        if not changed:
            continue
        # recompute every pairwise lnRR contrast that uses a changed value, in every table storing contrasts
        means = dict(cur.execute("SELECT tv_id, mean FROM an_target_values").fetchall())
        for t, cols in contrast_tables(con):
            q = f'SELECT contrast_id, tv_ids, contrast_type, mean_t, mean_c, effect' + \
                (", sd_t, n_t, sd_c, n_c" if {"sd_t", "n_t", "sd_c", "n_c"} <= cols else "") + \
                (", effect_metric" if "effect_metric" in cols else "") + f' FROM "{t}"'
            for r in cur.execute(q).fetchall():
                ids = json.loads(r[1])
                if not set(ids) & set(changed):
                    continue
                metric = r[-1] if "effect_metric" in cols else "lnRR"
                if r[2] not in PAIRWISE or metric != "lnRR" or len(ids) != 2:
                    raise RuntimeError(f"{t}/{r[0]}: non-pairwise contrast uses a corrected value; formula needed")
                mt, mc = means[ids[0]], means[ids[1]]
                eff = float(np.log(mt / mc))
                upd = {"mean_t": mt, "mean_c": mc, "effect": eff}
                if "pct_effect" in cols:
                    upd["pct_effect"] = 100 * (mt / mc - 1)
                if len(r) >= 10 and all(v is not None for v in r[6:10]):
                    sdt, nt, sdc, nc = r[6:10]
                    var = sdt ** 2 / (nt * mt ** 2) + sdc ** 2 / (nc * mc ** 2)
                    if "var_effect" in cols:
                        upd["var_effect"] = var
                    if "effect_bc" in cols:
                        upd["effect_bc"] = eff + sdt ** 2 / (2 * nt * mt ** 2) - sdc ** 2 / (2 * nc * mc ** 2)
                    if "se_effect" in cols:
                        upd["se_effect"] = var ** 0.5
                    if "ci95_lower" in cols:
                        upd["ci95_lower"], upd["ci95_upper"] = eff - 1.959964 * var ** 0.5, eff + 1.959964 * var ** 0.5
                old_eff = r[5]
                cur.execute(f'UPDATE "{t}" SET {", ".join(k + "=?" for k in upd)} WHERE contrast_id=?',
                            (*upd.values(), r[0]))
                log.append((f"{vc['id']}-{t}-{r[0]}", now(), t, r[0], "effect", repr(old_eff), repr(eff), vc["id"],
                            vc["policy"], "RECOMPUTED"))
    cur.executemany("INSERT INTO v2_changelog VALUES (?,?,?,?,?,?,?,?,?,?)", log)
    con.commit()
    n_total = cur.execute("SELECT COUNT(*) FROM v2_changelog").fetchone()[0]
    con.close()
    rep = {"applied_at": now(), "new_changelog_rows": len(log), "changelog_rows_total": n_total}
    write_json(AUDIT / "corrections_applied.json", rep)
    return rep


if __name__ == "__main__":
    print(run())
