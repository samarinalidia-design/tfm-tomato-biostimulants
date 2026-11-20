# Secondary (pre-registered, Addendum 1) meta-analyses for the TEST: TEST alone, and TRAIN+TEST with a
# dataset indicator. Same model as the confirmatory TRAIN analysis (rma.mv REML, study/contrast; CR2 by study).
# Usage: Rscript meta_test.R <train_csv> <test_csv> <output_json>
suppressPackageStartupMessages({library(metafor); library(clubSandwich); library(jsonlite)})
a <- commandArgs(trailingOnly = TRUE)
rd <- function(f, lab) { d <- read.csv(f, stringsAsFactors = FALSE)
  d <- d[!is.na(d$vi) & d$vi > 0 & !is.na(d$lnRR), c("contrast_id", "study_id", "lnRR", "vi")]
  d$dataset <- lab; d$study_id <- paste(lab, d$study_id, sep = ":"); d }
tr <- rd(a[1], "TRAIN"); te <- rd(a[2], "TEST")
fit1 <- function(d) {
  k <- length(unique(d$study_id))
  if (k < 5) return(list(k_studies = k, status = "TOO_FEW_STUDIES"))
  m <- rma.mv(lnRR, vi, random = ~ 1 | study_id / contrast_id, data = d, method = "REML", test = "t")
  ci <- conf_int(m, vcov = "CR2", cluster = d$study_id)
  ct <- coef_test(m, vcov = "CR2", cluster = d$study_id)
  t <- qt(0.975, k - 1)
  list(k_studies = k, n = nrow(d), mu_lnRR = as.numeric(m$b[1]), se_CR2 = ct$SE, ci95_CR2 = c(ci$CI_L, ci$CI_U),
       tau2_between = m$sigma2[1], tau2_within = m$sigma2[2],
       pi95_new_study_mean = c(m$b[1] - t * sqrt(m$se^2 + m$sigma2[1]), m$b[1] + t * sqrt(m$se^2 + m$sigma2[1])))
}
res <- list(TEST = fit1(te), TRAIN = fit1(tr))
both <- rbind(tr, te)
if (length(unique(te$study_id)) >= 5) {
  both$is_test <- as.numeric(both$dataset == "TEST")
  m <- rma.mv(lnRR, vi, mods = ~ is_test, random = ~ 1 | study_id / contrast_id, data = both, method = "REML", test = "t")
  ct <- coef_test(m, vcov = "CR2", cluster = both$study_id)
  ci <- conf_int(m, vcov = "CR2", cluster = both$study_id)
  res$TRAIN_vs_TEST <- list(diff_TEST_minus_TRAIN = as.numeric(m$b[2]), se_CR2 = ct$SE[2], df = ct$df_Satt[2],
                            p_CR2 = ct$p_Satt[2], ci95_CR2 = c(ci$CI_L[2], ci$CI_U[2]))
  res$TRAIN_plus_TEST <- fit1(both)
}
res$R_version <- R.version.string
write(toJSON(res, auto_unbox = TRUE, digits = 10, pretty = TRUE), a[3])
cat("done\n")
