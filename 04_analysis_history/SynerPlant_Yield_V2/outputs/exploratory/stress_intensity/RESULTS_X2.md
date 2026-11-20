# X2 — Re-extracted a-priori stress intensity (EXPLORATORY: after the V2 freeze, before the TEST)

**Code:** `src/x02_stress_intensity.py`. **Coding table:** `audit/stress_intensity_curated.csv`. Frozen V2 untouched.

**Re-extraction**
- 98 salinity and drought arm codings.
- 94 confirmed by the same number in the original PDF (`AUTO_VERIFIED_V2`, page recorded). 4 are coded only from
  the verified arm description.
- 11 arms are not comparable and kept as NA: a tiny weekly salt dose, soil % salt, withholding days or rounds, FTSW,
  rain only, a pooled marginal.

| Family | Studies | With intensity in frozen V2 | With intensity now | With external damage model |
|---|---|---|---|---|
| Salinity | 28 | 20 | **26** | 26 (Maas–Hoffman) |
| Drought | 26 | 16 | **19** | 9 (FAO-33, ET-based supply only) |

**Does nominal intensity predict the damage observed in the S arm?** Factorial studies only.
- **Across studies: no.**
  - Maas–Hoffman / FAO-33 expected damage vs observed ln(S/C): Spearman 0.02 (25 studies, p = 0.92). Without the
    FAO-29 1.5 factor: 0.09.
  - Salinity ECe alone: 0.05 (17 studies). Drought ET supply: 0.22 (9). Drought % FC: −0.27 (10). All
    non-significant.
  - The external models overpredict badly. For example, 2 % NaCl irrigation or 150 mM NaCl for 2 weeks "should"
    destroy the crop, yet the observed losses are −0.54 and −0.19. The applied concentration does not capture the
    root-zone exposure (volume, frequency, duration, pot size, leaching, substrate, cultivar tolerance).
- **Within studies: yes.** The more severe level shows the larger damage in 86 % of 49 pairs (14 studies).
- **The biostimulant effect does not follow nominal intensity, even within studies.** The more severe level shows
  the larger effect in only 39 % of pairs, consistent with X1, where the within-study gradient was entirely the
  coupling artefact.

**Prediction (grouped 5 × 5 CV, same splits, a-priori features only)**

| Set | Median | External damage | Intensity scales |
|---|---|---|---|
| PRIMARY, 69 studies | 0.362 | 0.372 (+2.7 %) | 0.387 (+6.7 %) |
| Studies with intensity, 46 | 0.386 | 0.391 | 0.404 |

Neither predictor beats the median (paired study-bootstrap CIs include 0, point estimates are worse).

**Conclusion**
- The between-study stress gradient found in X1 runs through the **damage actually realised in each experiment**,
  not through the nominal stress dose printed in the Methods.
- Published intensities are comparable within a study but not across studies.
- An a-priori predictor would need a measured, comparable exposure: root-zone ECe or soil water potential measured
  during the stress, or relative transpiration. Alternatively, it would need a prior estimate of the yield loss
  itself (the grower's own S vs C history). Very few studies report these.
