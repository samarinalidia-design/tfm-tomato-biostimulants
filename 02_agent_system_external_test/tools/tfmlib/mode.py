"""Dataset mode of this project: the EXTERNAL_TEST corpus (publications first online 2024+).

The same extraction/QA protocol as the A399 TRAIN_DEV database (TFM 3.1) is reused; only the
scope, the temporal window, the dataset role and the TEST-specific integrity gates differ.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ELIGIBLE_TEST = "ELIGIBLE_TEST_WINDOW"
INELIGIBLE_TEST = ("INELIGIBLE_PRE2024", "INELIGIBLE_AFTER_WINDOW")


def role(cfg) -> str:
    return str(cfg.get("scope.dataset_role", "TRAIN_DEV"))


def is_test(cfg) -> bool:
    return role(cfg) == "EXTERNAL_TEST"


def window(cfg):
    return str(cfg.get("scope.temporal_window_start", "2024-01-01")), str(cfg.get("scope.temporal_window_end", "2099-12-31"))


def date_in_window(cfg, date: str) -> bool:
    if not date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        return False
    lo, hi = window(cfg)
    return lo <= str(date) <= hi


def label(cfg) -> str:
    return str(cfg.get("scope.label", "A399"))


def norm_doi(v) -> str:
    s = str(v or "").strip().lower()
    s = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", s)
    return s.rstrip(".")


def norm_title(v) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())


def train_dev_identity(cfg):
    """DOIs/titles of every TRAIN_DEV publication (written by the bootstrap from the A399 freeze)."""
    p = cfg.root / str(cfg.get("scope.train_dev_identity", "manifests/train_dev_identity.csv"))
    if not p.is_file():
        return None
    with p.open(encoding="utf-8-sig", newline="") as f:
        recs = list(csv.DictReader(f))
    return {norm_doi(r.get("doi")) for r in recs} - {""}, {norm_title(r.get("title")) for r in recs} - {""}


def model_freeze(cfg):
    """(path, payload) of the ML MODEL_FREEZE.json required before TEST extraction, or (path, None)."""
    raw = cfg.get("test_protocol.model_freeze_path")
    if not raw:
        return None, None
    p = Path(str(raw))
    if not p.is_file():
        return p, None
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return p, None
