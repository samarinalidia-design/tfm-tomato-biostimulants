"""H5 - point-prediction metrics of the R models (h03) against the same reference, same rule as h02."""
import pandas as pd
from h00_common import OUT, group_mae
from h02_cv import summarize

py = pd.read_csv(OUT / "cv" / "cv_predictions.csv.gz")
ref = py[py.candidate == "row_median|B|none|z"]
r = pd.read_csv(OUT / "rma" / "rma_predictions.csv")
r["candidate"] = "R:" + r.candidate
p = pd.concat([ref, r[ref.columns]], ignore_index=True)
mets = p.groupby(["candidate", "seed", "fold"]).apply(
    lambda x: group_mae(x.lnRR, x.pred, x.group_id), include_groups=False).rename("group_mae").reset_index()
s = summarize(p, mets)
s.to_csv(OUT / "rma" / "rma_comparison.csv", index=False)
pd.set_option("display.width", 250)
print(s[["candidate", "group_mae", "group_mae_sd_seeds", "gain_vs_ref", "diff_ci_lo", "diff_ci_hi",
         "median_fold_wins_of_5", "rmse", "bias_study_balanced", "passes_rule"]].round(4).to_string(index=False))
