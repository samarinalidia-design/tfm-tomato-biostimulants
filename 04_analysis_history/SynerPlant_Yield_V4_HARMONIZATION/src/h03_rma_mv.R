# H3 - multilevel meta-regression (advice 2 + 3) and location-scale meta-analysis (advice 5) on the SAME outer folds.
# Prediction for a held-out study uses the fixed part only (its own random effect is unknown for a new study).
# vi imputed in-fold exactly as in h02_cv.impute_vi; contrasts that share one control arm get covariance
# cv2_c / n_c (the sampling variance of ln(control mean)).  TEST is never read.
suppressPackageStartupMessages(library(metafor))
args <- commandArgs(trailingOnly = FALSE)
here <- dirname(normalizePath(sub("--file=", "", args[grep("--file=", args)])))
V4 <- dirname(here)
d <- read.csv(file.path(V4, "data", "TRAIN_HARMONIZED.csv"), stringsAsFactors = FALSE)
d$group_id <- as.character(d$study_id)
folds <- read.csv(file.path(V4, "outputs", "folds.csv"), stringsAsFactors = FALSE)
folds$group_id <- as.character(folds$group_id)
COMP <- c("comp_bacteria", "comp_amf", "comp_fungi_other", "comp_seaweed", "comp_humic", "comp_protein_aa",
          "comp_chitosan", "comp_silicon", "comp_selenium", "comp_organic_amend", "comp_hormone",
          "comp_osmolyte_antiox", "comp_botanical", "comp_cell_free", "comp_living_microbe")
MINS <- 5

impute <- function(tr, df, prior = FALSE) {   # prior = TRUE: new experiment, only n is known (no own SD)
  cv2 <- median(c(tr$cv2_t, tr$cv2_c), na.rm = TRUE)
  ntm <- median(tr$n_t, na.rm = TRUE); ncm <- median(tr$n_c, na.rm = TRUE)
  nt <- ifelse(is.na(df$n_t) | df$n_t <= 0, ntm, df$n_t)
  nc <- ifelse(is.na(df$n_c) | df$n_c <= 0, ncm, df$n_c)
  cvt <- if (prior) rep(cv2, nrow(df)) else ifelse(is.na(df$cv2_t), cv2, df$cv2_t)
  cvc <- if (prior) rep(cv2, nrow(df)) else ifelse(is.na(df$cv2_c), cv2, df$cv2_c)
  vi <- if (prior) cvt / nt + cvc / nc else ifelse(!is.na(df$vi) & df$vi > 0, df$vi, cvt / nt + cvc / nc)
  data.frame(vi = pmax(vi, 1e-4), covc = cvc / nc)
}

vmat <- function(df, iv) {
  V <- diag(iv$vi)
  sc <- df$shared_control_id
  for (k in unique(sc[duplicated(sc)])) {
    ix <- which(sc == k)
    for (a in ix) for (b in ix) if (a != b) V[a, b] <- min(iv$covc[a], iv$covc[b], 0.95 * sqrt(iv$vi[a] * iv$vi[b]))
  }
  V
}

pooled <- function(x, g, keep = NULL) {
  x[is.na(x) | x %in% c("", "UNMAPPED", "NOT_REPORTED")] <- "MISSING"
  if (is.null(keep)) {
    ns <- tapply(g, x, function(z) length(unique(z)))
    keep <- names(ns)[ns >= MINS & names(ns) != "MISSING"]
  }
  list(v = ifelse(x %in% keep, x, "OTHER"), keep = keep)
}

dummies <- function(v, lev) {           # first level = reference
  if (length(lev) < 2) return(NULL)
  m <- sapply(lev[-1], function(l) as.numeric(v == l))
  if (is.null(dim(m))) m <- matrix(m, nrow = 1)
  colnames(m) <- make.names(paste0("L_", lev[-1])); m
}

design <- function(tr, te, factors, flags) {
  Xa <- NULL; Xb <- NULL
  for (f in factors) {
    pa <- pooled(tr[[f]], tr$group_id); pb <- pooled(te[[f]], te$group_id, pa$keep)
    lev <- names(sort(table(pa$v), decreasing = TRUE))
    pb$v[!pb$v %in% lev] <- lev[1]
    Xa <- cbind(Xa, dummies(pa$v, lev)); Xb <- cbind(Xb, dummies(pb$v, lev))
  }
  for (f in flags) {
    if (length(unique(tr$group_id[tr[[f]] == 1])) >= MINS && length(unique(tr$group_id[tr[[f]] == 0])) >= MINS) {
      Xa <- cbind(Xa, setNames(data.frame(tr[[f]]), f)); Xb <- cbind(Xb, setNames(data.frame(te[[f]]), f))
    }
  }
  Xa <- as.matrix(Xa); Xb <- as.matrix(Xb)
  keep <- apply(Xa, 2, function(z) var(z) > 0)
  list(a = unname(Xa[, keep, drop = FALSE]), b = unname(Xb[, keep, drop = FALSE]))
}

Z <- qnorm(0.95)
fit_mv <- function(tr, te, iv_tr, iv_te, X) {
  V <- vmat(tr, iv_tr)
  tr$cid <- seq_len(nrow(tr))
  f <- tryCatch(if (is.null(X)) rma.mv(lnRR, V, random = ~ 1 | group_id / cid, data = tr, method = "REML")
                else rma.mv(lnRR, V, mods = X$a, random = ~ 1 | group_id / cid, data = tr, method = "REML"),
                error = function(e) NULL)
  if (is.null(f)) return(NULL)
  p <- if (is.null(X)) predict(f) else predict(f, newmods = X$b)
  mu <- if (is.null(X)) rep(as.numeric(p$pred), nrow(te)) else as.numeric(p$pred)
  se <- if (is.null(X)) rep(as.numeric(p$se), nrow(te)) else as.numeric(p$se)
  list(pred = mu, half = Z * sqrt(sum(f$sigma2) + iv_te$vi + se^2), tau2 = sum(f$sigma2))
}

fit_ls <- function(tr, te, iv_tr, iv_te, Xloc, Xsc) {
  args <- list(yi = tr$lnRR, vi = iv_tr$vi, method = "ML", scale = Xsc$a)
  if (!is.null(Xloc)) args$mods <- Xloc$a
  f <- tryCatch(do.call(rma, args), error = function(e) NULL)
  if (is.null(f)) return(NULL)
  # scale part: log(tau2) = Z gamma  -> tau2(x) for the new rows
  ps <- tryCatch(predict(f, newscale = Xsc$b, transf = exp), error = function(e) NULL)
  if (is.null(ps)) return(NULL)
  tau2 <- as.numeric(ps$pred)
  if (is.null(Xloc)) {
    mu <- rep(as.numeric(f$beta[1]), nrow(te)); se <- rep(as.numeric(f$se[1]), nrow(te))
  } else {
    p <- tryCatch(predict(f, newmods = Xloc$b, newscale = Xsc$b), error = function(e) NULL)
    if (is.null(p)) return(NULL)
    mu <- as.numeric(p$pred); se <- as.numeric(p$se)
  }
  list(pred = mu, half = Z * sqrt(tau2 + iv_te$vi + se^2), tau2 = mean(tau2))
}

out <- list(); fails <- list()
for (s in unique(folds$seed)) for (k in unique(folds$fold)) {
  tg <- folds$group_id[folds$seed == s & folds$fold == k]
  tr <- d[!d$group_id %in% tg, ]; te <- d[d$group_id %in% tg, ]
  iv_tr <- impute(tr, tr); iv_te <- impute(tr, te, prior = TRUE)
  XC <- design(tr, te, c("stress_family"), COMP)
  XB <- design(tr, te, c("stress_family", "biostimulant_class"), character(0))
  XS <- design(tr, te, c("stress_family"), character(0))
  XS2 <- design(tr, te, c("stress_family", "cultivation_system"), c("comp_living_microbe"))
  res <- list(
    "rma_mv|intercept" = fit_mv(tr, te, iv_tr, iv_te, NULL),
    "rma_mv|stress+comp" = fit_mv(tr, te, iv_tr, iv_te, XC),
    "rma_mv|stress+class" = fit_mv(tr, te, iv_tr, iv_te, XB),
    "ls|loc1_scale_stress" = fit_ls(tr, te, iv_tr, iv_te, NULL, XS),
    "ls|loc1_scale_stress_sys_microbe" = fit_ls(tr, te, iv_tr, iv_te, NULL, XS2),
    "ls|loc_stress+comp_scale_stress" = fit_ls(tr, te, iv_tr, iv_te, XC, XS))
  for (nm in names(res)) {
    r <- res[[nm]]
    if (is.null(r)) { fails[[length(fails) + 1]] <- data.frame(candidate = nm, seed = s, fold = k); next }
    out[[length(out) + 1]] <- data.frame(contrast_id = te$contrast_id, study_id = te$study_id, group_id = te$group_id,
                                         lnRR = te$lnRR, pred = r$pred, half90 = r$half, tau2 = r$tau2,
                                         candidate = nm, seed = s, fold = k)
  }
  cat(s, k, "\n")
}
dir.create(file.path(V4, "outputs", "rma"), showWarnings = FALSE)
write.csv(do.call(rbind, out), file.path(V4, "outputs", "rma", "rma_predictions.csv"), row.names = FALSE)
write.csv(if (length(fails)) do.call(rbind, fails) else data.frame(candidate = character(0)),
          file.path(V4, "outputs", "rma", "rma_failures.csv"), row.names = FALSE)
cat("done\n")
