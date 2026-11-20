# H6 - final fit of the pre-registered model on ALL TRAIN contrasts (403 / 69 studies):
# rma.mv(lnRR, V, random = ~ 1 | study / contrast, REML), V with shared-control covariances, vi imputed as in h03.
suppressPackageStartupMessages(library(metafor))
args <- commandArgs(trailingOnly = FALSE)
here <- dirname(normalizePath(sub("--file=", "", args[grep("--file=", args)])))
V4 <- dirname(here)
src_lines <- readLines(file.path(here, "h03_rma_mv.R"))
# reuse impute() and vmat() verbatim from h03 (definitions only)
eval(parse(text = src_lines[grep("^impute <- function", src_lines):(grep("^pooled <- function", src_lines) - 1)]))
d <- read.csv(file.path(V4, "data", "TRAIN_HARMONIZED.csv"), stringsAsFactors = FALSE)
d$group_id <- as.character(d$study_id)
iv <- impute(d, d)
V <- vmat(d, iv)
d$cid <- seq_len(nrow(d))
f <- rma.mv(lnRR, V, random = ~ 1 | group_id / cid, data = d, method = "REML")
cv2 <- median(c(d$cv2_t, d$cv2_c), na.rm = TRUE)
out <- list(mu = as.numeric(f$beta[1]), se = as.numeric(f$se), sigma2_study = f$sigma2[1], sigma2_contrast = f$sigma2[2],
            ci95 = c(f$ci.lb, f$ci.ub), k = f$k, n_studies = length(unique(d$group_id)),
            cv2_pooled = cv2, n_t_median = median(d$n_t, na.rm = TRUE), n_c_median = median(d$n_c, na.rm = TRUE),
            share_vi_imputed = mean(is.na(d$vi) | d$vi <= 0), metafor = as.character(packageVersion("metafor")),
            R = R.version.string)
writeLines(jsonlite_free <- paste0("{", paste(sprintf('"%s": %s', names(out),
  sapply(out, function(x) if (is.character(x)) sprintf('"%s"', x) else if (length(x) > 1)
    sprintf("[%s]", paste(format(x, digits = 15), collapse = ", ")) else format(x, digits = 15))), collapse = ", "), "}"),
  file.path(V4, "outputs", "rma", "full_train_fit.json"))
print(f)
