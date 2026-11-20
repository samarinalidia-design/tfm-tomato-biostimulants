# -*- coding: utf-8 -*-
"""Methods (section 3) of the TFM: English version of the original Spanish methodology with targeted updates to the
work actually performed (V5, 2026-11-20). Markup: **bold**, *italic*, `path/code`. {F:key}/{T:key} = figure/table numbers."""

GH = "https://github.com/samarinalidia-design/tfm-tomato-biostimulants"
R = "05_analysis_train_expansion_v5/v5"          # all paths are relative to the root of the GitHub repository GH
TRAIN_DB = "03_data_freeze/train_dev_DATA_FREEZE_20261113T112939135807Z"
TEST_DB = "03_data_freeze/external_test_DATA_FREEZE_20261118T105532769144Z"
FIG = "05_analysis_train_expansion_v5/v5/figures"

METHODS = [
    ('h1', '3. Research methodology'),
    ('p', 'This methodology describes a reproducible pipeline that (i) builds, verifies and freezes the SynerPlant evidence base and (ii) uses it for '
          'meta-analysis and for predictive modelling. The analytical unit is a verified experimental **contrast** (one comparison between two treatment '
          'groups of the same experiment), not a whole publication. Fruit yield is the primary predictive endpoint; terminal dry biomass is modelled '
          'separately as a secondary endpoint. Extraction maximised both the quantitative information and the potentially generalisable descriptors of each '
          'experiment: genotype, cultivation system, physical definition of the stress, composition, dose and application of the biostimulant, experimental '
          'design, endpoint, time, analytical method, uncertainty and quality of the evidence.'),
    ('p', 'The protocol distinguishes four levels: (i) the historical ledger of identified records; (ii) full-text candidates; (iii) the canonical document '
          'corpus actually retrieved; and (iv) the analytical database derived after extraction and quality control (QA). Publications up to 31 December 2023 '
          'form the development set **TRAIN_DEV**. Publications first available online from 2024 onwards were collected afterwards as a separate '
          '**EXTERNAL_TEST** corpus (2024–2026), processed with the same screening, extraction, harmonisation and QA protocol, and frozen as an independent '
          'database. Because this test corpus had already been inspected in earlier model versions (V2, V4), its use for the final models is labelled '
          '**POST_HOC_TEST_REUSE** and is not presented as a first, blind confirmatory test (Section 3.17).'),
    ('p', f'All code, frozen databases and analysis outputs are openly available in the GitHub repository {GH} (release `data-freeze-v5`); every file '
          'path given in this chapter is relative to the root of that repository. The final analysis version is **V5** '
          f'(`{R}`); its scripts are in `{R}/scripts`, the analysis tables in `{R}/data`, the frozen models in `{R}/freeze`, the numerical results in '
          f'`{R}/results` and all figures in `{FIG}`. A step-by-step description of how to rerun the analyses is given in `{R}/README_V5.md`.'),

    ('h2', '3.1. Overall study design and traceability principle'),
    ('p', 'The study is a reproducible computational investigation based on published experimental evidence. The bibliographic unit (article), the '
          'experimental unit (independent experiment), the treatment unit (arm), the observation unit (measurement or biological replicate) and the '
          'analytical unit (contrast) are kept explicitly separate. A publication may contain several experiments; an experiment may contain several doses, '
          'stress levels, sites, seasons, organs and timepoints; and each scientifically distinct combination may generate one or more contrasts. This '
          'hierarchy avoids pseudoreplication and avoids reducing a complex publication to a single row.'),
    ('p', 'The minimum trace is: bibliographic record → source file → study → experiment → experimental context → arm → intervention component → stress '
          'exposure → raw measurement → provenance → contrast → analysis table. Source values are never overwritten. Every correction, unit conversion, SD '
          'reconstruction, categorical normalisation or effect-size calculation is stored as a derived, reproducible layer. Every table uses primary and '
          'foreign keys; companion publications and duplicate versions are linked to the same experiment where appropriate. {F:workflow} summarises the '
          'complete workflow as finally executed, and {T:stages} lists the stages, their unit of analysis and the reproducible artefacts.'),
    ('fig', f'{FIG}/FigM1_workflow.png', 'workflow', 'Overall SynerPlant workflow as executed in this TFM.',
     'The TRAIN_DEV database (publications up to 2023) and the EXTERNAL_TEST database (2024–2026) were built with the same protocol and frozen separately. '
     'Analysis tables (V5) were built from both with identical rules; the meta-analysis describes average effects, the predictive branch estimates what '
     f'can be expected in a new study. Source: `{R}/scripts/v5_16_methods_figs.py`.'),
    ('tab', 'stages', 'Stages, unit of analysis and reproducible artefacts of the pipeline.',
     ['Stage', 'Main unit', 'Reproducible artefact / gate'],
     [['Historical search and de-duplication', 'Bibliographic record', 'Query logs, historical ledger, normalised DOI/title and duplicate status.'],
      ['Canonical corpus', 'File / publication', 'CORPUS_MANIFEST, file IDs, URLs, MIME type, size, SHA-256 and source role.'],
      ['Scientific screening', 'Publication and experiment', 'Class A/B/C/D/E/X, decision, reason and analytical role; X is not extracted.'],
      ['Document extraction and structuring', 'File / experiment / arm / measurement', 'Source layer V4.3 + STUDY_HANDOFF/QA + semantic contract V4.4; full text, supplements, tables, figures and raw data with provenance.'],
      ['Verification and reconciliation', 'Source / critical field', 'Automatic QA + targeted verifier + human review of flags; conflicts and figure digitisation resolved before integration; page-image receipts.'],
      ['Harmonisation and QA', 'Measurement', 'Compatible units, SD/SE/CI, inferential n, duplicates, missingness, outlier flags and risk of bias.'],
      ['Effect construction', 'Contrast', 'S vs C, B vs C, SB vs S, S×B and A×B interactions when the design allows.'],
      ['Database freeze', 'Verified contrast', f'contrast_candidates, marts, dictionary, QA, CSV/Parquet/SQLite and hashes (`{TRAIN_DB}`; `{TEST_DB}`).'],
      ['Analysis tables V5', 'Contrast', f'Source-verified corrections, identical TRAIN/TEST rules, variance imputation (`{R}/scripts/v5_01_build.py` → `{R}/data`).'],
      ['Meta-analysis, ML and external evaluation', 'Study / dependency cluster as group', f'Nested grouped CV, MODEL_FREEZE (`{R}/freeze`), one evaluation on TEST labelled POST_HOC_TEST_REUSE.']],
     [4.2, 3.4, 7.4]),

    ('h2', '3.2. Evidence sources, historical search and definition of TRAIN_DEV and TEST'),
    ('p', 'The bibliographic universe was built in two complementary passes in Crossref, Europe PMC and OpenAlex. The queries combined tomato terms '
          '(*Solanum lycopersicum*, *Lycopersicon esculentum*), biostimulants, abiotic stress and primary experiments, with the syntax adapted to each source '
          '(Annex A). The extension to biotic stress is documented as a protocolised extension of the corpus, without retrospectively rewriting the historical '
          'queries. Raw results, date, source, query identifier and sufficient metadata to reconstruct de-duplication and screening were kept.'),
    ('p', 'The first pass produced 19 910 records and the precision expansion 19 717, giving a historical total of 39 627. After merging and de-duplicating by '
          'DOI and normalised title, 12 141 unique records remained. The historical ledger was split into publications ≤ 2023 (n = 7 331) and ≥ 2024 '
          '(n = 4 810); these are record counts, not the final sizes of the analytical samples. The time criterion defines the validation plan: publications '
          'up to 2023 for TRAIN_DEV and publications from 2024 for the external test.'),
    ('p', 'TRAIN_DEV was not enlarged opportunistically in response to model performance. Searches for TRAIN_DEV were limited to resolving identities, '
          'repairing links and retrieving texts or supplements of eligible candidates already in the ledger. The last historical expansion still added '
          '6.746 % of records that looked like primary studies; the corpus is therefore described as systematically built and broad, but not exhaustive.'),
    ('p', '**Update (test corpus).** The external test corpus was collected after the TRAIN_DEV database had been frozen (13 November 2026) with a separate '
          'search restricted to publications first online from 1 January 2024: 108 records were identified, 80 were in scope and 58 were fully processed '
          '(16 had no eligible target and 6 were out of scope). The resulting EXTERNAL_TEST database contains 80 studies, 57 of which yield computable '
          f'contrasts (2 001 candidate contrasts), and was frozen on 18 November 2026 (`{TEST_DB}`, `MANIFEST.json`, `acceptance_report.json`). The '
          'system and its rules are documented in `02_agent_system_external_test/CLAUDE.md`.'),

    ('h2', '3.3. Historical screening, current canonical corpus and PRISMA-style reporting'),
    ('p', 'In the historical flow, the 7 331 records then assigned to the ≤ 2023 block were screened on title and abstract. 1 732 were tagged '
          'ADVANCE_FULLTEXT and 5 599 were excluded as WRONG_CROP (n = 1 762), WRONG_STRESS (n = 2 365), WRONG_OR_NO_BIOSTIMULANT (n = 635) or '
          'NOT_PRIMARY_EXPERIMENT (n = 837). A second screening reduced the set to 1 192 full-text candidates. These counts are kept for reproducibility and '
          'are not the final number of eligible TRAIN_DEV studies.'),
    ('p', 'The initial bottleneck was access, not biological eligibility. After remediation and document normalisation, the canonical corpus used for '
          'extraction contains 766 studies linked to 766 full texts and 100 supplements. The correspondence between the manifest and Google Drive is audited '
          'through active identifiers, not visible file names. Source availability and the scientific decision are kept as independent variables.'),
    ('p', 'All 766 studies with an interpretable source were fully screened and classified into an analytical taxonomy A/B/C/D/E/X ({T:classes}). In the '
          'audited state before extraction: A = 399, B = 158, C = 29, D = 53, E = 42 and X = 85. The 681 non-X studies are kept for structured extraction '
          'according to their role; class X stays in the manifest and in the selection denominators but does not enter the quantitative database.'),
    ('p', 'The extraction queue is generated automatically from the manifest and the screening, never by ad-hoc manual selection. It comprises 774 non-X '
          'source files, prioritising machine-readable supplements, then other supplements with data and finally the full text. Final extraction and '
          'model-readiness counts are recomputed by code in every build and are not transcribed manually. **Update:** the historical PRISMA snapshot shown '
          'in earlier drafts has been replaced by the current flow diagram of studies and contrasts for both TRAIN and TEST, reported in Section 4.1 '
          f'(`{FIG}/Fig16_PRISMA_flow.png`; counts from `{R}/results/build_flow_v5.csv`).'),

    ('h2', '3.4. Inventory, normalisation, linkage and content verification'),
    ('p', 'The canonical Google Drive folder is inventoried recursively. Normalisation is copy-only: source files are neither moved nor overwritten. Full '
          'texts and supplements are registered by function and receive stable identifiers. Every run is idempotent and resumable through checkpoints, so that '
          'a file that has already been inventoried is never created again or counted as new evidence.'),
    ('p', 'CORPUS_MANIFEST records at least study_id, active file_id, name, DOI/identity hint, role (FULLTEXT/SUPPLEMENT), URL, MIME type, size, checksum '
          'where available, identity status, access status and timestamp. The manifest is the documentary source of truth; analytical spreadsheets reference '
          'its file IDs. Any discrepancy between extension and content signature is routed by the real file signature and logged as QA.'),
    ('p', 'Identity is not inferred from the folder name alone. A DOI confirmed in the document has priority, followed by normalised title and author/year. '
          'Exact duplicates are detected with SHA-256; companion publications are linked through study_relations instead of being counted as independent '
          'studies. An ambiguous identity is never forced automatically and is sent to manual review.'),
    ('p', 'For PDFs with a digital text layer, that layer is the first extraction source. OCR is reserved for documents without readable text and the method '
          'is recorded in the provenance. For quantitative values, the most structured representation is preferred: machine-readable supplementary dataset > '
          'supplementary table > main-text table > explicit value in the text > figure digitisation.'),

    ('h2', '3.5. Full-text retrieval and scientific screening'),
    ('h3', '3.5.1. Source retrieval and access states'),
    ('p', 'Retrieval started from the 1 192 candidate identities, first checking PDFs and metadata already present in the corpus to avoid redundant '
          'downloads. The primary match is an exact DOI; when the DOI is missing or inconsistent, the normalised title and, if available, author/year are used '
          'as additional evidence. Ambiguous matches are kept for manual review and are not accepted automatically.'),
    ('p', 'For identified candidates, lawful access routes were documented through PMC/Europe PMC, publisher pages or repositories linked by OpenAlex/'
          'Crossref, and manual retrieval when the automated route was insufficient. Every attempt keeps the source URL, source type, access date and status '
          '(obtained, paywalled, access_blocked, landing_page_only, route_failed, unresolved or functional equivalents).'),
    ('p', 'Lack of access is never coded as a scientific exclusion. The FULLTEXT_NEEDED list is derived only after reconciling bibliographic identities with '
          'existing PDFs and removing exact duplicates or versions already represented. Supplementary materials are retrieved and linked separately because '
          'they may contain quantitative data missing from the main text. This separation between document acquisition and eligibility decision makes it '
          'possible to distinguish an absence of evidence from an absence of access to the evidence.'),
    ('h3', '3.5.2. Full-text scientific screening'),
    ('p', 'Each publication with an interpretable source receives a class A/B/C/D/E/X and a verification status, decided on the complete article and its '
          'supplements. The publication-level class is used for corpus management; final target eligibility is decided at experiment/contrast level, because '
          'a mixed publication may contain experiments with different analytical roles ({T:classes}).'),
    ('p', 'Class A requires tomato, an experimental stress (abiotic or biotic) and a biostimulant, and provides the S/SB contrasts for fruit yield or dry '
          'biomass. Class B contains tomato studies with stress but without biostimulant (baseline S/C response); class C tomato studies with biostimulant but '
          'without stress (baseline B/C response). Class D contains other crops with stress and biostimulant (cross-species transportability) and class E other '
          'crops with a single factor (biological and mechanistic context). Classes B–E are analysed in separate strata: they do not contribute tomato S/SB '
          'contrasts and do not increase the number of independent studies of the primary model. Class X is excluded.'),
    ('p', 'The core abiotic stresses are drought/water deficit, salinity and high temperature. Cold/chilling, nutrient limitation, waterlogging/hypoxia, '
          'osmotic stress, toxic elements, radiation and combinations are also kept when explicitly reported. Each stress keeps its original physical '
          'representation; no "universal severity" mixing, for example, mM NaCl with water potential or temperature, is created. Biotic stresses are kept in a '
          'separate BIOTIC stratum with pathogen, species/isolate, inoculum, method and timing of inoculation; Fusarium is retained as a pre-specified subgroup.'),
    ('tab', 'classes', 'Screening taxonomy and role of each class in the evidence base.',
     ['Class', 'Short criterion', 'Role in the database', 'Use'],
     [['A', 'Tomato + stress + biostimulant', 'PRIMARY', 'Direct mitigation (SB vs S); S×B interaction when C/S/B/SB exist; B vs C within the same studies.'],
      ['B', 'Tomato + stress, no biostimulant', 'BASELINE_STRESS', 'Baseline response to stress; S vs C.'],
      ['C', 'Tomato + biostimulant, no stress', 'BIO_BASELINE', 'Baseline biostimulant effect; contextual/secondary evidence.'],
      ['D', 'Other crop + stress + biostimulant', 'TRANSFER', 'Context for transportability; not equated automatically with tomato.'],
      ['E', 'Other crop + stress only or biostimulant only', 'SUPPORTING', 'Mechanistic context / feature support; not a primary target.'],
      ['X', 'Out of scope or unusable', 'EXCLUDE', 'Kept in ledger/PRISMA; not extracted into the quantitative database.']],
     [1.4, 4.4, 3.2, 6.0]),

    ('h2', '3.6. Data extraction: document pipeline, structuring and relational model'),
    ('p', 'The document extraction layer was run with the local pipeline V4.3 (run docling_local_sourceqa_v4_3_rerun_380) in Python/Jupyter. Sources are '
          'selected from a frozen file-level manifest derived from the TFM_ML_DATABASE_V3 database, which links each study_id to its full text and '
          'supplements, keeps the screening class and excludes class X from quantitative extraction. The corpus is processed in batches; hashes and '
          'checkpoints allow resuming without repeating completed studies and keep failures retryable.'),
    ('p', 'The first layer is a deterministic source layer that does not depend on an API or a generative model. Files are routed by content signature. PDFs '
          'are processed with Docling (high-accuracy table mode) and PyMuPDF for text, pages and native geometry; RapidOCR is activated only when the digital '
          'layer is insufficient. XLS/XLSX/CSV files are read with pandas/openpyxl, keeping exact sheet and A1-cell provenance. Word documents are extracted '
          'natively and legacy .doc files are converted with LibreOffice. Figures are exported at high resolution together with vector words/coordinates when '
          'available; OpenCV is used only to detect geometric structure and digitisation candidates, never to accept graph values without calibration.'),
    ('p', 'For a given value the source priority is: machine-readable supplement > supplementary table > main-text table > explicit number in the text > '
          'calibrated figure digitisation. A lower-priority source may supply n, SD/SE/CI, units, timepoints, context or missing statistics, but does not '
          'duplicate a value already supported by a higher representation. Conflicts between sources are logged and never resolved by silent substitution.'),
    ('p', 'Each study produces an independent folder with the source artefacts and three control outputs: STUDY_HANDOFF.json (inventory, text, tables, sheets, '
          'figures, quantitative candidates and locators), STUDY_QA.json (coverage and study status) and HUMAN_REVIEW_QUEUE.csv when assets or decisions need '
          'review. The source layer is complete only when all expected sources have been processed and every quantitative asset has an explicit disposition.'),
    ('p', 'The second layer is the semantic structuring of the hand-off. An initial attempt with ChatGPT did not produce usable structured output, so '
          'structuring was carried out with a multi-agent system built on Claude large language models (Anthropic; Claude Opus for extraction, figure '
          'digitisation and adjudication, Claude Sonnet for the independent verification pass), run through Claude Code '
          '(TRAIN_DEV: `01_agent_system_train_dev`; EXTERNAL_TEST: `02_agent_system_external_test`). '
          'All workflow state is kept in SQLite and agents submit results only through a validating command-line tool (`tools/tfm.py`). Each value is '
          'extracted twice and independently: pass A (semantic extraction) and pass B (verification against the original source, blind to pass A); figures '
          'are read twice from calibrated axes (at least three ticks). The two passes are reconciled in code: agreeing values are accepted automatically, '
          'while conflicts and values found by only one pass go to an adjudicator agent and, where unresolved, to the author. Every accepted value is tied '
          'to a source receipt (page image, table cell or figure item; 12,011 receipts in TRAIN_DEV and 2,087 in EXTERNAL_TEST). Model identifiers, run '
          'times and task status are recorded for each of the 5,678 (TRAIN_DEV) and 1,354 (EXTERNAL_TEST) agent runs. The output follows a versioned '
          'semantic JSON contract. The schema separates study, experiments, '
          'experiment_context, arms, stress_factors, arm_components, measurements, reported_effects, statistical_analyses, raw_observations, data_assets, '
          'provenance_qa, risk_of_bias, contrast_candidates, asset_dispositions, figure_digitization_queue and ambiguities. The semantic interpretation does not '
          'modify the original evidence: it produces a structured proposal that must pass the verification of Section 3.8. Mixtures are decomposed into '
          'arm_components, biological raw replicates are kept in raw_observations and high-dimensional omics matrices are registered as data_assets rather '
          'than exploded into thousands of agronomic observations. In TFM_ML_DATABASE_V3 (schema 3.6.0) stress_factors is the source of truth for stress '
          'exposure. {F:schema} shows the relational model and {T:layers} its layers; {F:extraction} summarises the extraction and verification pipeline.'),
    ('fig', f'{FIG}/FigM4_relational_schema.png', 'schema', 'Relational schema of the evidence database.',
     'Raw, QA and effect entities are kept separate; analysis exports are derived, versioned products. The frozen databases '
     '(`TFM_DATABASE_CLASS_A_FINAL.sqlite`, TRAIN_DEV and EXTERNAL_TEST) are available from the release '
     f'{GH}/releases/tag/data-freeze-v5 and their exported tables from `{TRAIN_DB}` and `{TEST_DB}`.'),
    ('tab', 'layers', 'Layers of the relational model and associated unit of observation.',
     ['Layer', 'Main tables', 'Row unit', 'Function'],
     [['Identity', 'studies, files, screening, study_relations', 'publication / file', 'Identity, class, links and document traceability.'],
      ['Experiment', 'experiments, experiment_context', 'experiment / site / season', 'Design, environment, system, experimental unit.'],
      ['Treatment', 'arms, arm_components, stress_factors', 'arm / component', 'Stress, mixture, dose, formulation and application.'],
      ['Observation', 'measurements, raw_observations', 'measurement / replicate', 'Values, uncertainty, n, outcome, time, organ.'],
      ['Assets', 'data_assets', 'file / matrix', 'Omics, raw/processed matrices and sample mapping.'],
      ['QA', 'provenance_qa, risk_of_bias, wf_source_receipts', 'value / domain', 'Verification, provenance (incl. page images) and risk of bias.'],
      ['Effects', 'contrast_candidates, covariance', 'contrast', 'lnRR, interactions and dependence structure.'],
      ['Export', 'evidence_long, A_* marts, V5 analysis tables', 'contrast', 'Clean input to meta-analysis and ML.']],
     [2.2, 4.6, 3.2, 5.0]),
    ('fig', f'{FIG}/FigM5_extraction_pipeline.png', 'extraction', 'Extraction, completion and verification pipeline.',
     'Local deterministic extraction (Docling and auxiliary tools) is followed by structured semantic extraction and a final targeted verification of '
     'critical fields before integration into the relational database. This figure replaces the Spanish infographic of the earlier draft.'),

    ('h2', '3.7. Outcomes, primary endpoint and target hierarchy'),
    ('p', 'The primary endpoint is tomato fruit yield under stress, expressed as harvested mass and evaluated through the direct comparison between plants '
          'with stress and biostimulant (SB) and plants exposed to the same stress without biostimulant (S). Total yield is preferred; marketable yield is kept '
          'as a separate definition. Each contrast must be compatible in fresh/dry basis, denominator (plant/area), period and cumulative or single harvest. '
          'Fruit number, mean fruit mass and water productivity are different outcomes. Terminal dry biomass is the independent secondary endpoint: whole-plant '
          'biomass is preferred, otherwise shoot biomass, while root biomass is kept separately. Yield and biomass are never pooled into one target ({T:outcomes}).'),
    ('p', 'The evidence layer also keeps growth/morphology, root architecture, gas exchange, photosynthesis and fluorescence, pigments, water relations, '
          'ionic/nutritional status, oxidative damage, antioxidants/redox, osmolytes, hormones/signalling, metabolomics, transcriptomics, proteins/enzyme '
          'activity, fruit quality, phenology, survival/damage and stress indices; for BIOTIC also disease severity and incidence, pathogen load, lesion area, '
          'mortality/survival and gall indices. Biomarkers measured after treatment may be used in mechanistic synthesis but never as pre-experimental predictors.'),
    ('p', '**Update (yield definitions, V5).** Contrasts were kept when the yield definition was total, marketable or unspecified; non-marketable yield and '
          'yield *fractions* (for example green/unripe fruit, or single fruit-size classes) were excluded because they are parts of the total, not the total '
          'itself. Every yield contrast was assigned a definition tier (STRICT: total, fresh, cumulative, known denominator and unit; ASSUMED; BROAD; '
          'UNIT_UNRESOLVED; EARLY; DRY) that is used as a descriptor in the models and for sensitivity analyses, not as a filter. Dry biomass was restricted to '
          'shoot or whole-plant organ scope and, when an experiment reported several timepoints, to the last timepoint of each group.'),
    ('tab', 'outcomes', 'Outcome hierarchy and analytical rule.',
     ['Family', 'Role', 'Examples', 'Rule'],
     [['Fruit yield', 'Primary', 'kg/plant, t/ha, marketable', 'Primary endpoint: total yield; marketable kept as a definition tier; fractions excluded.'],
      ['Terminal dry biomass', 'Secondary', 'whole plant, shoot; root separately', 'Secondary endpoint; root-only kept separately.'],
      ['Fresh biomass / growth', 'Secondary', 'fresh mass, height, leaf area', 'Separate scales/families.'],
      ['Physiology', 'Secondary', 'A, gs, Fv/Fm, RWC, pigments', 'Keep biological direction, unit and time.'],
      ['Biochemistry / ions', 'Mechanistic', 'proline, MDA, CAT, Na+/K+', 'Never inverted automatically to build a "benefit score".'],
      ['Omics', 'Data asset', 'metabolites, genes, proteins', 'Register matrix/samples; features are not pseudo-replicated as agronomic rows.']],
     [3.2, 2.2, 4.2, 5.4]),

    ('h2', '3.8. Provenance, quality control, verification and statistical reconstruction'),
    ('p', 'Every quantitative value and every relevant categorical variable is linked to its source_file_id and, whenever possible, to page, table, '
          'figure/panel, sheet/A1 cell or dataset variable, together with extraction method, unit, transformation and verification_status. Each asset receives '
          'an explicit disposition: EXTRACTED, DUPLICATE_HIGHER_PRIORITY, NOT_ELIGIBLE, NEEDS_DIGITIZATION or NEEDS_REVIEW. Values present only in graphs are '
          'never estimated visually: they remain in figure_digitization_queue until a calibrated, verifiable digitisation is available.'),
    ('p', 'Automatic control runs first at file level and then at study level (source_file_coverage, table_asset_coverage, figure_asset_coverage, '
          'quantitative_figure_asset_coverage, failed_sources, needs_review_sources). Operational states include SOURCE_LAYER_COMPLETE, NEEDS_REVIEW and FAIL; '
          'PENDING_VERIFICATION indicates that extraction has finished but the semantic interpretation has not yet been verified. A file or study in FAIL is '
          'not considered final and is reprocessed after the technical cause has been corrected.'),
    ('p', 'Semantic verification consists of one main structured pass and a targeted review of the critical fields: identity and composition of the arms, '
          'stress_factors, outcome and timepoint, mean, SD/SE/CI, inferential n, unit, dose/application, factorial design, dependence between contrasts and '
          'provenance. Missing information is marked as not reported and is never inferred. Ambiguous cases, conflicts between sources, quantitative figures '
          'and complex designs are sent to human review. Discrepancies are never averaged. When an omission is detected later, the correction is applied as a '
          'versioned patch on the study record, preserving the raw value, the original source and the verification history. For every verified page a '
          f'rendered page image and its extracted text are stored as a *source receipt* (`wf_source_receipts`; the page images '
          'are kept locally and are not redistributed because the articles are copyrighted), which allows any value to be checked against the original page.'),
    ('p', 'Randomised units, biological replicates, technical replicates, subsamples and independent repetitions are distinguished. The inferential n is the '
          'unit that was actually randomised; an additional technical reading does not increase n. When a supplement contains identifiable biological '
          'replicates, raw values are kept and mean, SD and n are recomputed reproducibly. Conversions of uncertainty are applied only when the required '
          'assumptions are explicit and documented ({T:uncert}):'),
    ('eq', 'SD = SE · √n'),
    ('eq', 'SD = [(U − L) / (2 · t₀.₉₇₅, n−1)] · √n     (two-sided CI of a mean; assumptions documented)'),
    ('tab', 'uncert', 'Permitted rules for reconstructing uncertainty and n.',
     ['Reported value', 'Permitted conversion', 'Condition / QA'],
     [['SD', 'Used directly', 'Compatible unit; SD ≥ 0.'],
      ['SE + n', 'SD = SE·√n', 'n must be the independent experimental unit.'],
      ['CI of a mean + n', 'CI → SE → SD', 'CI level and reference distribution known.'],
      ['CI / difference between groups', 'No arm SD derived by default', 'Only with an explicit formula and sufficient assumptions.'],
      ['p-value without statistic', 'No variance reconstructed by default', 'Kept as metadata, not as a substitute for SD.'],
      ['ANOVA CV % or LSD of the experiment', 'SD of each arm from CV × mean or LSD / (t·√(2/n))', 'Used before any imputation (V5); flagged STUDY_PRINTED_CV_OR_LSD.'],
      ['Raw biological replicates', 'Recompute mean/SD/n', 'Replicate IDs and experimental unit must be clear.'],
      ['Technical replicates', 'Do not increase n', 'Kept as nested measurements.']],
     [4.2, 5.0, 5.8]),
    ('p', '**Update: source-verified corrections in the V5 analysis tables.** Before modelling, a final audit of the analysis tables found errors that '
          'were confirmed against the stored page images and corrected in the analysis tables only (the frozen databases were not modified). All changes are '
          f'listed in `{R}/data/corrections_register.csv` and implemented in `{R}/scripts/v5_01_build.py`: '
          '(i) in two studies (D_8a246bc169c4b812 and 112) the yields of fruit-size fractions (small, medium, large) had been stored as separate "total yield" '
          'contrasts; they were replaced by one total-yield contrast per arm pair, computed as the sum of the fraction means of the same plants, without summing '
          'SDs (none were reported and the covariance between fractions is unknown); the interaction A×B of the same study was recomputed from the sums; '
          '(ii) in study 717 the harvest year had been taken from the publication year (2021); the year was bound to each measurement (2018, 2019) and each '
          'season was treated as a separate experiment, and the "green yield" (unripe fruit) columns were excluded as a fraction; '
          '(iii) errors in the automatic stress classification were fixed (for example, the code "drought" was partly read as heat, "nutrient solution" as '
          'nutrient stress and "temporary wilting" as disease), biotic stresses such as early blight in D_9f55f313bda6b2a2 were classified as BIOTIC and '
          'experiments with two simultaneous stresses as COMBINED; full-irrigation arms coded as stress in study 41 were recoded as unstressed; '
          '(iv) the author-declared salinity of study 112 (soil EC 1.2 mS cm⁻¹, below the tomato threshold of about 2.5 dS m⁻¹, with a control shared with '
          'the unstressed control of D_8a246bc169c4b812) was recoded as "no stress" and flagged as disputed, keeping the authors\' statement in a separate '
          'column; (v) unknown hybrid status was no longer coded as "not hybrid" (0) but as unknown; and (vi) exact duplicate and constant columns were removed '
          'from the actual model inputs (Section 3.12). Unknown cultivars stay UNSPECIFIED, latitude derived from the country centre is labelled '
          'COUNTRY_CENTROID, and missing data were never invented.'),

    ('h2', '3.9. Effect sizes, factorial contrasts and propagation of uncertainty'),
    ('p', 'Effects are computed only from reconciled raw values. C = control without stress or biostimulant, S = stress without biostimulant, '
          'B = biostimulant without stress and SB = stress + biostimulant ({F:contrasts}). For strictly positive means the natural logarithm of the response '
          'ratio (lnRR) is used and validated separately for each endpoint. lnRR is convenient for biologists because it expresses a relative change that is '
          'independent of the unit (kg per plant, t per hectare) and can be back-transformed into a percentage.'),
    ('eq', 'lnRR_S|C = ln(Ȳ_S / Ȳ_C)        [stress effect = stress damage D]'),
    ('eq', 'lnRR_B|C = ln(Ȳ_B / Ȳ_C)        [baseline biostimulant effect]'),
    ('eq', 'lnRR_yield = ln(Ȳ_yield,SB / Ȳ_yield,S)        [primary target: fruit yield]'),
    ('eq', 'lnRR_biomass = ln(Ȳ_biomass,SB / Ȳ_biomass,S)        [secondary target: terminal dry biomass]'),
    ('p', 'The percentage interpretation is Effect (%) = 100·[exp(lnRR) − 1]; for example lnRR = 0.37 corresponds to +45 %. No epsilon or pseudo-count is '
          'added to make zero or negative means positive. The predictive tables contain both SB vs S contrasts (effect under stress) and B vs C contrasts '
          '(effect without stress) of class A studies; the type of contrast is an explicit descriptor.'),
    ('eq', 'Var(lnRR_T|C) = SD_T²/(n_T·Ȳ_T²) + SD_C²/(n_C·Ȳ_C²)'),
    ('eq', 'SE(lnRR) = √Var(lnRR);        95 % CI ≈ lnRR ± 1.96·SE(lnRR)'),
    ('p', 'As a sensitivity analysis, the second-order bias-corrected lnRR is computed when mean, SD and n are defensible (Lajeunesse, 2015); ordinary lnRR '
          'remains the main estimand.'),
    ('eq', 'lnRR_bc = lnRR + ½[SD_T²/(n_T·Ȳ_T²) − SD_C²/(n_C·Ȳ_C²)]'),
    ('p', 'The stress × biostimulant interaction is evaluated only in C/S/B/SB designs that are comparable in background, dose, outcome and timepoint:'),
    ('eq', 'I_S×B = ln(Ȳ_SB/Ȳ_S) − ln(Ȳ_B/Ȳ_C) = ln[(Ȳ_SB·Ȳ_C)/(Ȳ_S·Ȳ_B)]'),
    ('eq', 'Var(I_S×B) = v_SB + v_S + v_B + v_C,     v_j = SD_j²/(n_j·Ȳ_j²)   [independent arms]'),
    ('p', 'When arms share units, controls or repeated measures, the covariance is included explicitly; if it cannot be reconstructed, the dependency_cluster_id '
          'is kept and correlated effects are not treated as independent. For two biostimulants A and B, strict synergy is computed only with C/A/B/A+B at '
          'comparable dose, background and time:'),
    ('eq', 'I_AB = ln[(Ȳ_AB·Ȳ_C)/(Ȳ_A·Ȳ_B)]'),
    ('p', 'The general implemented form is a linear contrast on the log scale:'),
    ('eq', 'θ = Σⱼ cⱼ·ln(Ȳⱼ);     Var(θ) = Σⱼ cⱼ²vⱼ + 2Σᵢ<ⱼ cᵢcⱼCov[ln(Ȳᵢ),ln(Ȳⱼ)]'),
    ('p', 'When lnRR is not appropriate but the groups share a continuous scale, Hedges g is kept as a sensitivity analysis and is never mixed numerically with '
          'lnRR. For incidences or mortality/survival, measures for proportions (log-RR/log-OR) are pre-specified; ordinal severity scales do not use lnRR.'),
    ('eq', 'S_p = √{[(n_T−1)SD_T² + (n_C−1)SD_C²]/(n_T+n_C−2)};   g = J·(Ȳ_T−Ȳ_C)/S_p'),
    ('fig', f'{FIG}/FigM2_contrasts_effect_sizes.png', 'contrasts', 'Experimental arms, contrasts and effect sizes used in this work.',
     'The main target is ln(SB/S), the effect of the biostimulant in stressed plants. ln(S/C) measures how strongly the stress reduced the control (stress '
     'damage D); it is known only after the experiment and is therefore used only as a conditional meta-regression moderator, never as a predictor of the '
     'a-priori models.'),
    ('h3', '3.9.1. Contrasts without reported variance (update)'),
    ('p', 'Many publications report means without SD or SE, so the sampling variance of lnRR cannot be computed directly. Excluding these contrasts would '
          'discard most of the evidence and could bias the results if variances are omitted selectively. Following Nakagawa et al. (2023), missing variances '
          'were filled in with a transparent hierarchy: (1) the authors\' SD/SE when available; (2) otherwise the experiment\'s printed ANOVA CV % or LSD '
          '({T:uncert}); (3) otherwise the mean coefficient of variation (CV̄ = SD/mean, weighted by sample size) of all TRAIN studies that report SDs. '
          'CV̄ was 0.290 for yield and 0.275 for dry biomass; a missing n was replaced by the median n of the table (n = 4). CV̄ and the median n were '
          'estimated on TRAIN only and applied unchanged to TEST. Each contrast carries a variance_status (AUTHOR_SD_SE, STUDY_PRINTED_CV_OR_LSD_OR_N_IMPUTED, '
          'IMPUTED_MEAN_CV_NOT_AUTHOR_REPORTED). **Imputed variances are not values reported by the authors**; they are an estimate and their influence was '
          f'checked in sensitivity and simulation analyses (Sections 3.15 and 4.13–4.14). Code: `{R}/scripts/v5_01_build.py`; summary: '
          f'`{R}/results/variance_imputation_v5.csv`.'),

    ('h2', '3.10. Quality, risk of bias, outliers and quantitative synthesis'),
    ('p', 'Risk of bias is assessed by domain and not reduced to an arbitrary score: randomisation/allocation, experimental unit, pseudoreplication, baseline '
          'comparability, intervention fidelity, measurement objectivity/blinding where relevant, missing data, selective reporting, co-interventions and '
          'unit-of-analysis correctness. Categories are low, some_concerns, high or unclear. A risk judgement modifies sensitivity and interpretation; it does not '
          'automatically remove evidence.'),
    ('p', 'Extreme values are audited before any synthesis. Within comparable outcome/unit groups a robust MAD-based z is computed; |z_MAD| > 4.5 triggers a '
          'review flag, never an automatic deletion. n ≤ 0, negative SD/SE, SD ≈ SE·√n inconsistencies, impossible units, duplicate natural keys and extreme '
          'coefficients of variation are also checked. Expected biological heterogeneity is kept as signal, not treated as error by default.'),
    ('eq', 'z_MAD = 0.6745·(x − median) / MAD;      flag if |z_MAD| > 4.5'),
    ('p', '**Meta-analysis (update).** Average effects were estimated with three-level random-effects models fitted by restricted maximum likelihood (REML) '
          'in metafor (Viechtbauer, 2010; Konstantopoulos, 2011): contrasts are nested within studies, so that several contrasts from the same study do not '
          'count as independent evidence. The sampling variance–covariance matrix includes the covariance created by a **shared control** (when several '
          'treatments are compared with the same control, their lnRR are positively correlated; covariance = CV_c²/n_c). Confidence intervals of the mean use '
          'cluster-robust CR2 standard errors with small-sample t-tests (Pustejovsky & Tipton, 2018), and a 95 % prediction interval (PI) describes the range '
          'of effects expected in a new study. Heterogeneity is reported as between-study and within-study variance (τ²) and I² (Higgins & Thompson, 2002). '
          'Subgroups (stress class, du Jardin biostimulant class (du Jardin, 2015), route, system) were estimated for levels with ≥ 4 studies and tested with '
          'robust Wald tests; single-moderator meta-regressions were adjusted for multiplicity with the Holm method. Small-study effects were examined with '
          'funnel plots, Egger\'s regression (Egger et al., 1997), Begg\'s rank test (Begg & Mazumdar, 1994), a multilevel Egger test, PET-PEESE (Stanley & '
          'Doucouliagos, 2014) and trim-and-fill (Duval & Tweedie, 2000); influence was assessed by leaving out one study at a time. For interactions S×B and '
          'A×B descriptive means of study means with t-based CIs are reported; no confirmatory pooling is done with fewer than five independent studies. '
          f'Code: `{R}/scripts/v5_05_meta.R`; results: `{R}/results/meta/`.'),
    ('eq', 'w_i = 1/(v_i + τ²_REML);       θ̂_RE = Σw_i y_i / Σw_i'),
    ('eq', 'I² = max[0, (Q − (k−1))/Q] · 100%'),
    ('p', 'The **stress-damage gradient** relates the biostimulant effect ln(SB/S) to the stress damage D = ln(S/C) of the same study (study means; '
          'between-study regression with study-bootstrap CI). Because S appears in both quantities, a negative slope is partly expected by construction; the '
          'expected size of this artefact was computed and reported. For salinity, the damage expected from the Maas–Hoffman threshold model (tomato '
          'threshold 2.5 dS m⁻¹, slope 9.9 % per dS m⁻¹; Maas & Hoffman, 1977) was compared with the observed damage. '
          f'Code: `{R}/scripts/v5_06_extra.py gradient`.'),
    ('p', 'Feature completeness is reported as C_f = 100·N_reported/N_eligible together with the number of independent studies and levels. This metric '
          'describes available information; it is not a quality score and is not used as a predictor.'),

    ('h2', '3.11. Database finalisation and generation of analysis datasets'),
    ('p', 'A database is final when all entities required for each contrast are linked, targets have provenance and verification_status, n corresponds to the '
          'experimental unit, and there are no blocking integrity errors ({T:gates}). The central output is the frozen relational database with '
          'contrast_candidates and evidence_long; from it, two independent class A tables are derived for fruit yield (primary) and dry biomass (secondary), '
          'together with the interaction and S_vs_C strata ({T:marts}). The absence of one endpoint is never filled with values of the other.'),
    ('p', 'Only deterministic, reproducible transformations are applied at this stage: typing, semantic normalisation through frozen vocabularies, physically '
          'equivalent conversions, timepoint in days where possible, documented SD reconstruction, QA flags, missingness indicators and explicit aggregation of '
          'components. Statistical imputers, scaling, one-hot/frequency/target encoding and thresholds for rare categories are **not** fitted on the full '
          'corpus: they are trained inside each cross-validation fold to avoid information leakage.'),
    ('p', 'The feature policy separates ID_GROUP / PROVENANCE_ONLY / CONTEXT_ONLY / FEATURE / QUALITY_FEATURE / TARGET (`feature_policy.csv` in each freeze). '
          'DOI, title, authors, journal, source_file_id and study_id are never predictors. The exact commercial name is kept for traceability, while class, '
          'composition, origin, formulation, dose, route and timing are generalisable candidates. Post-treatment biomarkers are excluded from the primary '
          'pre-experimental model.'),
    ('p', '**Update (V5 analysis tables).** The V5 tables were built from both frozen databases with one script and identical rules, definitions, '
          f'dictionaries and units (`{R}/scripts/v5_01_build.py`): `{R}/data/train_yield.csv`, `train_dry_biomass.csv`, `test_yield.csv`, '
          '`test_dry_biomass.csv`, the interaction tables (`*_interactions.csv`) and the S_vs_C tables (`*_SvsC.csv`), with the Excel workbooks '
          f'`{R}/SynerPlant_YIELD_TRAIN_TEST_V5.xlsx` and `{R}/SynerPlant_DRY_BIOMASS_TRAIN_TEST_V5.xlsx` and the dictionary '
          f'`{R}/data/data_dictionary_V5.csv`. The selection rules were: lnRR computable; contrast type SB vs S or B vs C; no duplicates; yield fractions '
          'and non-marketable yield excluded; box-plot centres used as means excluded from the default table (kept for sensitivity); dry biomass of shoot or '
          'whole plant at the last timepoint. Overlap between TRAIN and TEST was checked on study_id, dependency_cluster_id, DOI, normalised title and '
          f'study relations (all zero; `{R}/results/overlap_train_test.csv`). The selection flow is stored in `{R}/results/build_flow_v5.csv`.'),
    ('tab', 'marts', 'Analysis tables (V5) defined by biological question.',
     ['Table', 'Population / contrast', 'Target', 'Use'],
     [['train_yield / test_yield', 'Class A; SB vs S and B vs C; fruit yield', 'lnRR', 'Primary endpoint: meta-analysis and prediction (TRAIN 831 contrasts / 76 studies; TEST 117 / 16).'],
      ['train_dry_biomass / test_dry_biomass', 'Class A; SB vs S and B vs C; shoot/whole-plant dry mass, last timepoint', 'lnRR', 'Secondary endpoint (TRAIN 1 452 / 172; TEST 378 / 31).'],
      ['*_interactions', 'C/S/B/SB and C/A/B/AB quadruples', 'I_S×B, I_AB', 'Interaction analyses (descriptive).'],
      ['*_SvsC', 'Class A; S vs C', 'lnRR_S|C', 'Stress damage D; conditional moderator only.'],
      ['contrast_candidates (freeze)', 'All computable contrasts', 'effect', 'Audit and global analyses; source of the V5 tables.']],
     [3.8, 4.4, 1.8, 5.0]),
    ('tab', 'gates', 'Mandatory gates before modelling and their status in V5.',
     ['Gate', 'PASS criterion', 'Status / action'],
     [['Relational integrity', 'Unique primary keys; valid study→experiment→arm→measurement links.', 'PASS in both freezes (acceptance_report.json).'],
      ['Extraction coverage', 'All non-X studies reviewed, including supplements.', 'PASS (TRAIN_DEV, EXTERNAL_TEST).'],
      ['Target provenance', '100 % of targets with source_file_id + location + verification.', 'PASS; unverified targets excluded.'],
      ['n and uncertainty', 'Defensible inferential n; SD/SE/CI distinguishable.', 'Missing SD imputed and flagged (Section 3.9.1).'],
      ['Contrasts', 'Positive means for lnRR; comparable arms; dependence recorded.', 'PASS; shared controls and dependency clusters recorded.'],
      ['Biological QA', 'No impossible values or blocking duplicates; outliers reviewed.', 'PASS after V5 source-verified corrections.'],
      ['Leakage', 'IDs/provenance/post-treatment biomarkers outside the features.', 'PASS; S_vs_C only as a conditional moderator.'],
      ['Reproducibility', 'CSV/Parquet + dictionary + QA + SHA-256 of the same run.', f'PASS (`{R}/MANIFEST_V5_sha256.csv`).'],
      ['External TEST', '0 TEST records inspected before MODEL_FREEZE.', 'NOT MET: TEST used in earlier versions → POST_HOC_TEST_REUSE.']],
     [3.0, 6.4, 5.6]),

    ('h2', '3.12. Predictive models, regularisation and optimisation'),
    ('p', 'Modelling was run separately from database construction, after the gates of {T:gates}. Independent pipelines were fitted for fruit yield '
          '(primary) and dry biomass (secondary); targets were never merged and one was never imputed from the other, except that the conditional meta-'
          'regression may borrow strength from both endpoints (MR2, see below). Complexity was increased step by step and accepted only when it gave stable '
          'improvements over the baselines under grouped validation ({T:complexity}).'),
    ('tab', 'complexity', 'Pre-specified protocol for increasing model complexity when internal metrics are low.',
     ['Level', 'Action when metrics are low', 'Anti-overfitting rule'],
     [['1. Data', 'Check reconciliation, target, experimental unit, missingness and coverage', 'Labels/categories are never changed according to model results'],
      ['2. Baselines', 'Compare mean, three-level mean (MR0) and Ridge', 'Complexity is justified only against the baseline'],
      ['3. Regularisation', 'Ridge (L2) with nested tuning', 'Hyper-parameters only in inner grouped CV'],
      ['4. Non-linearity', 'Random Forest; equal-weight and learned stacks', 'Outer folds stay untouched during tuning'],
      ['5. Features', 'Numeric recoding, in-fold target encoding, text components, block selection', 'All encoders and selection inside the training pipeline'],
      ['6. Diagnosis', 'Grouped learning curves, applicability domain, residual analysis', 'The temporal test is never used to decide changes'],
      ['7. Decision', 'Prefer the simplest model with stable improvement', 'If there is no robust improvement, report limited predictability']],
     [2.6, 6.4, 6.0]),
    ('p', '**Candidate models (update).** Fourteen candidates were compared ({T:candidates}). The baselines were the training mean (BASELINE_mean) and the '
          'three-level random-effects mean (MR0). Ridge regression (Hoerl & Kennard, 1970) and Random Forest (Breiman, 2001), weighted by 1/(v + τ²), were '
          'trained on two feature sets: REF, the design descriptors of the database (cultivation system, stress class and intensity, du Jardin class of the '
          'biostimulant, dose class, route, number of applications, genotype descriptors, yield definition tier and type of contrast), and V3, a numeric '
          'recoding of the free-text descriptors (microorganism genus, active ingredient, route, stress type, phenological phase, soil texture, season, '
          'geography, genotype traits) with in-fold target encoding and TF-IDF text components. Stacks combined model predictions with equal weights or with '
          'non-negative weights learned in the inner folds (Breiman, 1996). Two **categories** were kept separate: category A (a-priori prediction from design '
          'descriptors, the primary claim) and category B (conditional prediction that additionally uses the observed stress damage S_vs_C of the new study as '
          'a meta-regression moderator: MR2, a three-level meta-regression with design moderators and S_vs_C fitted on yield and biomass together). S_vs_C '
          'was never used as an ML feature, because it is an outcome of the experiment.'),
    ('tab', 'candidates', 'Candidate models compared in the nested cross-validation (V5).',
     ['Model', 'Category', 'Description'],
     [['BASELINE_mean', 'A', 'Mean lnRR of the training studies.'],
      ['MR0', 'A', 'Three-level random-effects mean (study / experiment / contrast).'],
      ['RIDGE_REF, RF_REF', 'A', 'Ridge / Random Forest on the design descriptors (REF).'],
      ['RIDGE_V3TE, RF_V3TETF', 'A', 'Ridge with numeric recoding + target encoding; RF additionally with TF-IDF text components.'],
      ['STACK_A_REF, STACK_A_V3, LSTACK_A', 'A', 'Equal-weight Ridge+RF stacks; learned stack of MR0, Ridge and RF.'],
      ['MR2mt', 'B', 'Three-level meta-regression with design moderators and S_vs_C (yield + biomass).'],
      ['STACK_B_REF, STACK_B_MR0, STACK_B_V3, LSTACK_B', 'B', 'Stacks combining MR2 with Ridge or MR0; learned stack.']],
     [5.0, 1.8, 8.2]),
    ('p', 'Hyper-parameters (Ridge α ∈ {0.1, 1, 10, 100, 1000}; Random Forest 300 trees, max_features ∈ {0.33, 0.66}, min_samples_leaf ∈ {3, 10}), '
          'imputation (median plus missing indicators), winsorisation (1st–99th percentile), scaling, one-hot encoding (levels present in ≥ 3 training '
          'studies), target and frequency encoding, text components and stack weights were all fitted exclusively inside the training folds. Exact duplicate '
          'and constant columns were detected on the training rows of each fit and removed (`results/v5_feature_duplicates_audit_*.csv`; for example '
          'h_n_applications duplicated f_n_applications and h_stress_class = NONE duplicated the B vs C indicator); 7–8 columns were removed from the REF '
          'sets and 22–24 from the V3 sets. Seeds, grids, software versions and the number of jobs are fixed in the code '
          f'(`{R}/scripts/v5_common.py`, `v5_02_cv_select.py`). The objective is not to maximise a metric by iterating on the test, but to determine '
          'whether a reproducible predictive signal exists; if complex models do not beat the baselines consistently, the correct result is to document '
          'limited predictive capacity.'),

    ('h2', '3.13. Internal validation and performance metrics'),
    ('p', 'The main validation is **nested grouped cross-validation** ({F:validation}). The minimum group is the study; because study_relations, shared '
          'controls, the same site/season or companion publications indicate wider dependence, folds were built on dependency_cluster_id (75 clusters for 76 '
          'yield studies; 171 for 172 biomass studies). No group appears in training and validation at the same time. The outer loop used 5 folds repeated '
          'with 3 random seeds (11, 22, 33); the inner loop used 3 folds by cluster inside each outer training part for hyper-parameters, encoders, stack '
          'weights and interval width (Roberts et al., 2017). Biomass contrasts and studies of classes B–E do not increase the support of the yield model.'),
    ('fig', f'{FIG}/FigM3_validation_design.png', 'validation', 'Validation design.',
     'Outer folds of dependency clusters (studies that share controls or data are kept together) give honest estimates for new studies; all tuning '
     'happens in the inner folds. The selection rule was fixed in advance, the chosen pipeline was refitted on all TRAIN data and frozen, and the test '
     'set was evaluated once.'),
    ('p', 'The regression metrics are RMSE and MAE on the lnRR scale; R² (1 − SSE/SST) is complementary and interpreted cautiously when folds contain few '
          'studies; mean bias and the coverage and mean width of the 95 % intervals are also reported. Means and standard deviations over the three seeds are '
          'given. Model comparison uses only the outer results. **Pre-specified selection rule:** within each category (A and B) and endpoint the candidate '
          'with the lowest mean outer RMSE was selected; if another candidate was within 1 % of it, the simpler one was preferred. '
          f'Code: `{R}/scripts/v5_02_cv_select.py`; results: `{R}/results/v5_cv_summary.csv`, `v5_selected_models.csv`.'),
    ('p', 'To diagnose whether low performance is due to insufficient data, grouped **learning curves** were computed: within each outer fold 20, 40, 60, '
          '80 and 100 % of the training clusters were used (three random draws). A sustained decrease of the error with more studies suggests a data-limited '
          'problem; a flat curve close to the baseline suggests limited signal in the available variables. '
          f'Code: `{R}/scripts/v5_06_extra.py learning`.'),

    ('h2', '3.14. Uncertainty, calibration and applicability domain'),
    ('p', 'Besides the point prediction, every model gives a 95 % interval. For ML models the half-width is the 95th percentile of the absolute out-of-fold '
          'residuals obtained in the inner grouped folds (a group-wise split-conformal construction; Lei et al., 2018); for meta-models it is the model-based '
          'prediction interval; for equal-weight stacks the mean of the member half-widths and for learned stacks again the inner out-of-fold residuals. '
          'Calibration is evaluated by the empirical coverage and the width of the intervals in the outer folds and in TEST.'),
    ('p', 'The **applicability domain** is evaluated with the mean distance of a contrast to its five nearest training contrasts from other clusters, in the '
          'standardised feature space of the frozen Ridge model; contrasts beyond the 95th percentile of the training distances are labelled out-of-domain. '
          'Out-of-domain is interpreted as low density of comparable evidence, not as biological invalidity. '
          f'Code: `{R}/scripts/v5_06_extra.py ad`.'),
    ('p', '**Selective prediction (additional check).** To test whether unreliable cases can be identified in advance, four abstention rules were compared: '
          'local error (mean absolute inner out-of-fold residual of the 15 nearest training contrasts), distance to the training data, disagreement between '
          'Ridge and the mean, and random abstention as a control. Thresholds were set as quantiles of the training scores inside each outer fold and models '
          'were compared on exactly the same retained contrasts with 2 000 cluster-bootstrap resamples. The primary criterion was written before computing '
          'any result (yield, local error, 80 % of contrasts predicted; advantage only if Ridge beats the mean on the retained set with CI < 0, the gain is '
          f'larger than without abstention and ≥ 50 % of studies keep a prediction). Plan: `{R}/results/selective/PLAN_selective.json`; code: '
          f'`{R}/scripts/v5_10_selective.py`.'),

    ('h2', '3.15. Robustness analyses and internal generalisation'),
    ('p', 'Robustness was explored through internal transfer diagnostics by stress family, biostimulant class, route, cultivation system and genotype. These '
          'analyses remain internal to the development corpus and are not described as external validation.'),
    ('p', 'Sensitivity analyses covered influential effects (leave-one-study-out), alternative compatible outcome definitions, variance availability, risk of '
          'bias and weighting. Sensitivity results were never used to choose retrospectively the primary definition giving the best result. **Update:** a '
          'systematic sensitivity analysis changed one data-preparation decision at a time (CV̄ for all groups, imputed CVs × 0.5 and × 1.5, missing n = 3, '
          'no shared-control covariance, one contrast per control, author-reported SDs only, known yield definitions only, no unspecified yield scope (yield) '
          'or all timepoints (biomass), box-plot centres included); within each scenario all methods were evaluated on the same rows, with the three-level '
          f'meta-analysis and nested CV (`{R}/scripts/v5_13_sensitivity.py`; `{R}/results/sensitivity/`).'),
    ('p', '**Choice between biostimulants (additional check).** Because the practical aim is to help choose a product, the out-of-fold predictions were used '
          'to test, in experiments where several arms were compared with the same control, whether the model ranks the arms in the observed order. Pairwise '
          'accuracy, a noise-aware accuracy weighted by the probability that the observed order is real, "decisive" pairs (observed difference > 1.96 SE) and '
          'the yield lost relative to the best arm (regret) were computed, study-balanced, with 2 000 study-bootstrap resamples, and compared with a random '
          f'choice and with a simple rule based on the mean effect of each du Jardin class in the training folds (`{R}/scripts/v5_12_choice.py`).'),
    ('p', '**Simulation with known truth (additional check).** To verify the procedure itself, 200 meta-analyses per scenario were simulated with the structure '
          'of the real data (60 studies, 1–2 experiments, 1–4 treatment arms per shared control, n = 3–6, study CV around 0.25, a true design moderator of '
          '0.15) under increasing between-study heterogeneity (τ = 0.1, 0.3, 0.5) and proportion of studies without SD (0–80 %), with missingness either at '
          'random or more frequent in studies with large effects. Complete-case analysis, the V5 procedure (CV̄ imputation + shared-control covariance), the '
          'same without covariance and unweighted study means were compared for bias, RMSE and CI coverage, and pooled versus moderator-based prediction for '
          f'new studies (`{R}/scripts/v5_14_simulation.py`).'),

    ('h2', '3.16. Visualisations and reproducible generation of figures'),
    ('p', 'All figures are generated by code from the same build that produces the analysis tables, exported as vector PDF/SVG and 300 dpi PNG, and '
          'accompanied by their underlying tables. Counts of screening, extraction, variance availability, provenance and model readiness are recomputed from '
          f'versioned artefacts and are never edited by hand. Figures are stored in `{FIG}` and produced by `{R}/scripts/v5_07_figures_data.py` '
          '(data and meta-analysis figures), `v5_08_figures_models.py` (models and TEST), `v5_11_fig_selective.py`, `v5_15_block_panels.py` (additional '
          'checks) and `v5_16_methods_figs.py` (methods schematics). The earlier V4 figure set '
          '(`04_analysis_history/SynerPlant_Yield_V4_HARMONIZATION/outputs/figures_TFM_A4_V4`) was fully recomputed on the V5 data and is '
          'superseded.'),

    ('h2', '3.17. MODEL_FREEZE and external validation'),
    ('p', 'Before the test tables were read, the selection rule was applied to the TRAIN cross-validation, every candidate was refitted on all TRAIN data '
          f'(inner tuning grouped by cluster) and the pipeline was frozen in `{R}/freeze/MODEL_FREEZE_V5.json` and `models_v5.joblib`, with their SHA-256 '
          'checksums (`MODEL_FREEZE_V5.sha256`). The freeze records the hashes of the TRAIN tables, selected models, hyper-parameters, stack weights, '
          'features, encoders, CV̄, interval widths and the evaluation rules. The test script verifies the checksums before predicting '
          f'(`{R}/scripts/v5_03_freeze_fit.py`, `v5_04_test.py`).'),
    ('p', 'The pre-specified test criteria were: H1 (point accuracy) — RMSE of the selected category-A model on TEST lower than that of the mean baseline, '
          'with a 95 % cluster-bootstrap CI of the difference below 0; H2 (transfer) — RMSE_TEST ≤ 1.25 × RMSE_CV; H3 (intervals) — coverage of the 95 % '
          'intervals ≥ 0.90; H4 (conditional, reported only) — the category-B model better than the category-A model. The verdict was CONFIRMED if H1–H3 '
          'passed, PARTIAL if one or two passed and NOT_CONFIRMED otherwise. TEST rows followed the same selection rules as TRAIN and used the TRAIN CV̄ for '
          'missing variances; TEST was predicted once, without tuning.'),
    ('p', '**Deviation from the original protocol.** The original plan required that no TEST publication be inspected before MODEL_FREEZE. The 2024–2026 '
          'corpus had, however, already been used to evaluate earlier versions of the models (V2 and V4). The evaluation of the V5 models is therefore '
          'reported as **POST_HOC_TEST_REUSE**: it is a frozen, one-time evaluation on independent studies, but not a first blind test, and only new data '
          'collected after this TFM could provide an independent confirmation.'),

    ('h2', '3.18. Software, versioning and reproducibility'),
    ('p', 'Document management used Google Drive/Google Sheets and reproducible inventory scripts; the relational databases are SQLite files produced by the '
          'agent systems (TRAIN_DEV: `01_agent_system_train_dev`; EXTERNAL_TEST: `02_agent_system_external_test`). '
          'Analyses were run in Python 3.12 (pandas, NumPy, SciPy, scikit-learn (Pedregosa et al., 2011), joblib, matplotlib) and R 4.5.0 with metafor 5.2.1 '
          'and clubSandwich. The analysis scripts are listed in {T:scripts}. Every build records date/time, configuration and SHA-256 fingerprints; the '
          f'complete V5 version is described by `{R}/MANIFEST_V5_sha256.csv`, so that any value of a final table or figure can be traced back to the contrast, '
          'the raw measurement and its exact location in the article or supplement. Copyrighted documents remain outside any public repository.'),
    ('p', '**Data and code availability.** The repository is organised as follows: '
          f'extraction notebooks of the deterministic document layer V4.3 ({GH}/tree/main/00_extraction_notebooks_v4_3); '
          'the multi-agent extraction and verification system for TRAIN_DEV, including agent definitions, guard hooks, the validating command-line tool, '
          f'configuration, JSON schemas and tests ({GH}/tree/main/01_agent_system_train_dev); '
          f'the same system for EXTERNAL_TEST ({GH}/tree/main/02_agent_system_external_test); '
          'the frozen exports of both databases (analysis marts, evidence_long, contrast_candidates, covariance of shared controls, QA tables and freeze '
          f'manifests with SHA-256; {GH}/tree/main/03_data_freeze); '
          f'earlier analysis stages V2 and V4 ({GH}/tree/main/04_analysis_history); '
          f'and the V5 analysis with scripts, analysis tables, frozen models, results and figures ({GH}/tree/main/05_analysis_train_expansion_v5/v5). '
          f'The complete relational databases (SQLite and Excel, TRAIN_DEV and EXTERNAL_TEST) are attached to the release {GH}/releases/tag/data-freeze-v5. '
          'Full texts, supplements and page images of the source articles are not redistributed; each value can be located in the original publication '
          'through its DOI, page and locator.'),
    ('tab', 'scripts', 'Analysis scripts of version V5 (repository folder 05_analysis_train_expansion_v5/v5/scripts).',
     ['Script', 'Purpose', 'Main outputs'],
     [['v5_01_build.py', 'Corrections, TRAIN/TEST tables, variance imputation, overlap check', 'data/*.csv|parquet, corrections_register.csv, build_flow_v5.csv'],
      ['v5_common.py / v5_02_cv_select.py', 'Feature sets, duplicate removal, nested grouped CV of 14 candidates', 'results/v5_cv_*.csv, v5_cv_oof_*.parquet'],
      ['v5_03_freeze_fit.py', 'Selection rule, refit on TRAIN, MODEL_FREEZE', 'freeze/MODEL_FREEZE_V5.json, models_v5.joblib'],
      ['v5_04_test.py', 'One-time TEST evaluation (POST_HOC_TEST_REUSE)', 'results/test/*.csv'],
      ['v5_05_meta.R', 'Three-level meta-analysis, subgroups, bias, influence, matrix, interactions', 'results/meta/*.csv'],
      ['v5_06_extra.py', 'Stress gradient, learning curves, applicability domain, permutation importance', 'results/extra/*.csv'],
      ['v5_10_selective.py', 'Selective prediction (abstention)', 'results/selective/*'],
      ['v5_12_choice.py', 'Choice between biostimulants', 'results/choice/*'],
      ['v5_13_sensitivity.py', 'Sensitivity to data-preparation decisions', 'results/sensitivity/*'],
      ['v5_14_simulation.py', 'Simulation with known truth', 'results/simulation/*'],
      ['v5_07, v5_08, v5_11, v5_15, v5_16', 'Figures', 'figures/*.png|pdf|svg'],
      ['v5_09_package.py', 'Excel workbooks, dictionary, SHA-256 manifest', 'SynerPlant_*_V5.xlsx, MANIFEST_V5_sha256.csv']],
     [4.6, 5.8, 4.6]),

    ('h2', '3.19. Reporting criteria and transparency'),
    ('p', 'The report distinguishes clearly: (i) pre-specified rules; (ii) extraction/QA decisions taken without looking at predictive performance; '
          '(iii) secondary analyses; and (iv) exploratory extensions. The curated, non-exhaustive nature of the corpus, the heterogeneity of protocols, '
          'missingness, missing and imputed variances, ambiguous experimental units, poorly supported categories and the concentration of evidence on certain '
          'products, cultivars and systems are documented. Insufficient data for a complex model are reported as a methodological result and are not '
          'corrected by retrospectively enlarging the target or relaxing independence rules.'),
    ('p', 'Predictive results are presented together with their uncertainty and applicability. A complex model is preferred only if it improves stably on the '
          'baselines in grouped validation and behaves reasonably in the robustness analyses; otherwise limited predictability is reported as an informative '
          'finding. Historical estimates of earlier versions (V2–V4 and improvement rounds 1–7) are labelled as such and are never presented as new results.'),

    ('h2', '3.20. Methodological references'),
    ('ref', '1. Page, M. J., McKenzie, J. E., Bossuyt, P. M., Boutron, I., Hoffmann, T. C., Mulrow, C. D., et al. (2021). The PRISMA 2020 statement: an updated guideline for systematic reviews. BMJ, 372, n71. https://doi.org/10.1136/bmj.n71.'),
    ('ref', '2. Rethlefsen, M. L., Kirtley, S., Waffenschmidt, S., Ayala, A. P., Moher, D., Page, M. J., Koffel, J. B., & PRISMA-S Group. (2021). PRISMA-S: an extension to the PRISMA Statement for Reporting Literature Searches in Systematic Reviews. Systematic Reviews, 10, 39. https://doi.org/10.1186/s13643-020-01542-z.'),
    ('ref', '3. Hedges, L. V., Gurevitch, J., & Curtis, P. S. (1999). The meta-analysis of response ratios in experimental ecology. Ecology, 80, 1150–1156. https://doi.org/10.1890/0012-9658(1999)080[1150:TMAORR]2.0.CO;2.'),
    ('ref', '4. Viechtbauer, W. (2010). Conducting Meta-Analyses in R with the metafor Package. Journal of Statistical Software, 36(3), 1–48. https://doi.org/10.18637/jss.v036.i03.'),
    ('ref', '5. Prokhorenkova, L., Gusev, G., Vorobev, A., Dorogush, A. V., & Gulin, A. (2018). CatBoost: unbiased boosting with categorical features. Advances in Neural Information Processing Systems, 31.'),
    ('ref', '6. Iglewicz, B., & Hoaglin, D. C. (1993). How to Detect and Handle Outliers. ASQC Quality Press.'),
    ('ref', '7. Nakagawa, S., Noble, D. W. A., Lagisz, M., Spake, R., Viechtbauer, W., & Senior, A. M. (2023). A robust and readily implementable method for the meta-analysis of response ratios with and without missing standard deviations. Ecology Letters, 26(2), 232–244. https://doi.org/10.1111/ele.14144.'),
    ('ref', '8. Lajeunesse, M. J. (2015). Bias and correction for the log response ratio in ecological meta-analysis. Ecology, 96(8), 2056–2063. https://doi.org/10.1890/14-2402.1.'),
    ('ref', '9. Konstantopoulos, S. (2011). Fixed effects and variance components estimation in three-level meta-analysis. Research Synthesis Methods, 2(1), 61–76. https://doi.org/10.1002/jrsm.35.'),
    ('ref', '10. Pustejovsky, J. E., & Tipton, E. (2018). Small-sample methods for cluster-robust variance estimation and hypothesis testing in fixed effects models. Journal of Business & Economic Statistics, 36(4), 672–683. https://doi.org/10.1080/07350015.2016.1247004.'),
    ('ref', '11. Higgins, J. P. T., & Thompson, S. G. (2002). Quantifying heterogeneity in a meta-analysis. Statistics in Medicine, 21(11), 1539–1558. https://doi.org/10.1002/sim.1186.'),
    ('ref', '12. Egger, M., Davey Smith, G., Schneider, M., & Minder, C. (1997). Bias in meta-analysis detected by a simple, graphical test. BMJ, 315, 629–634. https://doi.org/10.1136/bmj.315.7109.629.'),
    ('ref', '13. Begg, C. B., & Mazumdar, M. (1994). Operating characteristics of a rank correlation test for publication bias. Biometrics, 50(4), 1088–1101. https://doi.org/10.2307/2533446.'),
    ('ref', '14. Stanley, T. D., & Doucouliagos, H. (2014). Meta-regression approximations to reduce publication selection bias. Research Synthesis Methods, 5(1), 60–78. https://doi.org/10.1002/jrsm.1095.'),
    ('ref', '15. Duval, S., & Tweedie, R. (2000). Trim and fill: a simple funnel-plot-based method of testing and adjusting for publication bias in meta-analysis. Biometrics, 56(2), 455–463. https://doi.org/10.1111/j.0006-341X.2000.00455.x.'),
    ('ref', '16. du Jardin, P. (2015). Plant biostimulants: Definition, concept, main categories and regulation. Scientia Horticulturae, 196, 3–14. https://doi.org/10.1016/j.scienta.2015.09.021.'),
    ('ref', '17. Maas, E. V., & Hoffman, G. J. (1977). Crop salt tolerance — current assessment. Journal of the Irrigation and Drainage Division, 103(2), 115–134.'),
    ('ref', '18. Hoerl, A. E., & Kennard, R. W. (1970). Ridge regression: biased estimation for nonorthogonal problems. Technometrics, 12(1), 55–67. https://doi.org/10.1080/00401706.1970.10488634.'),
    ('ref', '19. Breiman, L. (2001). Random forests. Machine Learning, 45, 5–32. https://doi.org/10.1023/A:1010933404324.'),
    ('ref', '20. Breiman, L. (1996). Stacked regressions. Machine Learning, 24, 49–64. https://doi.org/10.1007/BF00117832.'),
    ('ref', '21. Roberts, D. R., Bahn, V., Ciuti, S., Boyce, M. S., Elith, J., Guillera-Arroita, G., et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. Ecography, 40(8), 913–929. https://doi.org/10.1111/ecog.02881.'),
    ('ref', '22. Lei, J., G\'Sell, M., Rinaldo, A., Tibshirani, R. J., & Wasserman, L. (2018). Distribution-free predictive inference for regression. Journal of the American Statistical Association, 113(523), 1094–1111. https://doi.org/10.1080/01621459.2017.1307116.'),
    ('ref', '23. Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., et al. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, 2825–2830.'),
]
