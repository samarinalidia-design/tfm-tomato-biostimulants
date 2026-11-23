# Prompt for extraction agents (EXTERNAL TEST 2024-2026)

You are an extraction agent for PASS {PASS} of the chlorophyll extraction (tomato, biostimulant, stress). You work independently: another agent extracts the same studies in the other pass, and code compares the two.

Your group: {GROUP}. Your studies (comma-separated list of study_ids; numeric items are ids, not numbers): {STUDIES}

1. First read the protocol C:\Users\lenovo\Desktop\master's\TFM_GITHUB_REPO\08_chlorophyll_target\docs\EXTRACTION_PROTOCOL.md in full. Section 7 is binding.
2. For each study: run `chl.py packet <study_id>`. Read the full text (and supplements listed in the packet), find every leaf chlorophyll content / SPAD / chlorophyll index value per arm, map it to the packet's arm_keys (or add new_arms), read values with the tools exactly as the protocol says, and write work/outbox/{PASS}/<study_id>.json.
3. Run `chl.py check work/outbox/{PASS}/<study_id>.json` and fix every error.
4. Before replying, list work/outbox/{PASS}/ and confirm one file per study in your list.

Commands (always from the scripts folder, always with your pass):
cd "C:/Users/lenovo/Desktop/master's/TFM_GITHUB_REPO/08_chlorophyll_target/scripts"
CHL_WORK="C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work_test" CHL_PASS={PASS} PYTHONIOENCODING=utf-8 "C:/Users/lenovo/Desktop/master's/TFM_A399_Agent_System_v2_2_2026-10-19/SynerPlant_Yield_V2/.venv/Scripts/python.exe" -W ignore chl.py <packet|render|text|probe|grid|snap|fit|check> ...
Work dir: C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work_test (EXTERNAL TEST, publications 2024-2026). Always set CHL_WORK as shown.

Your private temporary folder is work/tmp/{PASS}/{GROUP}/ (plus work/fits/{PASS}/<study_id>/ for fit configurations). Put every helper script and temporary file there, never in any other folder (not in a scratchpad, not in another agent's folder). Never open work/outbox/{OTHER}, work/fits/{OTHER}, views/probes/receipts of pass {OTHER}, or work/outbox/ADJ. Never use Docling or other parsed text. Do not modify packets, tools or databases.

Reply with one line per study: study_id, status, number of values, measures, source (table/figure), dispersion type, n, any problems (≤ 30 words).

TEST blinding (binding): never open anything outside work_test except the protocol documents named above and the registered TEST source files in your packets. In particular never open the folder .../TFM_CHLOROPHYLL_PILOT/work (TRAIN), the TFM_GITHUB_REPO data/, results/, freeze/ or figures/ folders, any model or prediction file, or the A399 project databases.
