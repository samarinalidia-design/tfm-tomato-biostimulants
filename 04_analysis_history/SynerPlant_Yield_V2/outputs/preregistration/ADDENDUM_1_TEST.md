# Addendum 1 to the TEST pre-registration — 2026-11-18T09:37:55+00:00

TEST status: **not opened**.

1. **TEST builder** `s14_build_test_dataset.py`: imports the frozen s03/x01 unchanged. On a TRAIN copy it reproduces PRIMARY_EXPANDED byte-identically (404 contrasts / 69 studies) and all 224 quadruples.
2. **TEST rules**: year window < 2024 excluded; TRAIN study-specific decisions do not apply; unit-unresolved TEST contrasts are excluded and reported.
3. **Confirmatory TRAIN meta-analysis (R metafor + CR2)**: V2 primary +72 % (CR2 95 % CI 0.354–0.734, 31 studies); agreement with Python < 2·10⁻⁸.
4. **Secondary TEST meta-analyses** (`s17_test_meta.py`, after s13 only): TEST pooled effect; TEST − TRAIN difference; TRAIN + TEST synthesis. They never change the primary verdicts.
5. **Chronology**: the TEST extraction started under the V1 freeze; V2 never saw TEST data.

## SHA-256
- `src/s14_build_test_dataset.py` 0ac606a1779c0f6fbe33cf39cb3d76fbdab9d4a3a2026bd59783cb338293b7dd
- `src/s16_meta_R.py` 171379ac5e8d7e66e534b84b4caf9d3ab4f193ba4a24f08bbf1fea4ea9f1bfa6
- `src/meta_confirmatory.R` a4700affabff4926880858d9be92cbd35a4f7af3b58501466e904a785b94a9f1
- `src/meta_test.R` 40ce863b24c4e22d3fe023f78878100e795d3416efd224e3bb96c16149ff41db
- `src/s17_test_meta.py` 36719d1f0998c6cc3e845cc9896ffeeb323ba63c81a40ed362ab4e77969f286c
- `src/s12b_addendum.py` d3672bfa6a778a41a0ce56a2f69968a8fb36ab9f5f89da0e23a2973928f8130f
- `outputs/meta/R_confirmatory.json` 3731119e1cb2fd0bcadcef0b0eae2668e35fbe1c9a55f2bddec2204a349da92a
- `outputs/test_inputs_validation.json` 8f7572ec5d0e383a42fd2302bff7ba26cc5266b6a01581c97a91743ce3a5060e
- `outputs/preregistration/PREREG_TEST_V2.json` 174e2052e69c5624456971f787c8cd9fab6ecd8626089d8505e9bede19c86401