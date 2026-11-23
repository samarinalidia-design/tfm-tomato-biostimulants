# Prompt for adjudicators (full TRAIN run)

You are the ADJUDICATOR in the extraction of leaf chlorophyll content from tomato biostimulant–stress articles. Two agents (pass A and pass B) extracted each study independently; code reconciled them and listed the disagreements.

Your studies (comma-separated study_ids; numeric items are ids): {STUDIES}

For each study:
1. Read the disagreement file work/adjudication/<study_id>.json and both pass files work/outbox/A/<study_id>.json and work/outbox/B/<study_id>.json (you may read both passes and their fits), and the packet (`chl.py packet <study_id>`).
2. Resolve every item against the ORIGINAL PDF (not against either pass): re-render the relevant pages and read Methods for n, dispersion type and basis. Issues: VALUE_CONFLICT (the failed fields are listed in `checks`), ONLY_A / ONLY_B (often the same value under different arm keys or time-point labels: decide whether it is real and map it), STATUS_DIFFERS, NEW_ARMS_PROPOSED (choose ONE consistent set of new arm keys and roles, map every value to it).
3. Rules: protocol C:\Users\lenovo\Desktop\master's\TFM_GITHUB_REPO\08_chlorophyll_target\docs\EXTRACTION_PROTOCOL.md (section 7 is binding), plus these decisions:
   - n genuinely not stated → null (never guess). Basis not stated → UNSPECIFIED (assumption in notes only).
   - Figure values on which A and B agree within 5 %: use their mean. Figure values in conflict: re-digitise yourself (CHL_PASS=ADJ, fits in work/fits/ADJ/<study_id>/) and use your value. Printed table numbers are copied exactly.
   - Chlorophyll printed only as ratios between arms (no per-arm content), or only as factor-level/marginal means pooled over another factor, or only as boxplot medians pooled over a factor → NO_CHLOROPHYLL_DATA (explain in notes). Boxplot medians per arm (not pooled) may be kept with dispersion_type OTHER and a note "MEDIAN".
   - Roles: C = no stress, no biostimulant; S = stress only; B = biostimulant only; SB = both; anything that is neither (non-biostimulant agrochemicals alone, weed treatments, other crops) = OTHER. Each SB arm needs an S arm with the same stress level to be useful; code the roles exactly as the paper's factors are.
   - during_stress: true when the measurement time point lies within the stress period (for every arm measured at that time, including controls); false for pre-stress baselines and recovery after the stress ended.
4. Write the FINAL COMPLETE value set to work/outbox/ADJ/<study_id>.json in the protocol format with "pass": "ADJ": all values (agreed ones too), the final design_check (with the chosen new_arms), and in "notes" a short decision log (item → decision → reason, page). Every value needs a receipt_id of a render (receipts of A/B renders are valid) and, for figures, a fit_file.
5. Run `chl.py check work/outbox/ADJ/<study_id>.json` until it passes. Before replying, confirm one ADJ file per study in your list.

Tools: cd "C:/Users/lenovo/Desktop/master's/TFM_GITHUB_REPO/08_chlorophyll_target/scripts" ; CHL_PASS=ADJ PYTHONIOENCODING=utf-8 "C:/Users/lenovo/Desktop/master's/TFM_A399_Agent_System_v2_2_2026-10-19/SynerPlant_Yield_V2/.venv/Scripts/python.exe" -W ignore chl.py <packet|render|text|probe|grid|snap|fit|check> ...
Work dir: C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work. Your private temporary folder: work/tmp/ADJ/<first study_id of your list>/ (create it); never write elsewhere except work/fits/ADJ/<study_id>/ and work/outbox/ADJ/. Use only the registered PDFs; never Docling; do not modify A/B files, packets, tools or databases.

Reply with one line per study: study_id, final status, values, the main decisions (≤ 30 words).
