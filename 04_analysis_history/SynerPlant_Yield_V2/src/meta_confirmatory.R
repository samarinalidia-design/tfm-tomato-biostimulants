# Confirmatory three-level meta-analysis (contrast within study), TRAIN_DEV yield lnRR.
# metafor::rma.mv REML + clubSandwich CR2 cluster-robust inference (Satterthwaite df), clustered by study.
# Usage: Rscript meta_confirmatory.R <input_dir> <output_json>
suppressPackageStartupMessages({library(metafor); library(clubSandwich); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
indir <- args[1]; outjson <- args[2]
sets <- c(PRIMARY_EXPANDED = "PRIMARY_EXPANDED.csv", STRICT_SENSITIVITY = "STRICT_SENSITIVITY.csv",
          REPORTED_VARIANCE_ONLY = "SENSITIVITY_REPORTED_VARIANCE.csv", QUALITY_CORE = "QUALITY_CORE.csv",
          V1_EQUIVALENT = "V1_EQUIVALENT.csv")
res <- list()
for (nm in names(sets)) {
  d <- read.csv(file.path(indir, sets[[nm]]), stringsAsFactors = FALSE)
  d <- d[!is.na(d$vi) & d$vi > 0 & !is.na(d$lnRR), c("contrast_id", "study_id", "lnRR", "vi")]
  k <- length(unique(d$study_id))
  if (k < 5) { res[[nm]] <- list(set = nm, n = nrow(d), k_studies = k, status = "TOO_FEW_STUDIES"); next }
  m <- rma.mv(lnRR, vi, random = ~ 1 | study_id / contrast_id, data = d, method = "REML", test = "t")
  ct <- coef_test(m, vcov = "CR2", cluster = d$study_id)
  ci <- conf_int(m, vcov = "CR2", cluster = d$study_id)
  pr <- predict(m)
  tcrit <- qt(0.975, k - 1)
  pi_study <- c(m$b[1] - tcrit * sqrt(m$se^2 + m$sigma2[1]), m$b[1] + tcrit * sqrt(m$se^2 + m$sigma2[1]))
  res[[nm]] <- list(set = nm, n = nrow(d), k_studies = k, mu_lnRR = as.numeric(m$b[1]),
                    pct_effect = 100 * (exp(as.numeric(m$b[1])) - 1),
                    se_model = as.numeric(m$se), ci95_model = c(m$ci.lb, m$ci.ub),
                    se_CR2 = ct$SE, df_CR2_Satterthwaite = ct$df_Satt, p_CR2 = ct$p_Satt,
                    ci95_CR2 = c(ci$CI_L, ci$CI_U),
                    tau2_between = m$sigma2[1], tau2_within = m$sigma2[2],
                    pi95_new_contrast_metafor = c(pr$pi.lb, pr$pi.ub),
                    pi95_new_study_mean = pi_study,
                    Q = m$QE, Q_df = m$k - 1, Q_p = m$QEp,
                    metafor = as.character(packageVersion("metafor")),
                    clubSandwich = as.character(packageVersion("clubSandwich")))
}
res[["R_version"]] <- R.version.string
write(toJSON(res, auto_unbox = TRUE, digits = 10, pretty = TRUE), outjson)
cat("done\n")
