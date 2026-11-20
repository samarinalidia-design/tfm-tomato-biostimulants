# H10 - exploratory syntheses for TFM sections 4.5-4.7 (TRAIN_DEV only; TEST not used).
#  (1) STRICT S x B interaction  ln(SB/S) - ln(B/C)        yield and dry biomass
#  (2) A x B interaction         ln[(AB*C)/(A*B)]          (>0 synergy, 0 additive, <0 antagonism; multiplicative scale)
#  (3) single-moderator meta-regressions on the V3.1 yield TRAIN (composition flags, physical measures)
# Weighted: rma.mv(study / contrast, REML) on rows with a sampling variance, CR2 cluster-robust tests (clubSandwich).
# Unweighted: one mean per study, t-interval over studies (uses all rows).
suppressPackageStartupMessages({library(metafor); library(clubSandwich)})
args <- commandArgs(trailingOnly = FALSE)
here <- dirname(normalizePath(sub("--file=", "", args[grep("--file=", args)])))
V4 <- dirname(here)
OUTD <- file.path(V4, "outputs", "interactions"); dir.create(OUTD, showWarnings = FALSE)

pool <- function(d, label) {
  d <- d[is.finite(d$effect), ]
  sm <- tapply(d$effect, d$study_id, mean)
  k <- length(sm)
  un <- if (k >= 2) { tt <- t.test(sm); c(mean(sm), tt$conf.int) } else c(mean(sm), NA, NA)
  w <- d[is.finite(d$var_effect) & d$var_effect > 0, ]
  kw <- length(unique(w$study_id))
  res <- data.frame(set = label, k_studies = k, n = nrow(d), unw_mu = un[1], unw_lo = un[2], unw_hi = un[3],
                    k_w = kw, n_w = nrow(w), w_mu = NA, w_lo = NA, w_hi = NA, tau2_b = NA, tau2_w = NA, pi_lo = NA, pi_hi = NA)
  if (kw >= 3) {
    w$cid <- seq_len(nrow(w))
    f <- tryCatch(rma.mv(effect, var_effect, random = ~ 1 | study_id / cid, data = w, method = "REML"), error = function(e) NULL)
    if (!is.null(f)) {
      ct <- coef_test(f, vcov = "CR2", cluster = w$study_id)
      ci <- conf_int(f, vcov = "CR2", cluster = w$study_id)
      p <- predict(f)
      res$w_mu <- f$beta[1]; res$w_lo <- ci$CI_L[1]; res$w_hi <- ci$CI_U[1]
      res$tau2_b <- f$sigma2[1]; res$tau2_w <- f$sigma2[2]
      res$pi_lo <- f$beta[1] - qt(0.975, max(kw - 1, 1)) * sqrt(f$sigma2[1] + ci$SE[1]^2)
      res$pi_hi <- f$beta[1] + qt(0.975, max(kw - 1, 1)) * sqrt(f$sigma2[1] + ci$SE[1]^2)
    }
  }
  res
}

sxb <- read.csv(file.path(V4, "data", "A_strict_SxB.csv"), stringsAsFactors = FALSE)
axb <- read.csv(file.path(V4, "data", "A_strict_AxB.csv"), stringsAsFactors = FALSE)
P <- rbind(pool(sxb[sxb$endpoint == "FRUIT_YIELD", ], "SxB_yield"),
           pool(sxb[sxb$endpoint == "DRY_BIOMASS", ], "SxB_biomass"),
           pool(axb[axb$endpoint == "FRUIT_YIELD", ], "AxB_yield"),
           pool(axb[axb$endpoint == "DRY_BIOMASS", ], "AxB_biomass"),
           pool(axb, "AxB_all"))
write.csv(P, file.path(OUTD, "interaction_pooled.csv"), row.names = FALSE)

# per-study A x B and S x B summaries (for forest / distribution panels)
st <- function(d) {
  d <- d[is.finite(d$effect), ]
  a <- aggregate(effect ~ study_id + endpoint, d, mean)
  n <- aggregate(effect ~ study_id + endpoint, d, length); names(n)[3] <- "n"
  v <- aggregate(var_effect ~ study_id + endpoint, d[is.finite(d$var_effect), ], function(x) mean(x) / length(x))
  m <- merge(merge(a, n), v, all.x = TRUE)
  m
}
write.csv(st(axb), file.path(OUTD, "axb_by_study.csv"), row.names = FALSE)
write.csv(st(sxb), file.path(OUTD, "sxb_by_study.csv"), row.names = FALSE)

# (3) single-moderator meta-regressions on the yield TRAIN (vi imputed and shared-control V as in h03)
src_lines <- readLines(file.path(here, "h03_rma_mv.R"))
eval(parse(text = src_lines[grep("^impute <- function", src_lines):(grep("^pooled <- function", src_lines) - 1)]))
d <- read.csv(file.path(V4, "data", "TRAIN_HARMONIZED.csv"), stringsAsFactors = FALSE)
d$group_id <- as.character(d$study_id)
iv <- impute(d, d); V <- vmat(d, iv); d$cid <- seq_len(nrow(d))
mods <- c("comp_bacteria", "comp_amf", "comp_fungi_other", "comp_seaweed", "comp_protein_aa", "comp_chitosan",
          "comp_silicon", "comp_organic_amend", "comp_hormone", "comp_living_microbe", "n_components",
          "relative_stress_level", "log_dose_within_family_v3", "log_application_count", "salinity_dSm_equiv_v3",
          "drought_supply_pct_v3", "is_field", "stress_is_ambient")
out <- list()
for (m in mods) {
  x <- d[[m]]
  if (is.logical(x)) x <- as.numeric(x)
  if (is.character(x)) x <- as.numeric(x %in% c("True", "TRUE", "1"))
  ok <- is.finite(x)
  k1 <- length(unique(d$group_id[ok]))
  binary <- all(x[ok] %in% c(0, 1))
  if (binary && (length(unique(d$group_id[ok & x == 1])) < 5 || length(unique(d$group_id[ok & x == 0])) < 5)) next
  if (k1 < 10) next
  xs <- if (binary) x[ok] else (x[ok] - mean(x[ok])) / sd(x[ok])
  dd <- d[ok, ]; dd$xs <- xs
  Vs <- V[ok, ok]
  f <- tryCatch(rma.mv(lnRR, Vs, mods = ~ xs, random = ~ 1 | group_id / cid, data = dd, method = "REML"), error = function(e) NULL)
  if (is.null(f)) next
  ct <- coef_test(f, vcov = "CR2", cluster = dd$group_id)
  ci <- conf_int(f, vcov = "CR2", cluster = dd$group_id)
  out[[m]] <- data.frame(moderator = m, type = ifelse(binary, "binary (present vs absent)", "numeric (per 1 SD)"),
                         k_studies = k1, n = nrow(dd), k_with = if (binary) length(unique(dd$group_id[dd$xs == 1])) else NA,
                         beta = f$beta[2], lo = ci$CI_L[2], hi = ci$CI_U[2], p_CR2 = ct$p_Satt[2],
                         tau2_b = f$sigma2[1])
}
R <- do.call(rbind, out)
R$p_holm <- p.adjust(R$p_CR2, "holm")
write.csv(R, file.path(OUTD, "moderator_metaregression_yield.csv"), row.names = FALSE)
print(P); print(R)
