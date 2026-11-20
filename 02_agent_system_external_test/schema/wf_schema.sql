-- =====================================================================
-- TFM agent system — workflow (wf_*) and analysis (an_*) layer
-- SQLite >= 3.35. Core tables (studies, experiments, arms, measurements,
-- ...) are imported 1:1 from the working workbook by `tfm.py import-xlsx`
-- and are NEVER edited in place by agents. Everything agents produce lands
-- in wf_* tables; only verified values are promoted to an_* tables.
-- =====================================================================
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wf_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- One row per agent submission (accepted or rejected) and per code run.
CREATE TABLE IF NOT EXISTS wf_runs (
  run_id          TEXT PRIMARY KEY,
  task_id         TEXT,
  agent           TEXT NOT NULL,
  model_alias     TEXT,              -- from .claude/agents/<agent>.md frontmatter
  model_id        TEXT,              -- self-reported by the agent (exact model id)
  prompt_sha      TEXT,              -- sha256[:12] of the agent definition file
  schema_version  TEXT,
  code_version    TEXT,
  started_at      TEXT,
  finished_at     TEXT,
  status          TEXT NOT NULL,     -- ACCEPTED | REJECTED | CODE
  output_sha256   TEXT,
  n_items         INTEGER,
  message         TEXT
);

-- Study-level state machine
CREATE TABLE IF NOT EXISTS wf_study_status (
  study_id        TEXT PRIMARY KEY,
  state           TEXT NOT NULL DEFAULT 'NEW',
     -- NEW, TRIAGED, SCOPE_REVIEW, STRUCTURED, EXTRACTING, ADJUDICATION,
     -- VERIFIED, CLOSED, NO_TARGET_PENDING, NO_TARGET_CONFIRMED,
     -- EXCLUDED_SCOPE, BLOCKED_HUMAN
  priority        INTEGER NOT NULL DEFAULT 3,   -- 0 = highest
  priority_reason TEXT,
  yield_status    TEXT DEFAULT 'UNKNOWN',       -- UNKNOWN, PRESENT, ABSENT, UNCLEAR
  biomass_status  TEXT DEFAULT 'UNKNOWN',
  scope_status    TEXT DEFAULT 'UNCHECKED',     -- UNCHECKED, OK, FLAGGED, EXCLUDED
  locked          INTEGER NOT NULL DEFAULT 0,
  closed_at       TEXT,
  notes           TEXT,
  updated_at      TEXT
);

-- Work queue (one row per unit of agent work)
CREATE TABLE IF NOT EXISTS wf_tasks (
  task_id         TEXT PRIMARY KEY,
  study_id        TEXT NOT NULL,
  task_type       TEXT NOT NULL,
     -- TRIAGE, TRIAGE_2ND, SCOPE, DESIGN, EXTRACT_A, EXTRACT_B, FIGURE_A,
     -- FIGURE_B, ADJUDICATE, MODERATORS, ROB, DEDUP, AUDIT
  agent           TEXT NOT NULL,
  scope_ref       TEXT NOT NULL DEFAULT '',   -- slot_id / cluster id / batch id
  status          TEXT NOT NULL DEFAULT 'READY',
     -- READY, LEASED, DONE, FAILED, CANCELLED
  priority        INTEGER NOT NULL DEFAULT 3,
  lease_owner     TEXT,
  lease_expires   TEXT,
  attempts        INTEGER NOT NULL DEFAULT 0,
  last_error      TEXT,
  created_at      TEXT,
  updated_at      TEXT,
  UNIQUE (study_id, task_type, scope_ref)
);
CREATE INDEX IF NOT EXISTS ix_tasks_queue ON wf_tasks(status, agent, priority, created_at);

-- Triage result per study and pass (P1 = first, P2 = independent second triage)
CREATE TABLE IF NOT EXISTS wf_triage (
  study_id          TEXT NOT NULL,
  pass              TEXT NOT NULL,
  run_id            TEXT NOT NULL,
  fruit_yield       TEXT,      -- PRESENT | ABSENT | UNCLEAR
  dry_biomass       TEXT,
  yield_components  TEXT,
  scope_flag        TEXT,
  scope_reason      TEXT,
  n_experiments     INTEGER,
  design_summary    TEXT,
  negative_evidence TEXT,      -- JSON
  payload           TEXT,      -- full JSON as submitted
  created_at        TEXT,
  PRIMARY KEY (study_id, pass)
);

-- Where targets are expected (closure = every slot VERIFIED or NOT_EXTRACTABLE)
CREATE TABLE IF NOT EXISTS wf_target_slots (
  slot_id               TEXT PRIMARY KEY,
  study_id              TEXT NOT NULL,
  endpoint              TEXT NOT NULL,
  source_kind           TEXT NOT NULL,   -- TABLE, TEXT, FIGURE, SUPP_TABLE, SUPP_DATASET
  source_file_id        TEXT,
  locator_label         TEXT,
  page                  INTEGER,
  figure_item_id        TEXT,
  expected_n_values     INTEGER,
  has_dispersion        TEXT,
  description           TEXT,
  route                 TEXT,            -- EXTRACT (A/B) | FIGURE (FA/FB) | SKIP_DUPLICATE_OF_TABLE | TWIN_VALIDATION
  status                TEXT NOT NULL DEFAULT 'OPEN',
     -- OPEN, EXTRACTED, VERIFIED, VERIFIED_PARTIAL, NOT_EXTRACTABLE
  not_extractable_reason TEXT,
  created_run_id        TEXT,
  updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS ix_slots_study ON wf_target_slots(study_id);

-- Canonical design map per study (from DESIGN agent)
CREATE TABLE IF NOT EXISTS wf_design_experiments (
  study_id        TEXT NOT NULL,
  experiment_key  TEXT NOT NULL,
  experiment_id   TEXT,          -- existing core experiments.experiment_id if matched
  description     TEXT,
  system          TEXT,
  run_id          TEXT,
  allocation      TEXT DEFAULT 'UNKNOWN',
  factorial_verified INTEGER DEFAULT 0,
  PRIMARY KEY (study_id, experiment_key)
);
CREATE TABLE IF NOT EXISTS wf_design_arms (
  study_id        TEXT NOT NULL,
  arm_key         TEXT NOT NULL,
  experiment_key  TEXT NOT NULL,
  arm_id          TEXT,          -- existing core arms.arm_id if matched
  label_in_source TEXT,
  stress_code     TEXT NOT NULL, -- 'NONE' or a code (same code = same stress level)
  stress_desc     TEXT,
  bio_code        TEXT NOT NULL, -- 'NONE' or a code (same code = same product+dose+timing)
  bio_desc        TEXT,
  n_bio_components INTEGER,
  genotype        TEXT,
  season          TEXT,
  site            TEXT,
  role            TEXT,          -- C | S | B | SB (derived by code)
  run_id          TEXT,
  component_codes TEXT DEFAULT '[]',
  background_key TEXT DEFAULT '',
  PRIMARY KEY (study_id, arm_key)
);
CREATE TABLE IF NOT EXISTS wf_design_timepoints (
  study_id        TEXT NOT NULL,
  timepoint_key   TEXT NOT NULL,
  experiment_key  TEXT,
  label           TEXT,
  days            REAL,
  kind            TEXT,          -- DAS, DAT, DAYS_AFTER_STRESS, HARVEST_CUMULATIVE, HARVEST_EVENT, OTHER
  is_terminal     INTEGER,
  run_id          TEXT,
  PRIMARY KEY (study_id, timepoint_key)
);
CREATE TABLE IF NOT EXISTS wf_core_patches (    -- proposed corrections to core tables (never auto-applied)
  patch_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  study_id        TEXT,
  table_name      TEXT,
  row_id          TEXT,
  field           TEXT,
  current_value   TEXT,
  proposed_value  TEXT,
  reason          TEXT,
  locator         TEXT,
  status          TEXT NOT NULL DEFAULT 'PROPOSED',  -- PROPOSED, ACCEPTED, REJECTED
  run_id          TEXT,
  created_at      TEXT
);

-- Every proposed numeric value (passes A, B, FA, FB, ADJ, HUMAN, LEGACY)
CREATE TABLE IF NOT EXISTS wf_values (
  value_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            TEXT NOT NULL,
  task_id           TEXT,
  pass              TEXT NOT NULL,
  study_id          TEXT NOT NULL,
  slot_id           TEXT,
  record_key        TEXT NOT NULL,
  arm_key           TEXT NOT NULL,
  endpoint          TEXT NOT NULL,
  yield_scope       TEXT,
  mass_basis        TEXT,
  denominator       TEXT,
  harvest_window    TEXT,
  organ_scope       TEXT,
  timepoint_key     TEXT NOT NULL,
  mean              REAL,
  dispersion_type   TEXT,
  dispersion_value  REAL,
  dispersion_type_reported TEXT,
  dispersion_basis TEXT,
  error_bar_status TEXT,
  error_bar_bounds_json TEXT,
  error_bar_relative_uncertainty REAL,
  n                 REAL,
  n_unit            TEXT,
  n_source          TEXT,
  unit_raw          TEXT,
  unit_norm         TEXT,
  mean_norm         REAL,
  disp_norm         REAL,
  sig_letters       TEXT,
  source_kind       TEXT,
  source_file_id    TEXT,
  page              INTEGER,
  locator           TEXT,
  verbatim          TEXT,
  figure_item_id    TEXT,
  calib_id          TEXT,
  axis_range        REAL,
  source_check      TEXT,      -- PASS | FAIL | UNAVAILABLE | FIGURE
  outcome_context_json TEXT,
  context_key       TEXT,
  ci_json           TEXT,
  receipt_id        TEXT,
  source_cell       TEXT,
  confidence        TEXT,
  notes             TEXT,
  created_at        TEXT
);
CREATE INDEX IF NOT EXISTS ix_values_key ON wf_values(study_id, record_key, pass);

-- Figure calibration (code fits the axis from >=3 ticks; values are computed, never typed)
CREATE TABLE IF NOT EXISTS wf_fig_calibrations (
  calib_id        TEXT PRIMARY KEY,
  run_id          TEXT,
  pass            TEXT,
  study_id        TEXT,
  figure_item_id  TEXT,
  panel           TEXT,
  image_path      TEXT,
  image_sha256    TEXT,
  coord_space     TEXT,          -- image_px | pdf_pt
  value_axis      TEXT,          -- y | x
  scale           TEXT,          -- linear | log10
  ticks_json      TEXT,
  a               REAL,
  b               REAL,
  r2              REAL,
  max_resid_frac  REAL,
  axis_range      REAL,
  status          TEXT           -- OK | WARN_TWO_TICKS | FAIL
);
CREATE TABLE IF NOT EXISTS wf_fig_points (
  point_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  calib_id        TEXT,
  run_id          TEXT,
  pass            TEXT,
  study_id        TEXT,
  arm_key         TEXT,
  timepoint_key   TEXT,
  px_mean         REAL,
  px_err_hi       REAL,
  px_err_lo       REAL,
  value_mean      REAL,
  value_err       REAL,
  err_type        TEXT,
  value_id        INTEGER
);

-- A-vs-B comparison per record_key
CREATE TABLE IF NOT EXISTS wf_reconciliation (
  rec_id            INTEGER PRIMARY KEY AUTOINCREMENT,
  study_id          TEXT NOT NULL,
  record_key        TEXT NOT NULL,
  family            TEXT NOT NULL,      -- TEXT_TABLE | FIGURE
  value_id_a        INTEGER,
  value_id_b        INTEGER,
  outcome           TEXT NOT NULL,      -- AGREE | CONFLICT | ONLY_A | ONLY_B
  fields_conflict   TEXT,               -- JSON list
  status            TEXT NOT NULL,      -- RESOLVED | OPEN | ESCALATED (waiting for a human decision)
  resolved_value_id INTEGER,
  resolved_by       TEXT,               -- AUTO | ADJUDICATOR | HUMAN
  created_at        TEXT,
  updated_at        TEXT,
  UNIQUE (study_id, record_key, family)
);

-- What each pass declared for each slot (completeness disagreements are caught here)
CREATE TABLE IF NOT EXISTS wf_slot_pass (
  slot_id     TEXT NOT NULL,
  pass        TEXT NOT NULL,     -- A, B, FA, FB
  status      TEXT NOT NULL,     -- EXTRACTED | NOT_EXTRACTABLE
  reason      TEXT,
  n_values    INTEGER,
  run_id      TEXT,
  created_at  TEXT,
  PRIMARY KEY (slot_id, pass)
);

-- Verified layer: only values that passed double extraction / adjudication / human check
CREATE TABLE IF NOT EXISTS an_target_values (
  tv_id             INTEGER PRIMARY KEY AUTOINCREMENT,
  dispersion_provenance_json TEXT,
  n_source          TEXT,
  study_id          TEXT NOT NULL,
  record_key        TEXT NOT NULL,
  arm_key           TEXT NOT NULL,
  experiment_key    TEXT,
  experiment_id     TEXT,
  arm_id            TEXT,
  role              TEXT,
  stress_code       TEXT,
  bio_code          TEXT,
  genotype          TEXT,
  season            TEXT,
  site              TEXT,
  endpoint          TEXT NOT NULL,
  yield_scope       TEXT,
  mass_basis        TEXT,
  denominator       TEXT,
  harvest_window    TEXT,
  organ_scope       TEXT,
  timepoint_key     TEXT,
  timepoint_days    REAL,
  is_terminal       INTEGER,
  mean              REAL,
  dispersion_type   TEXT,
  dispersion_value  REAL,
  dispersion_type_reported TEXT,
  dispersion_basis TEXT,
  error_bar_status TEXT,
  error_bar_bounds_json TEXT,
  error_bar_relative_uncertainty REAL,
  sd                REAL,
  n                 REAL,
  n_unit            TEXT,
  unit_raw          TEXT,
  unit_norm         TEXT,
  mean_norm         REAL,
  sd_norm           REAL,
  source_kind       TEXT,
  source_file_id    TEXT,
  page              INTEGER,
  locator           TEXT,
  verbatim          TEXT,
  figure_item_id    TEXT,
  verification      TEXT NOT NULL,   -- DOUBLE_AGREE | ADJUDICATED | HUMAN_VERIFIED
  outcome_context_json TEXT,
  context_key       TEXT,
  ci_json           TEXT,
  receipt_id        TEXT,
  source_cell       TEXT,
  basis_value_ids   TEXT,            -- JSON list of wf_values ids
  created_at        TEXT,
  updated_at        TEXT,
  UNIQUE(study_id, record_key)
);

CREATE TABLE IF NOT EXISTS an_contrasts (
  contrast_id        TEXT PRIMARY KEY,
  study_id           TEXT NOT NULL,
  experiment_key     TEXT,
  endpoint           TEXT NOT NULL,
  contrast_type      TEXT NOT NULL,     -- SB_vs_S | S_vs_C | B_vs_C | SxB | AxB | B_MAIN_EFFECT
  signature          TEXT,              -- endpoint attributes + timepoint (compatibility key)
  arm_key_t          TEXT,
  arm_key_c          TEXT,
  tv_ids             TEXT,              -- JSON
  stress_code        TEXT,
  bio_code           TEXT,
  mean_t             REAL, sd_t REAL, n_t REAL,
  mean_c             REAL, sd_c REAL, n_c REAL,
  effect             REAL,              -- lnRR or interaction on log scale
  var_effect         REAL,
  effect_bc          REAL,              -- bias-corrected lnRR (sensitivity)
  effect_metric      TEXT,
  estimand_id        TEXT,
  favorable_direction TEXT,
  pct_effect         REAL,
  var_available      INTEGER,
  shared_control_id  TEXT,
  dependency_cluster_id TEXT,
  min_verification   TEXT,
  any_figure_source  INTEGER,
  flags              TEXT,
  created_at         TEXT
);

-- Validation issues (rule engine output)
CREATE TABLE IF NOT EXISTS wf_validation (
  issue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id     TEXT NOT NULL,
  severity    TEXT NOT NULL,      -- BLOCKING | WARN | INFO
  study_id    TEXT,
  entity      TEXT,
  entity_id   TEXT,
  message     TEXT,
  status      TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN | RESOLVED | WAIVED
  run_id      TEXT,
  created_at  TEXT,
  resolved_at TEXT,
  resolution  TEXT
);
CREATE INDEX IF NOT EXISTS ix_validation ON wf_validation(study_id, status, severity);

-- Human review queue (exported/imported as CSV)
CREATE TABLE IF NOT EXISTS wf_review (
  review_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  study_id      TEXT,
  kind          TEXT,      -- SCOPE, DUPLICATE, CONFLICT, FIGURE_FAIL, TRIAGE_DISAGREE, PATCH, OTHER
  ref           TEXT,
  question      TEXT,
  options       TEXT,
  evidence      TEXT,
  priority      INTEGER DEFAULT 2,
  status        TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN | DECIDED
  decision      TEXT,
  decision_note TEXT,
  decided_by    TEXT,
  decided_at    TEXT,
  created_at    TEXT,
  UNIQUE (kind, ref)
);

CREATE TABLE IF NOT EXISTS wf_scope (
  study_id       TEXT NOT NULL,
  run_id         TEXT,
  proposed_class TEXT,     -- A | C | X | ...
  reason         TEXT,
  evidence       TEXT,
  status         TEXT NOT NULL DEFAULT 'PROPOSED',   -- PROPOSED | CONFIRMED | REJECTED
  created_at     TEXT,
  PRIMARY KEY (study_id, run_id)
);

CREATE TABLE IF NOT EXISTS wf_relations (
  rel_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  study_a      TEXT NOT NULL,
  study_b      TEXT NOT NULL,
  relation     TEXT NOT NULL,   -- DUPLICATE_DATA | PREPRINT_OF | COMPANION_SHARED_EXPERIMENT | SHARED_CONTROLS | SAME_LAB_INDEPENDENT | UNRELATED
  evidence     TEXT,
  confidence   TEXT,
  status       TEXT NOT NULL DEFAULT 'PROPOSED',  -- PROPOSED | CONFIRMED | REJECTED
  run_id       TEXT,
  created_at   TEXT,
  UNIQUE (study_a, study_b, relation)
);

CREATE TABLE IF NOT EXISTS wf_moderators (
  mod_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  study_id      TEXT NOT NULL,
  experiment_key TEXT,
  arm_key       TEXT,
  verification  TEXT DEFAULT 'UNVERIFIED',
  availability TEXT DEFAULT 'UNKNOWN',
  receipt_id TEXT,
  source_file_id TEXT,
  feature       TEXT NOT NULL,
  value         TEXT,
  unit          TEXT,
  locator       TEXT,
  verbatim      TEXT,
  run_id        TEXT,
  created_at    TEXT
);

CREATE TABLE IF NOT EXISTS wf_rob (
  study_id       TEXT NOT NULL,
  experiment_key TEXT NOT NULL DEFAULT '',
  domain         TEXT NOT NULL,
  judgement      TEXT NOT NULL,   -- low | some_concerns | high | unclear
  support        TEXT,
  locator        TEXT,
  run_id         TEXT,
  created_at     TEXT,
  PRIMARY KEY (study_id, experiment_key, domain)
);

CREATE TABLE IF NOT EXISTS wf_gold (
  gold_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  study_id        TEXT NOT NULL,
  arm_key         TEXT,
  endpoint        TEXT,
  timepoint_key   TEXT,
  yield_scope     TEXT, mass_basis TEXT, denominator TEXT, harvest_window TEXT, organ_scope TEXT,
  mean            REAL,
  dispersion_type TEXT,
  dispersion_value REAL,
  n               REAL,
  unit_raw        TEXT,
  source_kind     TEXT,
  locator         TEXT,
  entered_by      TEXT,
  entered_at      TEXT
);

CREATE TABLE IF NOT EXISTS wf_audit (
  audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  tv_id        INTEGER,
  run_id       TEXT,
  verdict      TEXT,        -- CORRECT | INCORRECT | UNSURE
  field_errors TEXT,        -- JSON list
  corrected    TEXT,        -- JSON
  notes        TEXT,
  created_at   TEXT
);

CREATE TABLE IF NOT EXISTS wf_registry (       -- optional: yield feasibility registry import
  study_id           TEXT PRIMARY KEY,
  evidence_tier      TEXT,
  eligibility_status TEXT,
  priority           TEXT,
  payload            TEXT
);

CREATE TABLE IF NOT EXISTS wf_legacy_figure (  -- figure_numeric_data.json v1.x (UNVERIFIED hints only)
  legacy_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  json_path        TEXT,
  schema_version   TEXT,
  study_id         TEXT,
  source_file_id   TEXT,
  figure_file      TEXT,
  figure_label     TEXT,
  panel            TEXT,
  group_label      TEXT,
  outcome          TEXT,
  outcome_role     TEXT,      -- PRIMARY_YIELD | SECONDARY_DRY_BIOMASS | AUXILIARY | UNKNOWN
  value            REAL,
  unit             TEXT,
  error_bar_type   TEXT,
  sd               REAL,
  se               REAL,
  n                REAL,
  timepoint        TEXT,
  has_calibration  INTEGER,
  has_px           INTEGER,
  recomputed_value REAL,
  method           TEXT,
  verification     TEXT,
  imported_at      TEXT
);

-- Append-only audit trail of state changes and promotions
CREATE TABLE IF NOT EXISTS wf_changelog (
  change_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT,
  run_id      TEXT,
  entity      TEXT,
  entity_id   TEXT,
  action      TEXT,
  detail      TEXT
);

-- ---------------------------------------------------------------- views
CREATE VIEW IF NOT EXISTS v_progress AS
SELECT state, COUNT(*) AS n_studies,
       SUM(priority = 0) AS p0, SUM(priority = 1) AS p1, SUM(priority >= 2) AS p2plus
FROM wf_study_status GROUP BY state;

CREATE VIEW IF NOT EXISTS v_task_queue AS
SELECT agent, task_type, status, COUNT(*) AS n
FROM wf_tasks GROUP BY agent, task_type, status;

CREATE VIEW IF NOT EXISTS v_slot_progress AS
SELECT endpoint, source_kind, status, COUNT(*) AS n_slots,
       SUM(COALESCE(expected_n_values,0)) AS expected_values
FROM wf_target_slots GROUP BY endpoint, source_kind, status;

CREATE VIEW IF NOT EXISTS v_open_blocking AS
SELECT * FROM wf_validation WHERE status = 'OPEN' AND severity = 'BLOCKING';

-- v2 verification of the original source and the quality of untrusted Docling output
CREATE TABLE IF NOT EXISTS wf_sources (
 source_file_id TEXT PRIMARY KEY, study_id TEXT NOT NULL, role TEXT, file_name TEXT,
 path TEXT, sha256 TEXT, status TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS wf_source_receipts (
 receipt_id TEXT PRIMARY KEY, study_id TEXT, source_file_id TEXT, source_sha256 TEXT,
 page INTEGER, sheet TEXT, cell_range TEXT, payload TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS wf_source_audit (
 study_id TEXT, source_file_id TEXT, disposition TEXT, receipts TEXT,
 docling_findings TEXT, relevance TEXT, run_id TEXT, updated_at TEXT,
 PRIMARY KEY(study_id,source_file_id)
);
CREATE TABLE IF NOT EXISTS wf_asset_inventory (
 study_id TEXT, asset_key TEXT, source_file_id TEXT, locator TEXT, relevance TEXT,
 disposition TEXT, reason TEXT, run_id TEXT, PRIMARY KEY(study_id,asset_key)
);
CREATE TABLE IF NOT EXISTS wf_contrast_audit (
 contrast_id TEXT PRIMARY KEY, snapshot_hash TEXT, verdict TEXT, reviewer TEXT,
 notes TEXT, checked_at TEXT, item_hash TEXT
);
CREATE TABLE IF NOT EXISTS wf_qa_reviews (
 issue_id INTEGER PRIMARY KEY, decision TEXT, evidence TEXT, run_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS wf_dry_basis (
 study_id TEXT, tv_record_key TEXT, basis TEXT, method TEXT, source_file_id TEXT,
 receipt_id TEXT, evidence TEXT, run_id TEXT, created_at TEXT,
 PRIMARY KEY(study_id,tv_record_key)
);

CREATE TABLE IF NOT EXISTS an_covariance (
 contrast_a TEXT, contrast_b TEXT, covariance REAL, method TEXT, shared_tv_ids TEXT,
 PRIMARY KEY(contrast_a,contrast_b)
);
CREATE TABLE IF NOT EXISTS wf_temporal_review (
 study_id TEXT PRIMARY KEY, eligibility TEXT, source_file_id TEXT, receipt_id TEXT,
 first_online_date TEXT, evidence TEXT, run_id TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS wf_inventory_corrections (
 slot_id TEXT, pass TEXT, old_count INTEGER, new_count INTEGER, receipt_id TEXT,
 reason TEXT, run_id TEXT, PRIMARY KEY(slot_id,pass)
);

CREATE TABLE IF NOT EXISTS wf_moderator_passes (
 study_id TEXT, pass TEXT, payload TEXT, run_id TEXT, PRIMARY KEY(study_id,pass)
);
