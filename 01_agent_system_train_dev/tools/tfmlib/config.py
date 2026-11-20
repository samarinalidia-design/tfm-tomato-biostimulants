from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class Config:
    """Pipeline, path and column-map configuration (all under config/)."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else ROOT
        self.pipeline = _load_yaml(self.root / "config" / "pipeline.yaml")
        paths_file = self.root / "config" / "paths.yaml"
        self.paths_file_exists = paths_file.exists()
        self.paths = _load_yaml(paths_file) if paths_file.exists() else {}
        self.column_map = _load_yaml(self.root / "config" / "column_map.yaml")

    # ---------------------------------------------------------------- paths
    def p(self, key: str) -> Optional[Path]:
        v = self.paths.get(key)
        if not v:
            return None
        return Path(os.path.expanduser(str(v)))

    @property
    def db_path(self) -> Path:
        rel = self.pipeline.get("db_path", "db/tfm_classA.sqlite")
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    @property
    def work_dir(self) -> Path:
        return self.root / self.pipeline.get("work_dir", "work")

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.pipeline
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def agent_for(self, task_type: str) -> str:
        return self.get(f"agents.{task_type}", "tfm-" + task_type.lower())

    def endpoint_spec(self, endpoint: str) -> Dict[str, Any]:
        return (self.pipeline.get("endpoints") or {}).get(endpoint, {}) or {}

    def all_endpoints(self) -> List[str]:
        return list((self.pipeline.get("endpoints") or {}).keys())

    def agent_file(self, agent: str) -> Path:
        return self.root / ".claude" / "agents" / f"{agent}.md"


def execution_contract_hash(cfg):
    import hashlib
    h=hashlib.sha256()
    files=[cfg.root/"CLAUDE.md",cfg.root/"config/pipeline.yaml",cfg.root/"config/column_map.yaml"]
    if (cfg.root/"docs/TFM_source_snapshot.txt").exists():files.append(cfg.root/"docs/TFM_source_snapshot.txt")
    for directory,pattern in [("tools","*.py"),("schema","*"),(".claude","*.md"),(".claude","*.json")]:
        files.extend(p for p in (cfg.root/directory).rglob(pattern) if p.is_file() and "__pycache__" not in p.parts and p.name!="settings.local.json")
    for p in sorted(set(files)):
        h.update(str(p.relative_to(cfg.root)).encode());h.update(b"\0");h.update(p.read_bytes());h.update(b"\0")
    return h.hexdigest()
