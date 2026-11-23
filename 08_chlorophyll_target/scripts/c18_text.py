"""Text added to the TFM document for the chlorophyll (V8) extension. Writes c18_text.json, read by c18_update_tfm_docx.py.
All numbers come from 08_chlorophyll_target/results (c09, c10, c12, c15, c16) and v8_meta/results/meta."""
import json, pathlib

T = {}
T['abstract_add'] = (
    'As a V8 extension, leaf chlorophyll was analysed as a third, physiological target with the same pipeline (TRAIN: 607 content contrasts from '
    '94 studies and 610 SPAD-index contrasts from 55 studies). Biostimulants increased chlorophyll content by 25% (19–32%) and the index by 20% '
    '(14–26%). Chlorophyll was more predictable than yield and biomass: a Random Forest reduced the cross-validated error for the SPAD index by 25% '
    '(11% when studies of the same research group were kept together), although this gain did not transfer to the later studies, whereas a '
    'pre-declared Random Forest for chlorophyll content met all temporal-test criteria (RMSE −13% versus the mean; 95% CI −23 to −0.6%).')
T['resum_add'] = (
    "Com a extensió (V8), la clorofil·la foliar s'ha analitzat com a tercer objectiu fisiològic amb el mateix procediment (607 contrastos de "
    "contingut de 94 estudis i 610 d'índex SPAD de 55 estudis). Els bioestimulants augmenten el contingut de clorofil·la un 25% (19–32%) i "
    "l'índex un 20% (14–26%). La clorofil·la és més predictible que el rendiment i la biomassa: un Random Forest redueix l'error de validació "
    "creuada de l'índex SPAD un 25% (un 11% agrupant els estudis del mateix grup de recerca), tot i que aquest guany no es transfereix als estudis "
    "posteriors, mentre que un Random Forest predeclarat per al contingut de clorofil·la compleix tots els criteris de la prova temporal "
    "(RMSE −13% respecte de la mitjana).")
T['m37'] = (
    'After the V5 analysis, leaf chlorophyll was added as a third, physiological target. It was analysed separately from yield and biomass, with '
    'the same contrasts (SB vs S and B vs C) and the same rules for deduplication, moderators and exclusions (Section 3.11). Two tables were '
    'defined because the measurements do not share a scale: leaf chlorophyll content determined after extraction (chlorophyll a, b or total, on a '
    'fresh-mass, dry-mass or leaf-area basis; a + b was computed only when both pigments were reported and their ratio was plausible) and '
    'non-destructive chlorophyll indices (SPAD and equivalent meters). Pigment and basis were kept as outcome-definition descriptors. Values were '
    'extracted from the full texts of the TRAIN_DEV studies by two independent agent passes with page receipts and calibrated digitisation of '
    'figures (at least three axis ticks), reconciled by code and adjudicated against the PDF where the passes disagreed. Systematically '
    'inconsistent pigment values, means rounded to fewer than two significant digits, implausible magnitudes and time points outside the stress '
    'period were flagged rather than deleted; for stressed contrasts only time points during the stress were used. Of 169 TRAIN studies with '
    'candidate chlorophyll data, 154 yielded values (2,773 values, 2,147 contrasts); the default analysis tables contained 607 contrasts from 94 '
    'studies (content) and 610 contrasts from 55 studies (index). Chlorophyll is measured after treatment; it is used here only as an outcome, '
    'never as a predictor of yield or biomass (code and data: 08_chlorophyll_target).')
T['m317'] = (
    'The chlorophyll models were selected with the same cross-validation engine, outer folds, seeds and a-priori (REF) descriptors as yield and '
    'biomass (the corrected V6 yield and biomass tables were re-run with this engine for comparability), plus a stricter grouping in which studies '
    'that share authors form one cluster. All configurations were then refitted on the complete TRAIN tables and frozen before any chlorophyll '
    'value of the 2024–2026 corpus was extracted (08_chlorophyll_target/freeze/MODEL_FREEZE_CHL.json, models_chl.joblib and SHA-256 checksums). '
    'The pre-declared models were Random Forest with inverse-variance weights for the chlorophyll index (best under both groupings) and, because no '
    'ML model beat the mean for chlorophyll content, the three-level mean as primary model with Random Forest with equal study weights as '
    'pre-declared ML candidate. The TEST chlorophyll values were extracted afterwards with the same pipeline by agents without access to TRAIN '
    'data or models, missing variances used the TRAIN CV̄, and the frozen models were evaluated once with criteria H1–H3. The TEST corpus had been '
    'used for yield and biomass, but its chlorophyll values had never been extracted before the freeze.')
T['r43'] = (
    'The chlorophyll evidence has a similar structure but is even more concentrated (Annex D, Figure D1). Of the 82 TRAIN studies with stressed '
    '(SB vs S) chlorophyll-content contrasts, 48 concerned salinity and 18 drought, and beneficial bacteria (33 studies), fungi and protein '
    'hydrolysates (14 each) were the most frequent classes. Nine stress × class cells had three or more studies (Table D1). All their point '
    'estimates were positive, from +14% (salinity × inorganic products, 4 studies) to +38% (salinity × other products, 4 studies); the '
    'best-supported cell, bacteria under salinity, gave +37% [+17, +60] (18 studies).')
T['r44'] = (
    'The chlorophyll targets, analysed with the same model and code (Figure 10e, f; Table 14), showed smaller but consistent average gains: leaf '
    'chlorophyll content increased by +25% [+19, +32] (94 studies, 607 contrasts) and the chlorophyll index by +20% [+14, +26] (55 studies, 610 '
    'contrasts); restricting to stressed plants gave +32% [+24, +41] and +25% [+18, +34]. The TEST studies gave +20% [−1, +44] (15 studies) and '
    '+34% [+1, +78] (10 studies), and the TEST − TRAIN differences were not significant (p = 0.62 and 0.40). Heterogeneity was lower than for '
    'yield (τ = 0.30 for content and 0.22 for the index, against 0.44 for yield and 0.31 for biomass); between-study differences accounted for 46% '
    'and 58% of the variance, and sampling error was negligible (Figure 10f). The 95% prediction interval for a new study was −30% to +126% for '
    'content and −23% to +87% for the index.')
T['r44b'] = (
    'For the chlorophyll targets, study aggregates and subgroup means are shown in Annex D (Figure D2). Under stress (SB vs S), beneficial '
    'bacteria (+41% [+24, +60], 33 studies), fungi (+31% [+12, +53], 14) and protein hydrolysates (+29% [+14, +46], 14) increased chlorophyll '
    'content, whereas seaweed/botanical extracts did not (+5% [−16, +31], 8). Among stresses, salinity (+32% [+22, +42], 48 studies) and drought '
    '(+23% [+11, +37], 18) were well supported, and heat gave the largest but least precise gain (+105% [+7, +292], 5 studies).')
T['r48'] = (
    'With the same engine, folds and descriptors (Figure 16e, f), the chlorophyll index was the only target for which an a-priori model clearly '
    'beat the mean: Random Forest with inverse-variance weights reached a CV RMSE of 0.204 against 0.272 for the mean (−25% [−35, −3]; '
    'R² = 0.41), and every ML configuration had a lower point error than the mean. When studies of the same research group were kept in the same '
    'fold, the gain shrank to −11% [−15, −4], so part of it came from closely related publications of the same groups. For chlorophyll content, '
    'no ML model beat the mean (Random Forest with equal study weights +2.6% [−5, +12]; three-level mean ±0%), so by the pre-specified rule the '
    'three-level mean was declared primary. With the same engine, the best a-priori models for yield and biomass were 5.1% and 0.8% better than '
    'the mean, close to the V5 values above.')
T['r48u'] = (
    'For the chlorophyll targets (Figure 17d, e), CV coverage of the 95% intervals ranged from 0.93 to 0.95 for chlorophyll content and from 0.92 '
    'to 0.96 for the index, with half-widths of 0.63–0.71 and 0.46–0.60 lnRR, narrower than for yield (0.77–0.97) because the effects are less '
    'heterogeneous. The Random Forest for the index combined one of the narrowest intervals (0.48) with a coverage of 0.96, whereas the three-level '
    'mean was the narrowest but under-covered (0.46; 0.92). The prediction intervals for a new study (Figure 17f) were −0.36 to 0.81 lnRR for '
    'content and −0.26 to 0.63 for the index.')
T['r49'] = (
    'The chlorophyll models, frozen before any chlorophyll value of the TEST corpus had been extracted, were evaluated on 63 content contrasts '
    '(15 studies) and 108 index contrasts (10 studies) (Figure 20c, d; Annex D, Figure D3). For the chlorophyll index, the cross-validated '
    'advantage did not transfer: the primary Random Forest had a TEST RMSE of 0.387 against 0.348 for the mean (+11% [+7, +31]), almost twice its '
    'CV RMSE (0.204), and only the coverage criterion was met (0.926), giving PARTIAL. For chlorophyll content, the primary three-level mean was '
    'equivalent to the mean (0.359 vs 0.357; PARTIAL), whereas the pre-declared Random Forest with equal study weights reduced the error to 0.310 '
    '(−13% [−23, −0.6]), with TEST RMSE below its CV value (0.319) and coverage of 0.95. It was the only pre-declared model of the four targets to '
    'meet all three criteria (CONFIRMED). The other four ML configurations for content were also better than the mean on TEST (−5% to −12%), '
    'whereas all ML configurations for the index were worse (+4% to +11%).')
T['r49b'] = (
    'In Figure 20d, the 95% intervals of the content Random Forest (−13.2% [−22.9, −0.6]), Ridge without weights (−5.2% [−8.2, −2.1]), Ridge '
    'with equal study weights (−11.7% [−18.0, −6.1]) and Random Forest with inverse-variance weights (−9.3% [−17.2, −2.4]) lay entirely below '
    'zero, and that of the selected index model entirely above it (+11.1% [+6.9, +31.0]). In a post-hoc permutation analysis on TEST, the content '
    'model relied mainly on the contrast type (B vs C or SB vs S), the biostimulant class, the dose, the stress intensity and the presence of live '
    'microorganisms, and its predictions were correlated with the observed effects (r = 0.66). For the index model, permuting any descriptor '
    'changed the TEST RMSE by less than 0.001 and its predictions were negatively correlated with the observed effects (r = −0.33): its TEST '
    'predictions did not follow the descriptors of the new studies.')
T['r49sig'] = (
    'The chlorophyll results show two faces of predictability. A large cross-validated gain (index) can disappear in later studies when it '
    'partly reflects repeated work of the same groups, whereas a model without internal advantage (content) transferred because it captured a '
    'general pattern — a larger chlorophyll benefit in stressed than in unstressed plants — that was especially clear in the new studies. With 15 '
    'TEST studies and an upper confidence limit of −0.6%, this confirmation is preliminary.')
T['r411'] = (
    'For the chlorophyll targets (Figure 22d–f), the TEST contrasts were as close to TRAIN as the CV contrasts (median distance 0.56 vs 0.59 of '
    'the threshold for content, 0.47 vs 0.47 for the index); 6 of 63 TEST content contrasts and none of the 108 TEST index contrasts lay outside '
    'the domain. In CV, out-of-domain contrasts had larger errors (content MAE 0.34 vs 0.23; index 0.20 vs 0.16) and slightly lower coverage '
    '(0.90 vs 0.94; 0.93 vs 0.96), and the error of the index model increased steadily with distance (Figure 22e). The failure of the index model '
    'on TEST was therefore not caused by unusual experiments: all TEST index contrasts were inside the domain, yet the error was higher than in CV '
    '(MAE 0.23 vs 0.16).')
T['r413'] = (
    'For the chlorophyll targets (Annex D, Figures D4 and D5), removing one study at a time left the pooled content effect between +24% and +26% '
    'and the index effect between +19% and +21%. As for yield and biomass, Begg\'s rank test indicated asymmetry (p = 0.017 for content and 0.003 '
    'for the index), whereas the conventional and multilevel Egger tests were not significant (p ≥ 0.26) and trim-and-fill added no studies; '
    'PET-adjusted estimates remained positive (+23% and +19%).')
T['r415a'] = (
    'The chlorophyll extension (V8) asks a practical question: by how much does a biostimulant change leaf chlorophyll under a given stress, and '
    'can this be predicted for a new study? Under stress (SB vs S), biostimulants increased leaf chlorophyll content by +32% [+24, +41] (82 '
    'studies), more than without stress (B vs C; mean lnRR 0.16 against 0.23 in TRAIN). By stress, the gain was +32% [+22, +42] under salinity '
    '(48 studies), +23% [+11, +37] under drought (18) and +105% [+7, +292] under heat (5), whereas cold (+36%, 4 studies), combined stress (+6%, '
    '3) and heavy metals (+3%, 5) were not significant. By class, bacteria (+41%), fungi (+31%) and protein hydrolysates (+29%) were clearly '
    'positive and seaweed/botanical extracts were not (+5% [−16, +31]). The best-supported combinations were bacteria under salinity (+37% '
    '[+17, +60], 18 studies), fungi under salinity (+34% [+14, +57], 7), protein hydrolysates under salinity (+24% [+10, +40], 10) and bacteria '
    'under drought (+27% [+5, +52], 9) (Table D1). Prediction intervals were narrower than for yield but still included losses (for example '
    '−35% to +186% for bacteria under salinity).')
T['r415b'] = (
    'Across the four targets analysed with the same engine, chlorophyll differed from yield and biomass in three respects (Figures 10, 16 and 20): '
    'its effects were less heterogeneous (τ 0.22–0.30 against 0.31–0.44), the chlorophyll index was the only target with a substantial '
    'cross-validated gain over the mean (−25%, or −11% with research-group folds, against −5% for yield and −1% for biomass), and chlorophyll '
    'content was the only target for which a pre-declared model met all TEST criteria (−13%). For the TEST studies, the frozen content model '
    'predicted on average +33% for stressed plants with a biostimulant (SB vs S) and +23% without stress (B vs C), against observed +49% and −1%: '
    'it reproduced the direction of the stress dependence but underestimated its size.')
T['r415sig'] = (
    'The chlorophyll evidence supports a more specific statement than the yield evidence: in salinity and drought experiments, microbial '
    'products and protein hydrolysates typically raise leaf chlorophyll content by about a quarter to two fifths, and the gain is larger in '
    'stressed than in unstressed plants. The forecast for an individual new study remains uncertain, and leaf chlorophyll is an indicator of the '
    'physiological status of the plant, not a substitute for yield.')
T['d59_1'] = (
    'Leaf chlorophyll was added to test whether the weak predictability of yield and biomass is a property of the evidence base or of the '
    'endpoints. With the same database, extraction pipeline, descriptors, models and validation, the chlorophyll targets behaved differently: '
    'their effects were less heterogeneous, the SPAD index showed a clear cross-validated gain over the mean, and chlorophyll content gave the '
    'only fully confirmed temporal test. Several partly complementary explanations are plausible.')
T['d59_2'] = (
    'First, chlorophyll is closer to the action of the treatment. Biostimulants act largely through nutrient uptake and nitrogen assimilation, '
    'protection of the photosynthetic apparatus against oxidative damage and hormonal regulation of leaf senescence; leaf chlorophyll responds to '
    'these processes within days, on the same leaves that are sampled. Fruit yield integrates the whole crop cycle — flowering, fruit set, '
    'assimilate allocation, harvest management and season length — and each step adds variation that the descriptors of an article cannot '
    'capture; terminal biomass lies in between. The heterogeneity follows this chain (τ = 0.44 for yield, 0.31 for biomass, 0.30 for chlorophyll '
    'content and 0.22 for the index), and a smaller between-study variance leaves a larger share of the variation for the descriptors to explain.')
T['d59_3'] = (
    'Second, chlorophyll loss is a typical and quantitatively consistent symptom of salinity, drought and heat stress (reduced synthesis, '
    'chlorophyll degradation and photo-oxidative damage), and preventing it is a primary effect claimed for microbial and protein-based '
    'biostimulants. The response therefore depends on information that the database records reliably: whether the plants were stressed, the '
    'type and intensity of the stress and the biostimulant class. The TEST evaluation illustrates this. The content model relied mainly on the '
    'contrast type, the biostimulant class, the dose, the stress intensity and the presence of live microorganisms, and in the TEST studies '
    'chlorophyll content did not change without stress (B vs C, −1%) but increased by about half under stress (SB vs S, +49%). For yield, the '
    'corresponding stress dependence also exists (Section 4.6) but is masked by much larger variation between studies.')
T['d59_4'] = (
    'Third, the measurements are more standardised. SPAD and similar meters give an instrument-defined, unitless reading, are non-destructive '
    'and are repeated on the same plants, so measurement error and definitional ambiguity are small compared with yield, whose definition (total '
    'or marketable, per plant or per area, harvest window) varies between studies and is often incompletely reported (Section 3.7). For extracted '
    'chlorophyll, the remaining definitional differences — pigment (a, b or total) and basis (fresh mass, dry mass or leaf area) — are recorded as '
    'descriptors and can be learnt by a model.')
T['d59_5'] = (
    'These advantages do not make the SPAD gain a general, transferable signal. Part of it came from the structure of the corpus: when the '
    'studies of each research group were kept together, the cross-validated gain fell from 25% to 11%, and on TEST the index model was worse than '
    'the mean (+11%), although every TEST contrast lay inside the applicability domain and no descriptor influenced its TEST predictions. The most '
    'likely interpretation is that the Random Forest partly recognised groups of similar studies (same laboratory, cultivar, meter and protocol) '
    'through descriptors such as photoperiod or growing system, and that the ten TEST studies, with a larger and more variable average effect '
    '(+34% [+1, +78]), did not share these patterns. A large internal gain of a flexible model on a corpus with repeated work by the same groups '
    'should therefore be checked with grouping by research group, a methodological lesson that applies equally to yield and biomass.')
T['d59_6'] = (
    'The confirmed result for chlorophyll content must also be weighed carefully. The model was declared before the test, but it had not been '
    'better than the mean in cross-validation (+2.6%), the TEST set comprised only 15 studies, and the upper confidence limit of the gain (−0.6%) '
    'was close to zero. Its success is consistent with the explanation above — the TEST studies showed an especially clear contrast between '
    'stressed and unstressed comparisons, which the descriptors capture — but a single small test cannot establish a stable advantage, and the '
    'model underestimated the size of the stress dependence. As for the other targets, prospective data are needed.')
T['d59_7'] = (
    'Biologically and practically, these results suggest that physiological endpoints close to the mode of action of biostimulants are where '
    'descriptor-based prediction can succeed first, and that such endpoints are useful for screening products and conditions. They are not '
    'substitutes for yield: chlorophyll is measured after treatment and cannot serve as a pre-experimental predictor, and higher chlorophyll does '
    'not necessarily translate into more fruit (Section 5.2). Trials that report chlorophyll during the stress together with the realised stress '
    'damage and yield at harvest would allow the link between early physiological and final productive responses to be quantified.')
T['c8'] = (
    '8. Leaf chlorophyll, analysed as a third target with the same pipeline, increased by 25% (content) and 20% (SPAD index) and was more '
    'predictable than yield and biomass. The SPAD index showed the largest cross-validated gain over the mean (−25%; −11% with research-group '
    'grouping), but this gain did not transfer to the later studies, whereas the pre-declared Random Forest for chlorophyll content met all '
    'temporal-test criteria (RMSE −13%). Endpoints that are close to the mode of action of biostimulants, measured in a standardised way and '
    'strongly stress-dependent are the most promising targets for prediction; they complement, but do not replace, yield.')
T['annexD_intro'] = (
    'This annex contains the chlorophyll-specific figures and the class × stress table of the V8 extension (Sections 3.7, 3.17 and 4.3–4.15). '
    'Data, code and the full tables are in the repository folder 08_chlorophyll_target (figures_TFM_V8, tables_TFM_V8).')
T['capD1'] = ('Evidence landscape for the chlorophyll targets (TRAIN), laid out as Figure 9. (a, b) Independent studies per stress class × '
              'biostimulant class for chlorophyll content and index; (c, d) effect of the biostimulant (SB vs S and B vs C): bold = pooled mean of a '
              'three-level REML model (≥ 3 studies), italics = median of study means (< 3 studies, no inference).')
T['capD2'] = ('Chlorophyll targets: study effects and subgroups (TRAIN), as Figures 11 and 12. (a, b) Study aggregates with 95% CI (square size = '
              'weight in the model; band = 95% CI of the pooled mean); (c, d) subgroup means by stress class and biostimulant class with robust '
              'CI and Wald p-values.')
T['capD3'] = ('Chlorophyll targets: frozen models on the 2024–2026 TEST studies, as Figures 18 and 19. Models were frozen before any TEST '
              'chlorophyll value was extracted. (a, b) TEST contrasts with the 95% interval of the pre-declared ML model (red diamonds: outside the '
              'interval); (c, d) RMSE in CV and on TEST.')
T['capD4'] = 'Leave-one-study-out influence on the pooled TRAIN effect of the chlorophyll targets, as Figure 24 (dashed line = pooled effect with all studies).'
T['capD5'] = ('Small-study effects and publication bias for the chlorophyll targets, as Figure 25: funnel plots of study aggregates, Egger, Begg '
              'and multilevel Egger tests, PET-PEESE and trim-and-fill estimates.')
T['tabD1_note'] = ('Effect = pooled SB vs S effect of the cell, % [95% CI]; PI = 95% prediction interval for a new study; * = fewer than five '
                   'studies (tentative). Source: 08_chlorophyll_target/results/c10_cells_chlorophyll.csv.')

OUT = pathlib.Path(__file__).resolve().parent / 'c18_text.json'
old = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
old.update(T)
OUT.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding='utf-8')
print(len(old), 'texts')

T2 = {}
T2['r410'] = (
    'For the chlorophyll targets (Figure 21c, d), the pre-declared Random Forest replaced Ridge. For the chlorophyll index, its error fell steeply '
    'from 0.284 with 9 training studies to 0.203 with 44, while the mean (0.279 → 0.267) and the three-level mean (0.266 → 0.263) hardly '
    'changed; the Random Forest overtook the means at about 18 studies, and the gap was still widening at the largest training size (0.064). For '
    'chlorophyll content, the Random Forest stayed slightly worse than the means at every size (0.324 → 0.320 against 0.316 → 0.309 for the mean, '
    '15–75 training studies), with no trend. Because these curves use folds grouped by dependency cluster, the steep index curve partly reflects '
    'the same closely related studies that inflated its CV gain (Section 4.8).')
T2['r412'] = (
    'For the chlorophyll targets (Figure 23g–l), selection reproduced the yield pattern. For the index, the Random Forest beat the mean without '
    'abstention (−0.068 [−0.118, −0.008]), but on contrasts selected by local error or by disagreement the mean improved even more, so the '
    'advantage shrank to −0.014 to −0.021 with confidence intervals including zero (pre-specified 80% share: −0.019 [−0.044, +0.010], 47 of 55 '
    'studies); random abstention left the advantage unchanged (−0.063 to −0.068), and selection by distance kept it (−0.063 to −0.084), with '
    'coverage of 0.96–0.99. For chlorophyll content, the Random Forest was not better than the mean at any share or under any rule (differences −0.002 to +0.016).')
OUT2 = pathlib.Path(__file__).resolve().parent / 'c18_text.json'
d2 = json.loads(OUT2.read_text(encoding='utf-8')); d2.update(T2); OUT2.write_text(json.dumps(d2, ensure_ascii=False, indent=1), encoding='utf-8')
print('added', list(T2))
