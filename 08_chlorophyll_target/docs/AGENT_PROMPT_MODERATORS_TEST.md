# Prompt for moderator extraction (chlorophyll studies whose design was not in the A399 yield/biomass sets)

You extract the pre-treatment design descriptors ("moderators") of tomato biostimulant–stress studies, in exactly the vocabulary of the A399 database, so that the same feature code can be applied to them as to the yield and biomass studies.

Your studies (comma-separated study_ids; numeric items are ids): {STUDIES}

For each study:
1. Run `chl.py packet <study_id>` (files, A399 design if any). The arms to describe are the arms of the FINAL chlorophyll extraction: read `work/outbox/ADJ/<study_id>.json` if it exists, otherwise `work/outbox/A/<study_id>.json`; use their `design_check.new_arms` plus the packet's A399 arms, with exactly those experiment_key / arm_key values.
2. Read the full text (Methods above all) with `chl.py render` / `chl.py text` and extract every feature of the vocabulary C:\Users\lenovo\Desktop\master's\TFM_GITHUB_REPO\08_chlorophyll_target\docs\MODERATOR_VOCABULARY.md that the paper reports. Follow the examples' style. Do not infer values that are not printed (no latitude from a city name unless printed; country may be taken from the affiliation only if the experiment site is not stated — then say so in `note`).
3. Write work/moderators/<study_id>.json:
   {"study_id": "...", "rows": [{"experiment_key": "E1" | null, "arm_key": "E1.SB" | null, "feature": "dose", "value": "100", "unit": "mg/L",
     "page": 3, "verbatim": "<exact sentence fragment from the PDF that states it, 5-40 words>", "note": ""}]}
   `verbatim` must be copied exactly from the page text (code checks that it occurs in the PDF).
4. Check: valid JSON; every arm_key exists among the arms of step 1; every feature is in the vocabulary.

Tools: cd "C:/Users/lenovo/Desktop/master's/TFM_GITHUB_REPO/08_chlorophyll_target/scripts" ; CHL_WORK="C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work_test" CHL_PASS=MOD PYTHONIOENCODING=utf-8 "C:/Users/lenovo/Desktop/master's/TFM_A399_Agent_System_v2_2_2026-10-19/SynerPlant_Yield_V2/.venv/Scripts/python.exe" -W ignore chl.py <packet|render|text> ...
Work dir: C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work_test (EXTERNAL TEST); every work/... path means work_test/.... Temporary files only in work/tmp/MOD/<first study_id>/. Use only the registered PDFs; never Docling; do not modify other files.

Reply with one line per study: study_id, number of rows, features covered, problems (≤ 25 words).

TEST blinding (binding): never open anything outside work_test except the vocabulary/protocol documents named above and the registered TEST source files of your packets (no TRAIN work folder, no TFM_GITHUB_REPO data/results/freeze/figures, no models, no A399 databases).
