"""Unit tests for the V6 text parsers; cases are real values from db_moderators. Run: python test_v6_parsers.py"""
import math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import v6_corrections as v

CASES = [
    (v.parse_duration_days, ('28', "days (printed as 4 weeks)"), 28),
    (v.parse_duration_days, ('14', "d (printed as 'two-week')"), 14),
    (v.parse_duration_days, ('12', 'weeks'), 84),
    (v.parse_duration_days, ('20', 'weeks (as printed; not converted)'), 140),
    (v.parse_duration_days, ('8 weeks', 'weeks (as printed; not converted to days)'), 56),
    (v.parse_duration_days, ('24 h', None), None),
    (v.parse_duration_days, ('6', 'h'), None),
    (v.parse_duration_days, ('14 (first period) + 7 (second period)', 'days'), None),
    (v.parse_duration_days, ('30 and 15', 'days'), None),
    (v.parse_duration_days, ('8 weeks after an unstated reference event; no numeric duration assigned', None), None),
    (v.parse_duration_days, ('-7', 'days'), -7),
    (v.parse_density, ('36765', 'plants ha-1 (printed value, not converted)'), 3.6765),
    (v.parse_density, ('3 seedlings per 1 x 2 m plot, plots separated by 1 m (no per-m2 value printed)', None), None),
    (v.parse_density, ('60 cm between rows; 45 cm within row (spacing as printed; density not printed)', 'cm'), 1 / 0.27),
    (v.parse_density, ('3.3', 'plants m-2'), 3.3),
    (v.parse_latitude, ("40 deg 24' N", None), 40.4),
    (v.parse_latitude, ('37°59′10″ N', None), 37.986111),
    (v.parse_latitude, ('31.2', 'decimal degrees N'), 31.2),
    (v.parse_photoperiod, ('16-8 (light-dark, as printed)', 'h'), 16),
    (v.parse_photoperiod, ('8h/16h (light/dark cycle as printed)', 'h'), 8),
    (v.parse_photoperiod, ('12-14', 'light hours/day'), 13),
    (v.parse_pot_volume, ('8 kg pot; mass only, litres not stated, not converted', 'kg'), None),
    (v.parse_pot_volume, ('6-inch pot (as printed; litre volume not printed, not converted)', None), None),
    (v.parse_pot_volume, ('12', 'L'), 12),
    (lambda a, b: v.parse_number(a), ('25 ± 5', None), 25),
    (lambda a, b: v.parse_number(a), ('20-25 (single greenhouse range; no day/night split stated)', None), 22.5),
    (lambda a, b: v.parse_number(a), ('70%-90% (day/night)', None), 80),
    (lambda a, b: v.parse_number(a), ('20; 25; 30; 35', None), None),
]
AGE = [('E1_4WK_DAT14', 28, 'AFTER_TRANSPLANT'), ('TP_1MAT', None, 'END_OF_EXPERIMENT_NO_DAYS'),
       ('E1.H6WAS', 42, 'AFTER_SOWING'), ('T15DAT', 15, 'AFTER_TRANSPLANT'), ('E1.T_END_12DAS', 12, 'AFTER_SOWING'),
       ('T8W', 56, 'REFERENCE_NOT_STATED'), ('E1.D7', 7, 'REFERENCE_NOT_STATED')]
N_FERT = [("100% NP = N 112.5 kg/ha as urea + P2O5 50 kg/ha", 112.5), ('NPK 120 kg N ha-1, 60 P', 120.0),
          ('300 kg N per feddan', 300 / 0.42), ('half-strength Hoagland', None)]

fail = 0
for fn, args, want in CASES:
    got = fn(*args)[0]
    ok = (got is None and want is None) or (got is not None and want is not None and math.isclose(got, want, rel_tol=1e-4))
    fail += not ok
    print('OK ' if ok else 'BAD', args, '->', got, '(want', want, ')')
for key, days, ref in AGE:
    got = v.plant_age(key)
    ok = got[1] == ref and ((got[0] is None and days is None) or (got[0] is not None and days is not None and math.isclose(got[0], days)))
    fail += not ok
    print('OK ' if ok else 'BAD', key, '->', got)
for txt, want in N_FERT:
    got = v.parse_n_kg_ha(txt)[0]
    ok = (got is None and want is None) or (got is not None and want is not None and math.isclose(got, want, rel_tol=1e-4))
    fail += not ok
    print('OK ' if ok else 'BAD', txt, '->', got)
print('FAILED' if fail else 'ALL PASSED', fail)
sys.exit(1 if fail else 0)
