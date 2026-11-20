# PREREG V4 - post-hoc TEST re-use (2026-11-18T16:51:28+00:00)

The TEST was already evaluated once (V2, 2026-11-18 11:03 UTC) and its V2 results (group-MAE 0.415, bias -0.32, single coverage 0.847) were known when the V4 idea was formed. V4 was selected on TRAIN cross-validation only, and no V4 code has read TEST values, but this evaluation is NOT an independent confirmation. Report it as a second look at a known TEST.

**A (new):** lnRR 0.4306 (+53.8 %), q single 0.8060, q simultaneous 1.2534
**B (V3.1 median):** lnRR 0.2847, q single 0.9341, q simultaneous 1.3184

## Criteria
- **H1_primary_interval**: interval score single A < B AND coverage single A >= 0.85
- **H2_simultaneous**: coverage simultaneous A >= 0.85
- **H3_bias**: |bias A| < |bias B|
- **H4_accuracy_noninferiority**: group-MAE A <= 0.587 (V2 transport threshold) AND group-MAE A - B <= 0.05
- **verdict**: SUPPORTED if H1 and H2 and H4; PARTIAL if H1 or H3 holds; otherwise NOT_SUPPORTED. With 12 TEST studies the bootstrap CIs are reported, not used as pass criteria.

TEST file SHA-256: `b703ff3095100d6d82a256fc91460f40abb6fb1c0ddb7c796aa3cb60b092dba5`
19 files hashed.