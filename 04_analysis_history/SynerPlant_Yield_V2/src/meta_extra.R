# Additional (EXPLORATORY, post-TEST) meta-analyses for the TFM: study-level forest data, subgroup models,
# moderator meta-regression and small-study / publication-bias diagnostics.
# Model: rma.mv REML, random ~1|study/contrast, CR2 cluster-robust inference by study (clubSandwich).
# Usage: Rscript meta_extra.R <primary_csv> <out_dir>
suppressPackageStartupMessages({library(metafor); library(clubSandwich); library(jsonlite)})
a <- commandArgs(trailingOnly = TRUE)
out <- a[2]; dir.create(out, showWarnings = FALSE, recursive = TRUE)
d <- read.csv(a[1], stringsAsFactors = FALSE)
d <- d[!is.na(d$vi) & d$vi > 0 & !is.na(d$lnRR), ]
d$study_id <- as.character(d$study_id)
d$sei <- sqrt(d$vi)
fitmv <- function(x, f = NULL) {
  args <- list(yi = quote(lnRR), V = quote(vi), random = ~ 1 | study_id / contrast_id, data = x,
               method = "REML", test = "t", sparse = TRUE)
  if (!is.null(f)) args$mods <- f
  do.call(rma.mv, args)
}
m0 <- fitmv(d)
ci0 <- conf_int(m0, vcov = "CR2", cluster = d$study_id)
res <- list(overall = list(k = length(unique(d$study_id)), n = nrow(d), mu = as.numeric(m0$b[1]),
                           ci = c(ci0$CI_L, ci0$CI_U)))

# ---- 1. study-level effects for the forest plot (contrasts aggregated within study, rho = 0.5)
es <- escalc(measure = "GEN", yi = lnRR, vi = vi, data = d)
ag <- aggregate(es, cluster = study_id, rho = 0.5, struct = "CS")
ag$ci_lo <- ag$yi - 1.96 * sqrt(ag$vi); ag$ci_hi <- ag$yi + 1.96 * sqrt(ag$vi)
ag$n_contrasts <- as.numeric(table(d$study_id)[ag$study_id])
w <- weights(m0); ag$weight_pct <- as.numeric(tapply(w, d$study_id, sum)[ag$study_id])
write.csv(ag[, c("study_id", "yi", "vi", "ci_lo", "ci_hi", "n_contrasts", "weight_pct",
                 intersect(c("stress_family", "biostimulant_class", "doi", "year"), names(ag)))],
          file.path(out, "forest_studies.csv"), row.names = FALSE)

# ---- 2. subgroups and moderator meta-regression (levels with < 4 studies pooled into OTHER)
collapse <- function(v, s) { k <- tapply(s, v, function(z) length(unique(z))); v[v %in% names(k)[k < 4] | is.na(v) | v == ""] <- "OTHER"; v }
mods <- intersect(c("stress_family", "biostimulant_class", "application_route", "cultivation_system"), names(d))
sub <- list(); mreg <- list()
for (mo in mods) {
  x <- d; x$g <- collapse(as.character(x[[mo]]), x$study_id)
  if (length(unique(x$g)) < 2) next
  m <- tryCatch(fitmv(x, ~ 0 + factor(g)), error = function(e) NULL)
  if (is.null(m)) next
  ci <- conf_int(m, vcov = "CR2", cluster = x$study_id)
  lv <- sub("factor\\(g\\)", "", rownames(m$b))
  ks <- sapply(lv, function(l) length(unique(x$study_id[x$g == l])))
  ns <- sapply(lv, function(l) sum(x$g == l))
  sub[[mo]] <- data.frame(moderator = mo, level = lv, k_studies = ks, n = ns, mu = as.numeric(m$b),
                          ci_lo = ci$CI_L, ci_hi = ci$CI_U, df = ci$df)
  p <- length(lv)
  C <- cbind(-1, diag(p - 1))
  wt <- tryCatch(Wald_test(m, constraints = C, vcov = "CR2", cluster = x$study_id, test = "HTZ"), error = function(e) NULL)
  m1 <- fitmv(x, ~ factor(g))
  r2 <- max(0, 1 - sum(m1$sigma2) / sum(m0$sigma2))
  mreg[[mo]] <- list(moderator = mo, levels = p, F_HTZ = if (!is.null(wt)) wt$Fstat else NA,
                     df_num = if (!is.null(wt)) wt$df_num else NA, df_den = if (!is.null(wt)) wt$df_denom else NA,
                     p_HTZ = if (!is.null(wt)) wt$p_val else NA, pseudo_R2_tau2 = r2,
                     tau2_between_without = m0$sigma2[1], tau2_between_with = m1$sigma2[1])
}
write.csv(do.call(rbind, sub), file.path(out, "subgroups_CR2.csv"), row.names = FALSE)
res$moderator_tests <- unname(mreg)

# ---- 3. small-study effects / publication bias
egg <- fitmv(d, ~ sei)                               # multilevel Egger (PET): slope on SE
ce <- coef_test(egg, vcov = "CR2", cluster = d$study_id)
cie <- conf_int(egg, vcov = "CR2", cluster = d$study_id)
pee <- fitmv(d, ~ vi)                                # PEESE
cip <- conf_int(pee, vcov = "CR2", cluster = d$study_id)
ctp <- coef_test(pee, vcov = "CR2", cluster = d$study_id)
pet_p <- ce$p_Satt[1]
res$egger_multilevel <- list(slope_on_SE = as.numeric(egg$b[2]), slope_p_CR2 = ce$p_Satt[2],
                             slope_ci = c(cie$CI_L[2], cie$CI_U[2]),
                             PET_intercept = as.numeric(egg$b[1]), PET_ci = c(cie$CI_L[1], cie$CI_U[1]), PET_p = pet_p,
                             PEESE_intercept = as.numeric(pee$b[1]), PEESE_ci = c(cip$CI_L[1], cip$CI_U[1]),
                             PET_PEESE_estimate = if (pet_p < 0.05) as.numeric(pee$b[1]) else as.numeric(egg$b[1]),
                             rule = "PET-PEESE: PEESE intercept if the PET intercept is significant (p<0.05), else PET")
sm <- rma(yi, vi, data = ag, method = "REML")       # study-level (aggregated) random-effects model
tf <- trimfill(sm)
rk <- ranktest(sm)
rg <- regtest(sm, model = "rma", predictor = "sei")
res$study_level <- list(k = sm$k, mu = as.numeric(sm$b), ci = c(sm$ci.lb, sm$ci.ub), tau2 = sm$tau2, I2 = sm$I2,
                        egger_z = rg$zval, egger_p = rg$pval, begg_tau = as.numeric(rk$tau), begg_p = rk$pval,
                        trimfill_k0 = tf$k0, trimfill_side = tf$side, trimfill_mu = as.numeric(tf$b),
                        trimfill_ci = c(tf$ci.lb, tf$ci.ub))
fd <- data.frame(study_id = ag$study_id, yi = ag$yi, sei = sqrt(ag$vi), filled = FALSE)
if (tf$k0 > 0) {
  fill <- data.frame(study_id = paste0("FILLED_", seq_len(tf$k0)), yi = tail(tf$yi, tf$k0),
                     sei = sqrt(tail(tf$vi, tf$k0)), filled = TRUE)
  fd <- rbind(fd, fill)
}
write.csv(fd, file.path(out, "funnel_studies.csv"), row.names = FALSE)
write.csv(data.frame(contrast_id = d$contrast_id, study_id = d$study_id, yi = d$lnRR, sei = d$sei),
          file.path(out, "funnel_contrasts.csv"), row.names = FALSE)
res$R_version <- R.version.string
write(toJSON(res, auto_unbox = TRUE, digits = 8, pretty = TRUE, na = "null"), file.path(out, "meta_extra.json"))
cat("done\n")
