# Leave-one-study-out influence on the pooled effect (same model as the confirmatory analysis:
# rma.mv REML, random ~1|study/contrast; CR2 by study). Usage: Rscript influence_loo.R <csv> <out_csv>
suppressPackageStartupMessages({library(metafor); library(clubSandwich)})
a <- commandArgs(trailingOnly = TRUE)
d <- read.csv(a[1], stringsAsFactors = FALSE)
d <- d[!is.na(d$vi) & d$vi > 0 & !is.na(d$lnRR), c("contrast_id", "study_id", "lnRR", "vi")]
d$study_id <- as.character(d$study_id)
fit <- function(x) {
  m <- rma.mv(lnRR, vi, random = ~ 1 | study_id / contrast_id, data = x, method = "REML", test = "t")
  ci <- conf_int(m, vcov = "CR2", cluster = x$study_id)
  c(mu = as.numeric(m$b[1]), lo = ci$CI_L, hi = ci$CI_U, tau2 = m$sigma2[1], k = length(unique(x$study_id)))
}
full <- fit(d)
out <- data.frame(left_out = "NONE", t(full), n_contrasts_left_out = 0)
for (s in unique(d$study_id)) {
  r <- tryCatch(fit(d[d$study_id != s, ]), error = function(e) rep(NA, 5))
  out <- rbind(out, data.frame(left_out = s, t(r), n_contrasts_left_out = sum(d$study_id == s)))
}
write.csv(out, a[2], row.names = FALSE)
cat("done\n")
