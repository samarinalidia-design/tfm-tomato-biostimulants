# Moderator vocabulary (A399 `moderators` table) with real examples

One row per (feature, level). Level: study (experiment_key null, arm_key null), experiment (experiment_key set, arm_key null) or arm (both set). Put a value at the most general level where it holds for all arms below; use arm level only when it differs between arms (dose, composition, microorganism, strain, stress_intensity, nacl_mm, ...). `value` is the text as in the paper (short, normalised like the examples); numbers go in `value` with the unit in `unit` (e.g. dose 3 + unit g/L; nacl_mm 100; stress_duration_days 21). Control / no-stress arms: biostimulant_class "none (...)", stress_type "none (...)" as in the examples.

| feature | studies in A399 | share arm-level | examples (value [unit]) |
|---|---|---|---|
| stress_type | 270.0 | 0.85 | none (no added NaCl); None; water deficit (reduced irrigation); none (salt free, 0 mM NaCl) |
| biostimulant_class | 269.0 | 0.92 | none (no spray); arbuscular mycorrhizal fungi (AMF) consortium, trap culture ; salicylic acid; commercial blend: fulvic and humic acids + microorganisms |
| system | 268.0 | 0.0 | plastic houses at the same place as trial 3 (Handan district; greenhouse pots (25 cm diameter black polyethylene bags); plastic pots; growth chamber per Methods cross-reference (p5; greenhouse, individual plastic pots, natural light |
| statistical_test | 266.0 | 0.0 | one-way ANOVA; Fisher's LSD post hoc; one-way ANOVA with Tukey HSD at p <= 0.05 (CoStat); Tukey's range test (P < 0.05); two-way ANOVA; Duncan's test |
| composition | 265.0 | 0.9 | washed bacterial cells re-suspended in distilled water, adju; bacterial cell suspension in sterile distilled water; P. azotoformans CHB 1107 M (deletion of acdS, ACC deaminase-; BDUA1 (Bacillus sp.) + BDUA2 (Pseudomonas sp.) |
| experimental_design | 263.0 | 0.0 | Randomized complete block design (RCBD); factorial experiment in split-split plot design (salinity x ; glasshouse pot experiment; 10 arms (7 B. subtilis formulatio; four treatments (control, MT, salt, MT + salt) forming a 2x2 |
| dose | 263.0 | 0.95 | 200 [ppm]; AMF 20 g fresh inoculum + compost 5% [per component as stated; compost % basis not stated]; 10^9 [CFU]; HA 750 ppm + SA 0 (control) [ppm; mM] |
| n_replicates | 262.0 | 0.04 | 24 [biological replicates (seedlings) per group]; 20 [plants per treatment (N=20; whether per independent experiment or in total not stated)]; 25 [plants per treatment]; UNRESOLVED: three (p2 Abstract, p4 Experimental design and g [replications] |
| substrate | 261.0 | 0.14 | mix (composition not restated in Methods 2.14); universal garden soil based on peat substrate and humus from; potting soil; field raised beds fumigated with 98% methyl bromide and 2% c |
| dose_unit | 259.0 | 0.87 | ppm; g dry-weight-equivalent formulation per 100 g seed (CFU per ; g Myco g-1 plant fresh weight at treatment; % v/v of MEF formulation in distilled water (10 mL per pot p |
| route | 253.0 | 0.87 | soil application (soils treated with the amendment); soil incorporation; soil application (method and timing not otherwise described); root bacterization |
| application_stage | 247.0 | 0.85 | FYM forty days prior to transplantation; Si timing not repor; first application two days after salinity imposition (salini; seed before sowing; seedling roots immediately before transp; seedling; 1-month-old seedlings planted in trays and watered |
| stress_intensity | 246.0 | 0.92 | 250 [mM]; -0.73 [MPa]; 4.9 [dS m-1 (ECe, saturation extract; salt stressed level)]; 50, 75 and 100% FC (gravimetric soil moisture content 23, 35 [% field capacity] |
| cultivar | 242.0 | 0.55 | San Marzano Nano; Belladonna (Solanum lycopersicum Mill.); Bright F1; 023 |
| stress_intensity_unit | 236.0 | 0.72 | CFU/g of soil; % NaCl in irrigation solution; % field capacity (55% FC = 8% volumetric soil moisture, Thet; % PEG-6000 in nutrient solution (w/v vs v/v not stated) |
| stress_onset_stage | 220.0 | 0.73 | seedling, from day 13; after 12 d in full-strength Hoagland with 20 uM Fe (preceded; thirty-day-old plantlets; 6-week-old seedlings after 7-day greenhouse acclimatization; |
| irrigation_regime | 211.0 | 0.69 | fully irrigated; drip irrigation, 2 L water per plant daily [L per plant per day]; WW maintained at pot capacity; WS by withholding pot irrigat; V0: no restoration of ETc, single irrigation at transplantin |
| replicate_unit | 193.0 | 0.0 | polythene bag with one tomato stand; inferred from Methods 2; treatment plot (each treatment covered 4.5 m2) within each o; experimental unit = one drip line 6 m long x 1 m wide, emitt; replicate of the randomized block design (plot named for ant |
| microorganism | 171.0 | 0.95 | Pseudomonas sp. (fluorescent pseudomonad); Bacillus haynesii; Bacillus toyonensis; IB 30/07: T. harzianum |
| randomization | 167.0 | 0.0 | plants arranged randomly; randomised complete block; randomized complete block; allocation procedure not describe; randomized design; irrigation water assigned by rows (3 rows |
| fertilization | 156.0 | 0.37 | 70% BNS; factor-level marginal pooled over B and S, not a tr [% of basic nutrient solution strength]; Hoagland's nutrient solution, pH 5.8, supplied daily with wa; nutrient solution, mg/L: N 116, P 21, K 82, Ca 125, Mg 21, S; all plants watered with half-strength Hoagland solution |
| temperature_day_c | 154.0 | 0.35 | average greenhouse temperature 28 C; a day-specific value is [degrees C (period average, not a day setpoint)]; 25-27 [°C; mean temperature range, day/night not separated]; 45 [degC (printed as mean maximum air temperature, 45/27 degC day/night, recorded daily as a mean)]; 23 ± 4 (single overall greenhouse range; no separate day val [°C] |
| n_applications | 151.0 | 0.87 | one initial application plus daily foliar over the 10-day he; PGPR 2 (seed soak and soil drench); foliar agent 1; 1 inoculation occasion (pre-transplant) consisting of 3 succ; GA 2 sprays; HT 1 exposure |
| frequency | 151.0 | 0.85 | two inoculations, 7 and 83 days after transplantation (dat); once a week for a month; two applications at stated stages; interval not stated; LK11: one seed priming at sowing and one seedling applicatio |
| country | 149.0 | 0.0 | Bangladesh; Germany; Türkiye; Jordan (author affiliation only; greenhouse site not stated) |
| stress_duration_days | 146.0 | 0.8 | 60 [days]; 7 [day]; 45 [days from sowing into NaCl-amended soil to uprooting (planned interval; not printed as a stress duration)]; total not printed; 8 days printed only for the electrolyte-l [days] |
| strain | 136.0 | 0.96 | TUCIM 10320; H2-7; V62; TS3-1 |
| relative_humidity | 128.0 | 0.04 | 60-75 [%]; 50–80 [%]; 70 [%]; 61.4–65.6 [%] |
| temperature_night_c | 117.0 | 0.45 | 20-25 (single greenhouse range; no day/night split stated) [C]; 24 [C during the 14-d growth-chamber stress phase (22 C growth room before/after)]; 23 ± 4 (single overall greenhouse range; no separate night v [°C]; 24 +/- 2 [C (inoculated plants; no day/night split printed)] |
| photoperiod_h | 108.0 | 0.07 | 16-8 (light-dark, as printed) [h]; 10 [h]; 12-14 [light hours/day]; 15 [h light per day (15 h light / 9 h dark, fluorescent); applied to tomato via 'same conditions described for Arabidopsis' and Arabidopsis pot phase 'same light regime'] |
| days_application_before_stress | 104.0 | 0.79 | 12 (first application); 0 (second application) [d]; 3 [d (first spray before heat onset)]; PGPR: seed treatment 5 weeks and root treatment 2 weeks befo [weeks (PGPR); h (foliar agent)]; at least 28 [days] |
| season | 97.0 | 0.14 | summer 2014; winter 2017-2018 and winter 2018-2019; transplanting first w; 2018; 2019 |
| genotype_type | 93.0 | 0.52 | F1 hybrid scion (cv. Belladonna F1); rootstock self or S. ly; VIGS empty-vector control (TRV::00); thermotolerant; cultivar |
| nacl_mm | 83.0 | 0.99 | 43 [mM]; 250 [mM]; 175 [mM]; 80 [mM] |
| pot_volume_l | 80.0 | 0.0 | volume not printed; pot dimensions 5 cm x 5 cm x 8 cm [cm (dimensions, not L)]; 50 [L]; 8 kg soil per pot; pot size 25/25 cm; volume in litres not p [kg soil (source unit, not L)]; 1 kg pot; mass only, litres not stated, not converted [kg] |
| product_name | 79.0 | 0.92 | Biofertilizer (Bf); commercially sourced from De Novo Capita; Stimulate (Stoller); Galaxaura rugosa aqueous extract 1 (collection season not na; Fulvagra |
| soil_ph | 78.0 | 0.24 | 8.01; 8.5; 6.5; 7.05 |
| soil_texture | 78.0 | 0.13 | Silty clay loam; sandy clay loam (general statement for all sites; site-speci; fine-loamy; silty clay; 6.5% sand, 45% silt, 48.5% clay (soil before mix |
| ppfd | 73.0 | 0.09 | 400 [umol m-2 s-1 (printed as 'μmol/m−2 s−1'; reported as light intensity)]; 25 or 75; not assigned to a specific experiment [umol photons m-2 s-1]; 150-660 (PAR at canopy height, range) [umol m-2 s-1]; 100 [µmol m-2 s-1] |
| soil_ec | 61.0 | 0.78 | 1.5 [mS cm-1]; 1.158 [dS m-1 (EC1:5; +/- 0.04; NaCl-condition value, not printed per arm)]; 0.65 [dS m-1]; 785 [μS cm−2 (as printed)] |
| organic_matter | 58.0 | 0.4 | organic carbon 0.08 (printed as organic carbon, not organic  [% organic C]; 1.28 [g kg-1 dry soil]; 1 [% OM (culture soil before compost amendment)]; 1.17 [%] |
| latitude | 53.0 | 0.0 | 43°31'N; 41.545343 [decimal degrees N]; 23° 3′ 44.0.01″ N (as printed, malformed seconds) [degrees N as printed]; 41°5′42″36 N |
| field_capacity_pct | 41.0 | 0.96 | 65%-105% [% of field capacity (soil water content)]; 31.2 [% v/v volumetric SWC at field capacity (soil property, not a %FC stress level)]; 80 [% field capacity]; 90 [% of pot water-holding capacity (WW irrigation level and DS recovery level)] |
| pathogen | 40.0 | 0.49 | Fusarium oxysporum f.sp. radicis-lycopersici (Forl); Fusarium solani (Fusarium wilt); Ralstonia solanacearum; Xanthomonas euvesicatoria |
| ec_irrigation_ds_m | 40.0 | 0.91 | 572 µS/cm (as printed; not converted) [µS/cm]; 10.5 [dS/m]; 1.0 [dS/m]; 1.44 [dS m-1] |
| inoculation_method | 38.0 | 0.31 | colonized agar disk placed mycelium side down on adaxial sid; inoculated to each respective plant in the roots; no artificial inoculation; natural infestation in glasshouse; point droplet at centre of third intact leaf from bottom, le |
| inoculum_dose | 35.0 | 0.41 | ~10^7 [CFU/ml]; 1000000 [conidia/mL]; 0.2 [OD600; 1 ml/g of the potting mixture]; 3 x 10^8 [CFU/mL] |
| plant_density_m2 | 29.0 | 0.0 | spacing 0.2 m between plants and 0.5 m between rows; plants ; 2 [plants m-2]; density not printed; spacing only: 1.2 m between bed centers; 2.4 [plants m-2 (at the beginning of the experiment)] |
| fruit_type | 25.0 | 0.41 | oval fruit, processing (canning) type; small red ripened fruits; round, red, thin-shelled table tomato (cultivar description ; salad type, large fruits (cultivar description) |
| pathogen_strain | 23.0 | 0.33 | KACC 40032; PIT30; TFPK401; OTA22 |
| growth_habit | 10.0 | 0.64 | indeterminate; semi-determinate; dwarf; determinate |
| grafted | 6.0 | 0.46 | TRUE (factor levels: self-grafted Belladonna/Belladonna or g; ungrafted as labelled for control sub-plots; no grafting ste; grafted onto cv. M82; True |
| vpd_kpa | 1.0 | 0.0 | 0.773 [kPa]; 0.625 [kPa] |