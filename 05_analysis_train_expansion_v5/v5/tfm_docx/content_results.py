# -*- coding: utf-8 -*-
"""Results (section 4) of the TFM, written for biologists. Each subsection: purpose (1-2 sentences) -> results -> significance.
Figures from TFM_TRAIN_EXPANSION/v5/figures (V5 recomputation of the V4 figure set + additional checks)."""
FIG = "TFM_TRAIN_EXPANSION/v5/figures"
R = "TFM_TRAIN_EXPANSION/v5"

RESULTS = [
    ('h1', '4. Results'),
    ('p', 'Unless stated otherwise, effects are given as the percentage change in fruit yield or dry biomass of biostimulant-treated plants relative to '
          'untreated plants of the same experiment, 100·[exp(lnRR) − 1], with 95 % confidence intervals (CI). "TRAIN" refers to studies published up to 2023 '
          'and "TEST" to the independent studies published in 2024–2026. Model accuracy is expressed as the root-mean-square error (RMSE) on the lnRR scale: '
          'an RMSE of 0.44 means that a typical prediction misses the observed effect by roughly ±45–55 % of yield. Figures and tables can be regenerated with '
          f'the scripts listed in {{T:scripts}}; all numbers are taken from `{R}/results`.'),

    # 4.1
    ('h2', '4.1. Study selection and final data sets'),
    ('p', 'Before any effect can be estimated, it must be clear how many independent experiments enter the analysis and why others were excluded. The flow '
          'diagram summarises the path from the literature search to the final analysis tables for both the development (TRAIN) and the test (TEST) data.'),
    ('fig', f'{FIG}/Fig16_PRISMA_flow.png', 'prisma', 'Flow of records, studies and contrasts (PRISMA-style).',
     'Grey boxes: upstream screening counts from the historical PRISMA record. Coloured boxes: V5 TRAIN and TEST tables built with identical definitions '
     'and selection rules.'),
    ('p', 'Of 39 627 records identified, 12 141 were unique and 766 full texts were screened; 399 studies met the class A criterion (tomato, experimental '
          'stress and biostimulant) ({F:prisma}). After extraction, verification and the selection rules, the TRAIN tables contained 831 fruit-yield contrasts '
          'from 76 independent studies (75 dependency clusters) and 1 452 dry-biomass contrasts from 172 studies (171 clusters); the TEST tables contained 117 '
          'yield contrasts from 16 studies and 378 biomass contrasts from 31 studies ({T:datasets}). No study, dependency cluster, DOI or title was shared '
          'between TRAIN and TEST. About two thirds of the yield contrasts (568) compared stressed plants with and without biostimulant (SB vs S) and one third '
          '(263) compared unstressed plants (B vs C). Authors reported a usable SD or SE for 32 % of the yield contrasts and 46 % of the biomass contrasts; for '
          'the remainder the variance was imputed from the mean coefficient of variation (Section 3.9.1).'),
    ('tab', 'datasets', 'Final analysis data sets (V5).',
     ['Data set', 'Contrasts', 'Studies', 'Clusters', 'SB vs S / B vs C', 'Variance from authors'],
     [['TRAIN — fruit yield', '831', '76', '75', '568 / 263', '264 (32 %)'],
      ['TRAIN — dry biomass', '1 452', '172', '171', '961 / 491', '661 (46 %)'],
      ['TEST — fruit yield', '117', '16', '16', '—', '—'],
      ['TEST — dry biomass', '378', '31', '31', '—', '—']],
     [4.2, 2.0, 1.8, 1.8, 2.8, 2.4]),
    ('p', 'Before modelling, the analysis tables were audited against the stored page images of the original articles ({F:audit}). Compared with the previous '
          'version (V3.1), the yield TRAIN set doubled (from 403 to 831 contrasts) because all yield definitions were kept and labelled instead of filtered, '
          'and the TEST set grew from 12 to 16 studies. The audit corrected fruit-size fractions stored as total yield (2 studies), harvest years that had to be '
          'attached to each measurement (3 studies), stress classes (11 yield studies, including biotic and combined stresses) and the coding of unknown hybrid status '
          '(42 studies).'),
    ('fig', f'{FIG}/Fig1_data_V31_to_V5.png', 'audit', 'Training and test data before (V3.1) and after (V5) the source-verified audit.',
     f'(a) Data volume; (b) corrections by type (register: `{R}/data/corrections_register.csv`); (c) independent studies per stress class; (d) share of '
     'yield studies reporting each descriptor (unknown values are kept as missing).'),
    ('p', '**Significance.** The analysis rests on a traceable set of 76 independent yield studies and 172 biomass studies, with a separate, non-overlapping '
          'test set. The audit shows that even a carefully built database contains coding errors that can only be detected by going back to the original '
          'pages; correcting them before modelling prevents artefacts such as counting fruit-size fractions as independent yield results. Panel (d) also shows '
          'which agronomic descriptors are rarely reported (plant density, printed coordinates), which limits what any model can learn from them.'),

    # 4.2
    ('h2', '4.2. Characteristics of the evidence base'),
    ('p', 'The usefulness of a synthesis depends on how well the evidence covers the conditions in which biostimulants are used. This section describes the '
          'database and the distribution of studies by year, cultivation system and country.'),
    ('fig', f'{FIG}/Fig21_database.png', 'database', 'Relational databases behind the analysis.',
     '(a) Tables and rows of the TRAIN_DEV and EXTERNAL_TEST databases; (b) studies per endpoint; (c) endpoint × contrast type; (d) risk-of-bias judgements '
     'by domain (TRAIN).'),
    ('p', 'The TRAIN_DEV database holds 399 studies, 455 experiments, 3 836 treatment arms, 8 012 verified measurements and 8 322 candidate contrasts, each '
          'linked to its source page; the TEST database holds 80 studies and 2 001 candidate contrasts ({F:database}a). Dry biomass is the most frequently '
          'reported endpoint (more than 200 studies), followed by fruit yield (85 studies), fruit number and mean fruit mass ({F:database}b). The risk-of-bias '
          'assessment rarely found a high risk (≤ 15 % of experiments in any domain), but many experiments could not be judged because key information was '
          'not reported: missing data were unclear in 79 % of experiments, baseline comparability in 63 % and randomisation/allocation in 54 % ({F:database}d). Yield studies were '
          'published between 2001 and 2023, with most after 2018; greenhouse experiments dominate (44 of 76 yield studies), followed by field trials (22), and '
          'Italy, Egypt, India and Spain contribute most studies ({F:landscape}d–f).'),
    ('p', '**Significance.** The evidence is recent, greenhouse-dominated and geographically concentrated. Conclusions are therefore most reliable for '
          'protected Mediterranean-type production and should be transferred with care to open-field systems or regions with few studies. The frequent '
          'reporting gaps in randomisation and replication are relevant for researchers designing new trials.'),

    # 4.3
    ('h2', '4.3. Which biostimulants have been tested under which stresses?'),
    ('p', 'Growers and companies need to know which combinations of biostimulant type and stress are supported by evidence and which are evidence gaps. '
          'The evidence matrix crosses the du Jardin class of the biostimulant with the type of stress and shows, for each cell, the number of independent '
          'studies, the average yield effect and — distinguishing description from prediction — the range expected for a new study.'),
    ('fig', f'{FIG}/Fig15_evidence_landscape.png', 'landscape', 'Evidence landscape for fruit yield (TRAIN).',
     '(a) Independent studies per stress class × biostimulant class; (b) yield effect: bold = pooled mean with 95 % CI (≥ 3 studies), italics = median of '
     'study means (< 3 studies, no interval); (c) cells with ≥ 3 studies: mean and CI (blue), 95 % prediction interval for a new study (grey) and mean '
     'out-of-fold prediction of the selected model (×); (d) publication years; (e) cultivation system; (f) countries. Full table: '
     f'`{R}/results/class_x_stress_matrix_yield_V5.xlsx`.'),
    ('p', 'Most evidence concerns three groups — beneficial fungi (mycorrhizae, *Trichoderma*), beneficial bacteria (PGPR) and seaweed/botanical extracts — '
          'tested without stress, under salinity or under drought ({F:landscape}a). Only 21 cells have three or more studies; heat, cold, biotic, nutrient and '
          'combined stresses are represented by single studies in most classes. In all well-supported cells the average yield effect is positive ({T:matrix}), '
          'for example +59 % [+20, +109] for fungi under salinity (9 studies), +91 % [+18, +211] for bacteria under salinity (6 studies) and +96 % [+4, +272] '
          'for seaweed/botanicals under drought (6 studies). The prediction intervals, however, are very wide and almost always include losses (for example −33 '
          'to +274 % for fungi under salinity), and the model predictions (crosses in {F:landscape}c) are closer to the overall mean than the cell means.'),
    ('tab', 'matrix', 'Yield effect of biostimulant classes by stress type (cells with ≥ 5 independent TRAIN studies).',
     ['Stress × biostimulant class', 'Studies', 'Mean effect, % [95 % CI]', '95 % PI for a new study, %', 'Model prediction, %'],
     [['No stress × fungi (AMF, Trichoderma)', '15', '+16 [−10, +50]', '−66 to +298', '+21'],
      ['No stress × seaweed / botanical', '13', '+35 [+16, +57]', '−22 to +133', '+43'],
      ['No stress × bacteria (PGPR)', '11', '+36 [+15, +60]', '−24 to +142', '+34'],
      ['Salinity × fungi', '9', '+59 [+20, +109]', '−33 to +274', '+20'],
      ['Drought × fungi', '7', '+35 [+1, +79]', '−63 to +390', '+38'],
      ['No stress × inorganic (Si, Se, nano)', '7', '+28 [−5, +73]', '−44 to +195', '+53'],
      ['Drought × seaweed / botanical', '6', '+96 [+4, +272]', '−65 to +1010', '+74'],
      ['Drought × bacteria', '6', '+49 [−6, +137]', '−53 to +377', '+54'],
      ['Salinity × bacteria', '6', '+91 [+18, +211]', '−61 to +845', '+74'],
      ['No stress × other (non-du Jardin)', '5', '+73 [−10, +231]', '−63 to +706', '+31'],
      ['Drought × inorganic', '5', '+80 [+11, +190]', '−53 to +591', '+67']],
     [5.0, 1.5, 3.2, 3.2, 2.1]),
    ('p', '**Significance.** The matrix is a practical map of where evidence exists and where it is missing. It distinguishes three quantities that are '
          'often confused: the average past effect (descriptive), the plausible range in a new trial (prediction interval), and a model forecast. A positive '
          'average with a wide prediction interval means "this type of product usually helps, but a single new trial may well show no benefit". The empty '
          'cells (heat, cold, biotic and combined stresses for most classes) point to priorities for new experiments.'),

    # 4.4
    ('h2', '4.4. Overall effects and heterogeneity'),
    ('p', 'The central question of the synthesis is whether biostimulants increase yield and biomass on average, how large this effect is, and how much it '
          'varies between studies. A three-level meta-analysis accounts for several contrasts coming from the same study and for treatments sharing a control.'),
    ('fig', f'{FIG}/Fig14_meta_summary.png', 'meta', 'Meta-analytic summary.',
     '(a) Pooled effects for different data subsets, TEST and TRAIN+TEST (thick line: 95 % CI; thin line: 95 % prediction interval); (b) partition of the '
     'variance; (c) heterogeneity explained by moderators; (d) probability that a new study shows a gain above a threshold.'),
    ('p', 'Biostimulants increased fruit yield by **+45 % [+33, +59]** (76 studies, 831 contrasts) and dry biomass by **+35 % [+30, +40]** (172 studies) '
          '({F:meta}a, {T:pooled}). The effect was positive in all subsets: studies with a strict yield definition (+41 %), only stressed plants (+57 %) and '
          'only contrasts with author-reported variances (+51 %). The independent TEST studies gave very similar estimates (yield +40 % [+13, +74]; biomass '
          '+31 % [+18, +44]); the difference between TEST and TRAIN was small and not significant (yield −4 %, p = 0.72; biomass −3 %, p = 0.56). In the '
          'forest plots ({F:forest_y}, {F:forest_b}), 95 % of yield studies and 92 % of biomass studies showed a positive effect, and only 2.6 % and 1.7 % '
          'showed a significant negative effect.'),
    ('tab', 'pooled', 'Pooled effects of biostimulants (three-level REML, CR2 robust 95 % CI; PI = 95 % prediction interval).',
     ['Endpoint / data set', 'Studies', 'Contrasts', 'Effect, % [95 % CI]', '95 % PI, %'],
     [['Yield — TRAIN (primary)', '76', '831', '+45 [+33, +59]', '−40 to +250'],
      ['Yield — TRAIN, strict definition', '16', '159', '+41 [+19, +68]', '−31 to +188'],
      ['Yield — TRAIN, author-reported SD only', '29', '264', '+51 [+26, +81]', '−54 to +395'],
      ['Yield — TEST 2024–2026', '16', '117', '+40 [+13, +74]', '−46 to +264'],
      ['Dry biomass — TRAIN (primary)', '172', '1 452', '+35 [+30, +40]', '−27 to +148'],
      ['Dry biomass — TEST 2024–2026', '31', '378', '+31 [+18, +44]', '−42 to +196']],
     [5.2, 1.6, 1.8, 3.2, 3.2]),
    ('p', 'The effect varied strongly between studies. Between-study differences accounted for about half of the variance of yield effects (52 %) and a third '
          'of that of biomass effects (34 %), within-study differences for 30 % and 46 %, and sampling error for only about 20 % ({F:meta}b). As a consequence, '
          'the 95 % prediction interval for a new study ranges from −40 % to +250 % for yield. Translated into probabilities ({F:meta}d), a new study has an '
          '80 % chance of showing any yield gain, 63 % of a gain above 25 % and 47 % of a gain above 50 %.'),
    ('fig', f'{FIG}/Fig9_forest_yield.png', 'forest_y', 'Fruit yield: study effects and subgroups (TRAIN).',
     '(a) Study aggregates with 95 % CI (square size = weight in the model); (b) subgroup means with robust CI and Wald p-values.'),
    ('fig', f'{FIG}/Fig10_forest_biomass.png', 'forest_b', 'Dry biomass: study effects and subgroups (TRAIN).', 'Panels as in the previous figure.'),
    ('p', '**Significance.** The average benefit of biostimulants on tomato yield under stress is large, consistent across data subsets and confirmed by '
          'independent studies published after 2023. For a grower, however, the average is less informative than the variability: the same type of product '
          'can give anything from a loss to a doubling of yield in a particular trial. This motivates the search for moderators (Section 4.5) and the honest '
          'reporting of prediction intervals.'),

    # 4.5
    ('h2', '4.5. Moderators of efficacy and meta-regression'),
    ('p', 'Moderator analysis asks whether the effect depends on the type of stress, the class of biostimulant, the application route or the cultivation '
          'system — information that would help to choose the right product for a given situation.'),
    ('p', 'For fruit yield, none of the subgroups differed significantly: stress class p = 0.15, biostimulant class p = 0.84, route p = 0.88 and system '
          'p = 0.08 ({F:forest_y}b). Stressed experiments tended to show larger gains (salinity +52 %, drought +52 %, heat +91 % with 5 studies) than unstressed '
          'ones (+32 %), and greenhouse experiments larger gains (+63 %) than field trials (+20 %). Each moderator explained at most 5 % of the between-study '
          'variance ({F:meta}c). For dry biomass, the biostimulant class (p = 0.003) and the cultivation system (p = 0.005) were significant: bacteria '
          '(+43 %) and fungi (+34 %) increased biomass more than seaweed/botanical extracts (+17 %) and protein hydrolysates (+20 %), and soilless systems '
          'showed the smallest gains (+16 %) ({F:forest_b}b).'),
    ('fig', f'{FIG}/Fig20_moderators.png', 'moderators', 'Moderators of the yield effect.',
     '(a) Permutation importance of the design descriptors in the Ridge model (outer CV); (b) single-moderator meta-regressions with robust CI and '
     'Holm-adjusted p-values.'),
    ('p', 'In single-moderator meta-regressions ({F:moderators}b), unstressed contrasts showed a smaller yield effect than stressed ones (−0.12 lnRR, p = 0.02), '
          'and higher stress intensity tended to increase the benefit (+0.09 lnRR per SD, p = 0.08), but neither remained significant after correction for '
          'multiple testing (Holm p = 0.19 and 0.71). For biomass, foliar application (−0.12, Holm p = 0.005) and the absence of stress (−0.13, Holm p = 0.02) '
          'were associated with smaller gains. The permutation importance of all descriptors in the predictive model was small (< 0.01 RMSE) ({F:moderators}a).'),
    ('p', '**Significance.** The reported descriptors of the product and the experiment explain little of the variability in yield response. Biologically, '
          'the clearest pattern is that biostimulants help more when plants are stressed — consistent with their role as stress-mitigating agents — and that, '
          'for biomass, microbial products outperform extracts. These are useful general guidelines, but not sufficient to predict the result of a specific '
          'trial.'),

    # 4.6
    ('h2', '4.6. Stress × biostimulant interaction and the stress-damage gradient'),
    ('p', 'If biostimulants mitigate stress, their benefit should be larger in stressed than in unstressed plants and larger when the stress caused more '
          'damage. Two complementary analyses test this: the S×B interaction in full factorial experiments (C, S, B, SB) and the relationship between the '
          'biostimulant effect and the stress damage of the same study.'),
    ('fig', f'{FIG}/Fig4_stress_gradient.png', 'gradient', 'Stress-damage gradient.',
     '(a) Yield effect of the biostimulant ln(SB/S) against the stress damage D = ln(S/C), study means, TRAIN and TEST; (b) share of the stress loss '
     'recovered by the biostimulant; (c) salinity: damage expected from the Maas–Hoffman model versus observed damage; (d) the same as (a) for dry biomass.'),
    ('p', 'The stronger the stress reduced the yield of the untreated plants, the larger the relative gain from the biostimulant: the between-study slope was '
          '−0.50 [−0.65, −0.28] for yield (53 studies, R² = 0.44) and −0.38 [−0.57, −0.23] for biomass (142 studies), and the TEST studies showed the same '
          'direction ({F:gradient}a, d). Only part of this slope (≈ −0.12) is expected as a statistical artefact of the shared stressed arm. Biostimulants '
          'recovered on average about two thirds of the yield lost to stress (median 0.67, interquartile range 0.35–1.04; {F:gradient}b). For salinity, the '
          'damage predicted from the salt concentration with the classical Maas–Hoffman model did not agree with the damage observed in the experiments '
          '(Spearman ρ = −0.04, p = 0.85; {F:gradient}c). In factorial experiments, the S×B interaction was positive: the biostimulant gave +25 % [+9, +42] '
          'more yield benefit under stress than without stress (47 studies) and +14 % [+7, +22] more biomass benefit (115 studies) ({F:interactions}a).'),
    ('p', '**Significance.** These results support the biological hypothesis that biostimulants act mainly as stress mitigators: they recover a substantial '
          'part of the loss, and the more severe the stress, the more there is to recover. The poor agreement between nominal salt levels and observed damage '
          'shows that the actual stress experienced by the plants depends on the experimental system, so the observed damage (S vs C) is more informative than '
          'the nominal stress level. Because this damage is known only after the experiment, it can improve prediction only conditionally (category B models, '
          'Section 4.8).'),

    # 4.7
    ('h2', '4.7. Combinations of two biostimulants (A × B)'),
    ('p', 'Combining two biostimulants is common in practice in the hope of a synergistic effect. The A×B interaction compares the observed effect of the '
          'combination with the effect expected if the two products acted additively.'),
    ('fig', f'{FIG}/Fig19_interactions.png', 'interactions', 'Interactions.',
     '(a) S×B interaction by study (dots) and mean of study means with 95 % CI (diamonds); (b) A×B contrasts classified by their 95 % CI; (c) A×B '
     'interaction by study.'),
    ('p', 'Only 8 yield studies and 10 biomass studies contained complete C/A/B/AB designs ({F:interactions}b, c). The combinations performed worse than '
          'expected from the single products: the mean A×B interaction was −52 % [−74, −14] for yield and −17 % [−27, −5] for biomass. Among biomass '
          'contrasts with a known variance, 33 were additive, 8 antagonistic and only 1 synergistic; all yield contrasts with a known variance were '
          'antagonistic or additive.'),
    ('p', '**Significance.** In the published tomato experiments, combining two biostimulants rarely produced more than the sum of their effects; in most cases '
          'the second product added less than when applied alone. The evidence is limited to few studies, but it argues against assuming synergy when '
          'designing product mixtures and highlights the need for properly designed factorial trials.'),

    # 4.8
    ('h2', '4.8. Predictive performance of the models'),
    ('p', 'The predictive part of the work asks whether the effect of a biostimulant in a *new* study can be predicted from the description of the product and '
          'the experiment better than by simply using the average effect. Fourteen models were compared in a nested cross-validation in which each '
          'validation fold contained studies never seen during training.'),
    ('fig', f'{FIG}/Fig2_model_performance.png', 'cv', 'Model selection on TRAIN (nested cross-validation grouped by dependency cluster).',
     '(a) Fruit yield and (b) dry biomass: RMSE (mean ± SD over three seeds) and change relative to the mean baseline; blue = a-priori models (category A), '
     'purple = conditional models using the observed stress damage (category B); (c) R²; (d) partition of the variance of the effects.'),
    ('p', 'For fruit yield, the best a-priori model was Ridge regression on the design descriptors, with an RMSE of 0.438 compared with 0.459 for the mean '
          'baseline (−4.5 %; R² = 0.08) ({F:cv}a, {T:models}). More complex models — Random Forest, numeric recoding of the text descriptors with target '
          'encoding, and stacks — did not improve on Ridge. When the observed stress damage of the study was also available (category B), the combination of '
          'Ridge and the conditional meta-regression reached RMSE 0.424 (−7.5 %; R² = 0.14). For dry biomass, no a-priori model beat the mean: by the '
          'pre-specified rule the mean baseline was selected (RMSE 0.367; the three-level mean was only 0.4 % better), and all ML models were 2–8 % worse. '
          'The best conditional biomass model (three-level mean + MR2) reached 0.353 (−3.8 %). Most of the error stems from differences between studies that '
          'the descriptors do not explain ({F:cv}d).'),
    ('tab', 'models', 'Performance of the selected models and baselines: TRAIN nested CV and TEST (POST_HOC_TEST_REUSE).',
     ['Endpoint', 'Model', 'Category', 'CV RMSE', 'CV R²', 'TEST RMSE [95 % CI]', 'TEST coverage'],
     [['Yield', 'Mean (baseline)', 'A', '0.459', '0.00', '0.512 [0.33, 0.65]', '0.88'],
      ['Yield', 'Three-level mean (MR0)', 'A', '0.458', '0.00', '0.515 [0.33, 0.64]', '0.93'],
      ['Yield', 'Ridge, design descriptors (selected)', 'A', '0.438', '0.08', '0.524 [0.31, 0.64]', '0.90'],
      ['Yield', 'Ridge + MR2 (selected)', 'B', '0.424', '0.14', '0.492 [0.29, 0.59]', '0.93'],
      ['Biomass', 'Mean (baseline, selected)', 'A', '0.367', '−0.02', '0.455 [0.28, 0.57]', '0.90'],
      ['Biomass', 'Three-level mean (MR0)', 'A', '0.366', '−0.01', '0.458 [0.28, 0.57]', '0.89'],
      ['Biomass', 'MR0 + MR2 (selected)', 'B', '0.353', '0.06', '0.431 [0.27, 0.54]', '0.90']],
     [1.8, 4.6, 1.6, 1.6, 1.4, 3.0, 1.8]),
    ('fig', f'{FIG}/Fig3_uncertainty.png', 'uncertainty', 'Uncertainty in cross-validation.',
     '(a, b) Coverage of the 95 % intervals against their half-width; (c) confidence interval of the pooled mean versus prediction interval for a new study.'),
    ('p', 'The 95 % intervals of all models were well calibrated in cross-validation (coverage 0.93–0.96) but wide (half-width 0.8–0.97 lnRR for yield and 0.70–0.83 '
          'for biomass) ({F:uncertainty}a, b). In contrast to the narrow confidence interval of the pooled mean, the prediction interval for a new study spans '
          'most of the observed range ({F:uncertainty}c).'),
    ('p', '**Significance.** Descriptive information on the biostimulant, the stress and the crop allows only a small improvement over simply assuming the '
          'average effect: about 8 % of the variation of yield responses in new studies is predictable a priori, and none for biomass. Knowing how strongly '
          'the stress affected the untreated plants roughly doubles the explained variation, which suggests that measuring and reporting stress damage is '
          'more valuable for prediction than additional product descriptors. The intervals are reliable but wide, which is an honest statement of the current '
          'uncertainty.'),

    # 4.9
    ('h2', '4.9. External temporal test (2024–2026)'),
    ('p', 'A model is useful only if it works on studies that were not available when it was built. The frozen models were therefore evaluated once on the '
          '2024–2026 studies, with criteria fixed in advance. Because this corpus had been used to evaluate earlier versions, the result is labelled '
          'POST_HOC_TEST_REUSE.'),
    ('fig', f'{FIG}/Fig5_TRAIN_vs_TEST.png', 'test_y', 'Fruit yield: frozen models on the 2024–2026 TEST studies (POST_HOC_TEST_REUSE).',
     '(a) TEST contrasts by study with the interval of the selected model (red diamonds: outside the interval); (b) RMSE in CV and on TEST; (c) coverage; '
     '(d) pooled effect in TRAIN and TEST.'),
    ('fig', f'{FIG}/Fig7_biomass_TEST.png', 'test_b', 'Dry biomass: frozen models on the TEST studies.', 'Panels as in the previous figure.'),
    ('p', 'On the TEST yield studies, the selected Ridge model had an RMSE of 0.524, not lower than that of the mean baseline (0.512); the error increased '
          'relative to CV but stayed within the pre-specified transfer limit (≤ 1.25 × CV RMSE), and interval coverage was 0.897, just below the 0.90 '
          'threshold ({F:test_y}, {F:test_crit}). The conditional model performed better (RMSE 0.492, coverage 0.93), but its advantage over the mean was not '
          'significant. For dry biomass, the selected mean baseline gave RMSE 0.455 with coverage 0.899, and the conditional model 0.431 ({F:test_b}). Both '
          'endpoints therefore received the verdict **PARTIAL**: transfer passed, while the point-accuracy and coverage criteria were not met. The pooled '
          'average effect itself was reproduced in TEST (Section 4.4).'),
    ('fig', f'{FIG}/Fig13_V5_TEST_posthoc.png', 'test_crit', 'Summary of the pre-specified TEST criteria.',
     '(a) Criteria H1–H3 and verdict per endpoint; (b) change in RMSE relative to the mean baseline on TEST with 95 % cluster-bootstrap CI (◀ = selected '
     'models; other models shown for transparency only).'),
    ('tab', 'criteria', 'Pre-specified evaluation criteria on TEST (POST_HOC_TEST_REUSE).',
     ['Criterion', 'Yield', 'Dry biomass'],
     [['Selected a-priori model', 'Ridge, design descriptors', 'Mean baseline'],
      ['H1: RMSE below the mean (CI of difference < 0)', 'Not met (0.524 vs 0.512)', 'Not met (selected model is the mean)'],
      ['H2: RMSE_TEST ≤ 1.25 × RMSE_CV', 'Met (0.524 ≤ 0.548)', 'Met (0.455 ≤ 0.459)'],
      ['H3: 95 % interval coverage ≥ 0.90', 'Not met (0.897)', 'Not met (0.899)'],
      ['H4: conditional model better than a-priori model', 'Yes (0.492)', 'Yes (0.431)'],
      ['Verdict', 'PARTIAL', 'PARTIAL']],
     [6.0, 4.5, 4.5]),
    ('p', '**Significance.** The test confirms the main biological message — biostimulants increase yield and biomass on average by a similar magnitude in '
          'recent studies — but shows that the a-priori models do not forecast the result of an individual new study better than the average effect. The '
          'intervals remained close to their nominal coverage, so the uncertainty statements can be trusted. For practical recommendations this means that '
          'the evidence base supports statements about typical effects and their range, not precise product-specific forecasts.'),

    # 4.10
    ('h2', '4.10. Learning curves: is prediction limited by the amount of data?'),
    ('p', 'Weak prediction may result either from the absence of a predictable signal or from too few studies. Learning curves show how the error changes '
          'when the model is trained on increasing numbers of studies.'),
    ('fig', f'{FIG}/Fig17_learning_curves.png', 'learning', 'Grouped learning curves (TRAIN).',
     'Outer-fold RMSE against the number of training studies for the mean, the three-level mean and Ridge.'),
    ('p', 'For fruit yield, the error of the Ridge model decreased steadily from 0.48 with 12 training studies to 0.43 with 61 studies, whereas the mean '
          'baseline hardly changed (0.47 to 0.46); Ridge became better than the mean once more than about 20 studies were available ({F:learning}a). For dry '
          'biomass, Ridge remained worse than the three-level mean at every training size (0.37 vs 0.35; {F:learning}b).'),
    ('p', '**Significance.** For yield, prediction is data-limited: every additional study improves the model, and the curve has not levelled off at 76 '
          'studies. Systematic collection of new, well-described yield experiments is therefore the most effective way to improve predictions. For biomass, '
          'additional studies of the same kind are unlikely to help unless new, more informative descriptors are recorded.'),

    # 4.11
    ('h2', '4.11. Applicability domain'),
    ('p', 'A prediction is more trustworthy for a new experiment that resembles the training studies than for an unusual one. The applicability domain '
          'measures how far each contrast is from the nearest training contrasts.'),
    ('fig', f'{FIG}/Fig18_applicability_domain.png', 'ad', 'Applicability domain.',
     '(a) Distance of CV and TEST contrasts to the training data (1 = threshold); (b) error against distance; (c) error and coverage inside and outside '
     'the domain.'),
    ('p', 'Most TEST yield contrasts (112 of 117) were inside the applicability domain; for them the 95 % intervals covered 93 % of the observed effects. The '
          'five out-of-domain contrasts had a mean absolute error of 0.93 and only 20 % coverage, and in cross-validation out-of-domain contrasts also had '
          'larger errors (0.46 vs 0.29) and lower coverage (0.86 vs 0.96) ({F:ad}c). The relation between distance and error was, however, not monotonic '
          '({F:ad}b), and for biomass no difference was found.'),
    ('p', '**Significance.** The shortfall in TEST coverage is concentrated in a few atypical experiments, which supports flagging out-of-domain cases with a '
          'warning. Because the relation is not monotonic, distance alone is not a reliable filter; whether reliable predictions can be selected in advance is '
          'tested directly in the next section.'),

    # 4.12
    ('h2', '4.12. Can reliable predictions be identified in advance?'),
    ('p', 'In practice it may be acceptable to give a recommendation only for cases where the model is expected to be reliable. This analysis tests whether '
          'abstaining from uncertain cases gives the model a real advantage over the simple average, with the decision rule learnt only from training '
          'studies and the main criterion fixed in advance.'),
    ('fig', f'{FIG}/FigB1_selective_prediction.png', 'selective', 'Selective prediction (TRAIN, nested cross-validation).',
     '(a) Error of Ridge on the retained contrasts and of the mean on the same contrasts; (b) difference Ridge − mean with 95 % cluster-bootstrap CI '
     '(numbers = studies keeping at least one prediction); (c) coverage of the 95 % intervals.'),
    ('p', 'Selecting contrasts by the local error of similar training contrasts reduced the error substantially: with 50 % of contrasts predicted, the Ridge '
          'RMSE fell from 0.438 to 0.347, whereas random abstention left it unchanged ({F:selective}a). However, the mean baseline improved just as much on the '
          'same contrasts (to 0.378), so the advantage of Ridge over the mean remained about −0.02 to −0.03 at every share ({F:selective}b). For the '
          'pre-specified criterion (80 % of contrasts, 70 of 76 studies) the difference was −0.021 [−0.049, +0.009] and the advantage was **not confirmed**. '
          'Interval coverage rose slightly (0.95 → 0.96) at constant width ({F:selective}c). For biomass, Ridge was worse than the mean at every share.'),
    ('p', '**Significance.** It is possible to say in advance which experiments will be easier to predict, but they are easier for any method, including the '
          'simple average. Abstention therefore increases confidence in the retained recommendations but does not create cases in which the descriptor-based '
          'model has a demonstrable advantage.'),

    # 4.13
    ('h2', '4.13. Robustness: influential studies, small-study effects and data-preparation decisions'),
    ('p', 'A conclusion is only useful if it does not depend on a single study, on selective publication or on arbitrary decisions taken while preparing the '
          'data. Three complementary analyses test this.'),
    ('fig', f'{FIG}/Fig8_influence.png', 'influence', 'Leave-one-study-out influence on the pooled TRAIN effect.',
     '(a) Yield and (b) dry biomass: pooled effect after removing each study in turn; (c) maximum shift.'),
    ('p', 'Removing any single study changed the pooled yield effect only between +42 % and +48 % (maximum shift 0.024 lnRR) and the biomass effect between '
          '+34 % and +35 % ({F:influence}).'),
    ('fig', f'{FIG}/Fig11_publication_bias.png', 'pubbias', 'Small-study effects and publication bias.',
     '(a, b) Funnel plots of study aggregates; (c) bias-adjusted estimates; (d) tests.'),
    ('p', 'Funnel plots were moderately asymmetric. Begg\'s rank test was significant for both endpoints (yield p = 0.003; biomass p < 0.001), whereas '
          'Egger\'s regression (p = 0.90 and 0.43) and the multilevel Egger test (p = 0.07 and 0.37) were not, and trim-and-fill imputed no missing studies '
          '({F:pubbias}). The PET estimate, which corrects most strongly for small-study effects, was lower but still clearly positive (yield +27 %, biomass '
          '+29 %).'),
    ('fig', f'{FIG}/FigB3_data_sensitivity.png', 'sensitivity', 'Sensitivity of the conclusions to data-preparation decisions (TRAIN).',
     '(a) Pooled effect; (b) gain of Ridge over the mean; (c) interval coverage; one decision changed at a time, all methods on the same rows.'),
    ('p', 'Across eleven scenarios that changed one data-preparation decision at a time, the pooled effect remained between +43 % and +51 % for yield and '
          'between +32 % and +35 % for biomass ({F:sensitivity}a). Assumptions about the imputed variances and the shared controls changed the yield effect by '
          'at most 2 percentage points, and interval coverage stayed between 0.94 and 0.97 ({F:sensitivity}c). The small predictive gain of Ridge for yield was '
          'not robust: it disappeared when only author-reported variances were used (−0.8 %) and reversed when contrasts with an unspecified yield definition '
          'were excluded (+5.4 %, i.e. worse than the mean) ({F:sensitivity}b). For biomass, Ridge was worse than the mean in every scenario.'),
    ('p', '**Significance.** The average benefit of biostimulants is robust to individual studies, to plausible publication bias and to the decisions taken '
          'when preparing the data; publication bias may inflate its size somewhat, but not its sign. By contrast, the small gain of the predictive model '
          'partly reflects differences in how yield was defined and measured rather than differences between biostimulants, which is an important caution '
          'for anyone building prediction tools from published data.'),

    # 4.14
    ('h2', '4.14. Additional analyses of practical interest'),
    ('h3', '4.14.1. Does the model choose the better biostimulant?'),
    ('p', 'The practical aim of SynerPlant is to help choose between products. In experiments where several treatments were compared with the same control, '
          'we tested whether the model ranks the treatments in the order that was observed, and how much yield would be lost by following its choice.'),
    ('fig', f'{FIG}/FigB2_product_choice.png', 'choice', 'Choice between biostimulants (TRAIN, out-of-fold predictions).',
     '(a) Share of correct pairwise choices (0.5 = random); (b) the same for pairs whose observed difference exceeds measurement noise; (c) yield lost '
     'relative to the best treatment compared with a random choice.'),
    ('p', 'Across 911 pairs of treatments in 49 yield studies, the models chose the better treatment in 56–58 % of pairs, close to the 50 % expected by chance '
          '({F:choice}a). Between products of different du Jardin classes (280 pairs, 15 studies) the share rose to 64–68 %, but a simple rule — choose the '
          'class with the highest average effect in the training studies — achieved the same (66 %). The pattern was similar for pairs whose difference '
          'exceeded measurement noise ({F:choice}b). A random choice lost on average 16.7 % of yield relative to the best treatment; only the Random Forest '
          'model reduced this loss significantly (to 12.8 %), and this model had not been selected in advance ({F:choice}c). For biomass, choices between '
          'all pairs were at chance level.'),
    ('p', '**Significance.** Published evidence supports choosing between product *types* (for example a microbial product versus an extract), but a simple '
          'class-based rule is as good as the machine-learning models, and choices within a class (doses, strains, formulations) are essentially random. '
          'Good prediction accuracy and good product recommendations are different properties; the second needs direct comparative trials.'),
    ('h3', '4.14.2. Does the analytical procedure work when the truth is known?'),
    ('p', 'With real data the true effect is unknown, so the procedure was also tested on simulated meta-analyses with the structure of the database, in '
          'which the true effect, the heterogeneity and the pattern of missing SDs were controlled.'),
    ('fig', f'{FIG}/FigB4_simulation.png', 'simulation', 'Simulation with known truth.',
     '(a) Bias of the pooled effect and (b) coverage of its 95 % CI as the share of studies without SD increases; (c) error of the prediction for new '
     'studies with and without a true moderator.'),
    ('p', 'When studies with larger effects omitted SDs more often, analysing only studies with reported SDs underestimated the true effect by 0.05–0.44 lnRR '
          'and its CI contained the true value in only 3–60 % of simulations ({F:simulation}a, b). The V5 procedure, which imputes missing variances from '
          'the mean CV and keeps all studies, was unbiased in every scenario (bias ≤ 0.01) with CI coverage of 0.92–0.98; ignoring shared controls changed '
          'little, and unweighted study means performed similarly. A true moderator of the effect improved predictions for new studies by only 1–4 % under '
          'realistic heterogeneity ({F:simulation}c).'),
    ('p', '**Significance.** The simulation confirms that imputing missing variances, rather than discarding incompletely reported studies, protects the '
          'pooled estimate against a plausible reporting bias. It also reproduces, under controlled conditions, the main empirical finding: when effects '
          'differ strongly between studies, even a real moderator brings little predictive gain. The weak predictability observed in the real data is '
          'therefore a property of the problem, not a failure of the method.'),
]
