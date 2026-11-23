# Copy of V5 v5_05_meta.R (statistics unchanged) applied to the chlorophyll targets; only the endpoint list differs and the S x B / A x B interaction part is dropped.
# V5 meta-analysis for figures/tables (descriptive pooled estimates; not the ML predictions).
# rma.mv REML, random ~1|study_id/contrast_id, V = sampling variances (var_lnrr_imp: author SD where available,
# otherwise Nakagawa 2023 CV-bar imputation -- imputed variances are NOT author-reported) with shared-control
# covariance (CV_c^2/n_c for contrasts sharing shared_control_id). Robust CR2 inference (clubSandwich), t tests.
suppressPackageStartupMessages({library(Matrix); library(metafor); library(clubSandwich); library(jsonlite); library(data.table)})
args <- commandArgs(trailingOnly = TRUE)
V5 <- if (length(args)) args[1] else "."
D <- file.path(V5, "data"); O <- file.path(V5, "results", "meta"); dir.create(O, showWarnings = FALSE, recursive = TRUE)

rd <- function(f) { x <- fread(file.path(D, f), encoding = "UTF-8"); as.data.frame(x) }
prep <- function(x, default = TRUE) {
  if (default) x <- x[x$in_default == 1, ]
  x <- x[is.finite(x$effect) & is.finite(x$var_lnrr_imp) & x$var_lnrr_imp > 0, ]
  x$yi <- x$effect; x$vi <- x$var_lnrr_imp
  x$sc <- ifelse(is.na(x$shared_control_id) | x$shared_control_id == "", x$contrast_id, x$shared_control_id)
  x
}
Vmat <- function(x) {
  n <- nrow(x); cc <- x$cv_used_c^2 / x$n_imp_c
  ii <- seq_len(n); jj <- seq_len(n); vv <- x$vi
  for (g in unique(x$sc[duplicated(x$sc)])) { i <- which(x$sc == g); if (length(i) > 1) {
    pr <- expand.grid(a = i, b = i); pr <- pr[pr$a != pr$b, ]
    ii <- c(ii, pr$a); jj <- c(jj, pr$b); vv <- c(vv, pmin(cc[pr$a], cc[pr$b])) } }
  Matrix::sparseMatrix(i = ii, j = jj, x = vv, dims = c(n, n))
}
fit <- function(x, mods = ~1) {
  V <- Vmat(x)
  m <- tryCatch(rma.mv(x$yi, V, mods = mods, random = ~ 1 | study_id / contrast_id, data = x, test = "t", sparse = TRUE,
                       control = list(optimizer = "optim")), error = function(e) NULL)
  m
}
pool <- function(x, label) {
  k <- nrow(x); ns <- length(unique(x$study_id))
  if (ns < 2) return(data.frame(set = label, k = k, studies = ns, mu = NA, ci_lo = NA, ci_hi = NA, pi_lo = NA, pi_hi = NA, tau2_study = NA, tau2_within = NA, I2 = NA))
  m <- fit(x); if (is.null(m)) return(NULL)
  rob <- tryCatch(conf_int(m, vcov = "CR2", cluster = x$study_id), error = function(e) NULL)
  lo <- if (!is.null(rob)) rob$CI_L[1] else m$ci.lb; hi <- if (!is.null(rob)) rob$CI_U[1] else m$ci.ub
  se <- if (!is.null(rob)) rob$SE[1] else m$se
  pr <- predict(m)
  W <- solve(m$V); X <- model.matrix(m); P <- W - W %*% X %*% solve(t(X) %*% W %*% X) %*% t(X) %*% W
  I2 <- 100 * sum(m$sigma2) / (sum(m$sigma2) + (m$k - m$p) / sum(diag(P)))
  tcrit <- qt(0.975, max(ns - 1, 1)); pis <- sqrt(sum(m$sigma2) + se^2)
  data.frame(set = label, k = k, studies = ns, mu = as.numeric(m$b[1]), se_CR2 = se, ci_lo = lo, ci_hi = hi,
             pi_lo = as.numeric(m$b[1]) - tcrit * pis, pi_hi = as.numeric(m$b[1]) + tcrit * pis,
             tau2_study = m$sigma2[1], tau2_within = m$sigma2[2], I2 = I2, typical_vi = (m$k - m$p) / sum(diag(P)))
}

EP <- list(chl_index = c("train_chl_index.csv", "test_chl_index.csv"), chlorophyll = c("train_chlorophyll.csv", "test_chlorophyll.csv"))
summ <- list(); sub <- list(); forest <- list(); loo <- list(); bias <- list(); mat <- list(); modr <- list()
for (ep in names(EP)) {
  tr <- prep(rd(EP[[ep]][1])); te <- prep(rd(EP[[ep]][2]))
  trall <- prep(rd(EP[[ep]][1]), default = FALSE)
  both <- rbind(tr[, intersect(names(tr), names(te))], te[, intersect(names(tr), names(te))])
  sets <- list(TRAIN_primary = tr, TRAIN_SB_vs_S_only = tr[tr$contrast_type == "SB_vs_S", ],
               TRAIN_author_SD_only = tr[tr$variance_from_author_sd == 1, ], TEST = te, TRAIN_plus_TEST = both)
  if (ep == "yield") sets$TRAIN_STRICT <- tr[tr$yield_tier == "STRICT", ]
  if (ep == "biomass") sets$TRAIN_all_timepoints <- trall[trall$is_boxplot == 0, ]
  s <- do.call(rbind, lapply(names(sets), function(n) pool(sets[[n]], n))); s$endpoint <- ep; summ[[ep]] <- s
  # TEST - TRAIN difference
  both$is_test <- as.numeric(both$dataset_role_v5 == "TEST")
  md <- fit(both, ~ is_test)
  if (!is.null(md)) { r <- coef_test(md, vcov = "CR2", cluster = both$study_id)
    summ[[paste0(ep, "_diff")]] <- data.frame(set = "TEST_minus_TRAIN", k = nrow(both), studies = length(unique(both$study_id)),
      mu = r$beta[2], se_CR2 = r$SE[2], ci_lo = r$beta[2] - qt(.975, r$df_Satt[2]) * r$SE[2], ci_hi = r$beta[2] + qt(.975, r$df_Satt[2]) * r$SE[2],
      pi_lo = NA, pi_hi = NA, tau2_study = NA, tau2_within = NA, I2 = NA, typical_vi = r$p_Satt[2], endpoint = ep) }
  # subgroups (TRAIN): levels with >= 4 studies, others -> other
  for (g in c("h_stress_class", "h2_dujardin", "h_route", "h_system")) {
    x <- tr; ns <- tapply(x$study_id, x[[g]], function(v) length(unique(v))); keep <- names(ns)[ns >= 4]
    x$grp <- ifelse(x[[g]] %in% keep, x[[g]], "other"); x$grp <- factor(x$grp)
    m0 <- fit(x); m1 <- fit(x, ~ 0 + grp)
    if (is.null(m1)) next
    rob <- conf_int(m1, vcov = "CR2", cluster = x$study_id)
    w <- tryCatch(Wald_test(fit(x, ~ grp), constraints = constrain_zero(2:nlevels(x$grp)), vcov = "CR2", cluster = x$study_id), error = function(e) NULL)
    pr2 <- if (!is.null(m0)) max(0, 1 - sum(m1$sigma2) / sum(m0$sigma2)) else NA
    sub[[paste(ep, g)]] <- data.frame(endpoint = ep, moderator = g, level = sub("^grp", "", rob$Coef), mu = rob$beta, ci_lo = rob$CI_L, ci_hi = rob$CI_U,
      studies = as.numeric(sapply(sub("^grp", "", rob$Coef), function(l) length(unique(x$study_id[x$grp == l])))),
      k = as.numeric(sapply(sub("^grp", "", rob$Coef), function(l) sum(x$grp == l))),
      p_HTZ = if (!is.null(w)) w$p_val else NA, pseudoR2_tau = pr2)
  }
  # forest: study aggregates (rho = 0.5 within study), with rma.mv weights
  m <- fit(tr); wts <- weights(m)
  es <- escalc(measure = "GEN", yi = yi, vi = vi, data = tr)
  ag <- aggregate(es, cluster = study_id, rho = 0.5, struct = "CS")
  agw <- tapply(wts, tr$study_id, sum)
  forest[[ep]] <- data.frame(endpoint = ep, study_id = ag$study_id, yi = ag$yi, vi = ag$vi, k = as.numeric(table(tr$study_id)[ag$study_id]),
                             weight_pct = as.numeric(agw[ag$study_id]))
  # publication bias on study aggregates + multilevel Egger / PET-PEESE
  ra <- rma(yi, vi, data = ag, method = "REML")
  tf <- trimfill(ra); eg <- regtest(ra); rk <- ranktest(ra)
  tr$sei <- sqrt(tr$vi)
  pet <- fit(tr, ~ sei); peese <- fit(tr, ~ vi)
  pc <- coef_test(pet, vcov = "CR2", cluster = tr$study_id); qc <- coef_test(peese, vcov = "CR2", cluster = tr$study_id)
  bias[[ep]] <- data.frame(endpoint = ep, k_studies = nrow(ag), egger_regtest_p = eg$pval, begg_ranktest_p = rk$pval,
    ml_egger_slope = pc$beta[2], ml_egger_p = pc$p_Satt[2], PET_mu = pc$beta[1], PEESE_mu = qc$beta[1],
    REML_study_level_mu = as.numeric(ra$b), trimfill_mu = as.numeric(tf$b), trimfill_k0 = tf$k0, trimfill_side = tf$side, I2_study_level = ra$I2)
  fwrite(data.frame(endpoint = ep, yi = c(ag$yi, if (tf$k0 > 0) tf$yi[tf$fill] else numeric(0)),
                    sei = sqrt(c(ag$vi, if (tf$k0 > 0) tf$vi[tf$fill] else numeric(0))),
                    filled = c(rep(0, nrow(ag)), rep(1, tf$k0))), file.path(O, paste0("funnel_", ep, ".csv")))
  flush <- function() {
    fwrite(do.call(rbind, summ), file.path(O, "pooled_effects.csv")); fwrite(do.call(rbind, sub), file.path(O, "subgroups_CR2.csv"))
    fwrite(do.call(rbind, forest), file.path(O, "forest_studies.csv")); fwrite(do.call(rbind, bias), file.path(O, "publication_bias.csv"))
    if (length(loo)) fwrite(do.call(rbind, loo), file.path(O, "leave_one_study_out.csv"))
    if (length(mat)) fwrite(do.call(rbind, mat), file.path(O, "class_x_stress_matrix.csv"))
    if (length(modr)) fwrite(do.call(rbind, modr), file.path(O, "moderator_metaregression.csv")) }
  flush(); cat(ep, "core done
")
  # leave-one-study-out
  st <- unique(tr$study_id)
  loo[[ep]] <- do.call(rbind, lapply(st, function(s) { mm <- fit(tr[tr$study_id != s, ]); if (is.null(mm)) return(NULL)
    data.frame(endpoint = ep, left_out = s, mu = as.numeric(mm$b), ci_lo = mm$ci.lb, ci_hi = mm$ci.ub) }))
  # class x stress matrix (TRAIN): pooled (descriptive) mean with CI, prediction interval for a new study, n studies
  cells <- unique(tr[, c("h2_dujardin", "h_stress_class")])
  mat[[ep]] <- do.call(rbind, lapply(seq_len(nrow(cells)), function(i) {
    x <- tr[tr$h2_dujardin == cells$h2_dujardin[i] & tr$h_stress_class == cells$h_stress_class[i], ]
    ns <- length(unique(x$study_id)); sm <- tapply(x$yi, x$study_id, mean)
    o <- data.frame(endpoint = ep, biostimulant_class = cells$h2_dujardin[i], stress = cells$h_stress_class[i], studies = ns, k = nrow(x),
                    median_study_mean = median(sm), mu = NA, ci_lo = NA, ci_hi = NA, pi_lo = NA, pi_hi = NA, estimate_type = "DESCRIPTIVE_MEDIAN_OF_STUDY_MEANS")
    if (ns >= 3) { p <- pool(x, "cell"); if (!is.null(p) && is.finite(p$mu)) {
      o$mu <- p$mu; o$ci_lo <- p$ci_lo; o$ci_hi <- p$ci_hi; o$pi_lo <- p$pi_lo; o$pi_hi <- p$pi_hi; o$estimate_type <- "POOLED_RMA_MV_CR2" } }
    o }))
  # single-moderator meta-regressions (TRAIN, yield and biomass): binary composition flags and numerics (per 1 SD)
  cand <- c("h2_live_microorganism", "h2_nonliving_microbial_product", "h_dj_dj_beneficial_bacteria", "h_dj_dj_beneficial_fungi",
            "h_dj_dj_seaweed_botanical", "h_dj_dj_humic_fulvic", "h_dj_dj_protein_n", "h_dj_dj_inorganic", "h_potted", "is_B_vs_C",
            "h3_route_foliar", "h3_route_soil_drench", "h3_route_seed", "h3_abs_latitude", "h3_log_n_applications", "h_stress_intensity")
  modr[[ep]] <- do.call(rbind, lapply(intersect(cand, names(tr)), function(v) {
    x <- tr[is.finite(as.numeric(tr[[v]])), ]; z <- as.numeric(x[[v]])
    if (length(unique(z)) < 2 || length(unique(x$study_id)) < 6) return(NULL)
    bin <- all(z %in% c(0, 1)); x$z <- if (bin) z else (z - mean(z)) / sd(z)
    mm <- fit(x, ~ z); if (is.null(mm)) return(NULL)
    r <- coef_test(mm, vcov = "CR2", cluster = x$study_id)
    data.frame(endpoint = ep, moderator = v, type = ifelse(bin, "binary (present - absent)", "numeric (per 1 SD)"),
               beta = r$beta[2], se = r$SE[2], df = r$df_Satt[2], p = r$p_Satt[2], k = nrow(x), studies = length(unique(x$study_id)))
  }))
  if (!is.null(modr[[ep]])) modr[[ep]]$p_holm <- p.adjust(modr[[ep]]$p, "holm")
  flush(); cat(ep, "all done
")
}
fwrite(do.call(rbind, summ), file.path(O, "pooled_effects.csv"))
fwrite(do.call(rbind, sub), file.path(O, "subgroups_CR2.csv"))
fwrite(do.call(rbind, forest), file.path(O, "forest_studies.csv"))
fwrite(do.call(rbind, bias), file.path(O, "publication_bias.csv"))
fwrite(do.call(rbind, loo), file.path(O, "leave_one_study_out.csv"))
fwrite(do.call(rbind, mat), file.path(O, "class_x_stress_matrix.csv"))
fwrite(do.call(rbind, modr), file.path(O, "moderator_metaregression.csv"))

cat("done\n")
