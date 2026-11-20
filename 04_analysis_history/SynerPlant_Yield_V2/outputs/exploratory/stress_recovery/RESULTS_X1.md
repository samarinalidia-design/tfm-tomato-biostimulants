# X1 — Stress damage and recovered losses (EXPLORATORY: after the V2 freeze, before the TEST)

**Code:** `src/x01_stress_recovery.py`. It does not change the frozen V2 release.

**Sample.** Factorial experiments with all four arms (C, S, B, SB) linked to PRIMARY_EXPANDED contrasts:
- 224 contrasts from 42 studies, out of 404 contrasts from 69 studies;
- mostly drought (20 studies) and salinity (19 studies);
- about 49 % of arm sampling errors imputed from the pooled CV.

| Quantity | Median (contrasts) | Interpretation |
|---|---|---|
| D = ln(S/C) | −0.39 | stress lowers yield by about 32 % |
| ln(SB/S) | 0.26 | biostimulant effect under stress, about +29 % |
| ln(B/C) | 0.18 | biostimulant effect without stress, about +19 % |
| ln(SB/C) | −0.08 | SB reaches or exceeds C in only 41 % of contrasts |
| Recovered share of the log-loss, RL | 0.64 (IQR 0.33–1.12) | the biostimulant recovers roughly two thirds of the stress loss |
| ln(SB/S) − ln(B/C) | +0.07; positive in 67 % | the effect under stress is somewhat larger than without stress (descriptive; not a formal S × B test) |

**Stress gradient: study-level association between damage and effect**

| Measure | Observed | Coupling artefact (null) |
|---|---|---|
| Slope of ln(SB/S) on D, between studies | −0.59 (95 % CI −0.74 to −0.41; study bootstrap) | −0.02 (−0.35 to +0.26) |
| R² of study means of ln(SB/S) on D | 0.57 | 0.015 (97.5 % quantile 0.17) |
| Slope within studies | −0.25 | −0.25 |

The null is a simulated world in which the effect does not depend on damage, with each arm's sampling error drawn
anew.

- **Between studies the association is real.** The stronger the stress damage in an experiment, the larger the
  biostimulant effect. Study-level damage explains about 57 % of the between-study variance of the effect in this
  subset.
- **Within studies the association is fully explained by the coupling artefact** (shared sampling error in S). There
  is no evidence of a within-study gradient.
- **The unstressed effect ln(B/C) shares no arm with the target** and explains 26 % of the between-study variance
  (slope 0.83).

**Predictive check: grouped 5 × 5 CV on the same 42 studies**

| Model | group-MAE | Null world | Gain vs median |
|---|---|---|---|
| median | 0.348 | 0.361 | — |
| a + b·D | 0.279 | 0.365 | −20 % |
| recovered share × (−D) | 0.259 | 0.429 | −25 % |
| a + b·ln(B/C) | 0.275 | 0.364 | −21 % |
| a + b·D + c·ln(B/C) | **0.215** | 0.373 | **−38 %** |

In the null worlds none of these models beats the median. The observed gains are therefore not produced by the
coupling.

**Limits.**
- D and ln(B/C) come from the same experiment, so they are known only after it. They describe experiments; they are
  not forecasts made before the experiment.
- Using them for prediction requires the expected damage to be known in advance (from a prior season, from
  stress-intensity → damage curves, or from a pre-registered severity). The next step is therefore to collect the
  a-priori stress intensity and model intensity → expected damage.
- Only factorial studies are included (42 of 69), which is a selection.
- The analysis was done after the freeze. To claim the gain, pre-register these models before opening the TEST and
  evaluate them there once.
