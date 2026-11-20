"""Run the confirmatory R meta-analysis (metafor rma.mv + clubSandwich CR2) and compare it with the exploratory
Python REML (s07_meta.py). Output: outputs/meta/R_confirmatory.json, outputs/meta/R_vs_python.csv."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
import pandas as pd
from v2_common import V2, OUT, now, write_json

RSCRIPT = Path(r"C:\Program Files\R\R-4.5.0\bin\Rscript.exe")
META = OUT / "meta"


def main():
    outj = META / "R_confirmatory.json"
    r = subprocess.run([str(RSCRIPT), str(V2 / "src" / "meta_confirmatory.R"), str(OUT / "data"), str(outj)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"R failed:\n{r.stderr[-3000:]}")
    R = json.loads(outj.read_text(encoding="utf-8"))
    P = {x["set"]: x for x in json.loads((META / "meta_summary.json").read_text())["overall"]}
    rows = []
    for k, v in R.items():
        if not isinstance(v, dict) or "mu_lnRR" not in v:
            continue
        p = P.get(k, {})
        rows.append({"set": k, "k_studies": v["k_studies"], "n": v["n"],
                     "R_mu": v["mu_lnRR"], "Py_mu": p.get("mu_lnRR"),
                     "R_pct": v["pct_effect"], "R_CI95_CR2": v["ci95_CR2"], "Py_CI95_CR1": p.get("C_ci95_cluster_robust"),
                     "R_df_CR2": v["df_CR2_Satterthwaite"], "R_p_CR2": v["p_CR2"],
                     "R_tau2_between": v["tau2_between"], "Py_tau2_between": p.get("tau2_between"),
                     "R_tau2_within": v["tau2_within"], "Py_tau2_within": p.get("tau2_within"),
                     "R_PI95_new_study": v["pi95_new_study_mean"], "Py_PI95_new_study": p.get("D_pi95_new_study_mean"),
                     "abs_diff_mu": abs(v["mu_lnRR"] - p["mu_lnRR"]) if p else None})
    t = pd.DataFrame(rows)
    t.to_csv(META / "R_vs_python.csv", index=False)
    write_json(META / "R_confirmatory_status.json", {"run_at": now(), "R": R.get("R_version"),
                                                     "max_abs_diff_mu_R_vs_python": float(t.abs_diff_mu.max()),
                                                     "status": "CONFIRMATORY_R_DONE"})
    return t


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    print(main().to_string())
