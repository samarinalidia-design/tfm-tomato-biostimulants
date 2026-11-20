#!/usr/bin/env python3
"""Enforce the project command surface and JSON-only result writes."""
import json,os,re,shlex,sys
from pathlib import Path
try:data=json.load(sys.stdin)
except Exception:sys.exit(2)
name=data.get("tool_name","");arg=data.get("tool_input") or {};root=Path(os.environ.get("CLAUDE_PROJECT_DIR",Path.cwd())).resolve()
reason=None
if os.environ.get("TFM_MAINTENANCE")=="1":
    if name in ("Write","Edit"):
        p=Path(arg.get("file_path") or "").expanduser()
        if not p.is_absolute():p=root/p
        p=p.resolve()
        ok=[root/"tools",root/"config",root/"schema",root/"docs",root/".claude"/"agents",root/"CLAUDE.md"]
        if any(p==x or p.is_relative_to(x) for x in ok):sys.exit(0)
    elif name=="Bash":
        c=(arg.get("command") or "").strip()
        if c.startswith(("python tools/migrate_author_20261105.py","python -m pytest")) and not re.search(r"[;\n|&><`]|\$\(",c):sys.exit(0)
if name=="Bash":
    command=arg.get("command") or ""
    if re.search(r"[;\n|&><`]|\$\(",command):reason="one literal tfm.py command at a time"
    else:
        try:parts=shlex.split(command)
        except ValueError:parts=[]
        allowed={"pilot-select","pilot-finish","replicate-summary","verify-build","claim","packet","submit","release","reconcile","source-index","source-view","figure-fit","figure-grid","figure-snap","figure-probe","validate","contrasts","close","close-all","qa-seed","status","gates","study","sql","checkpoint","review-export","human-audit-export","export","dedup-seed"}
        if len(parts)<3 or parts[0] not in ("python","python3") or parts[1]!="tools/tfm.py" or parts[2] not in allowed:reason="only approved tfm.py commands; human decisions and installation run outside agents"
        elif "--force" in parts:reason="verification cannot be bypassed"
        elif parts[2]=="export" and "--draft" not in parts:
            # Final export itself has the complete fail-closed release checks.
            pass
elif name in ("Write","Edit","NotebookEdit"):
    path=Path(arg.get("file_path") or arg.get("notebook_path") or "").expanduser()
    if not path.is_absolute():path=root/path
    path=path.resolve()
    if not path.is_relative_to(root/"work"/"outbox") or path.suffix.lower()!=".json":reason="agents write JSON results only in work/outbox; the CLI manages all database/source artifacts"
elif name in ("Read","Grep","Glob"):
    outbox=(root/"work"/"outbox").resolve()
    p=Path((arg.get("file_path") if name=="Read" else arg.get("path")) or root).expanduser()
    if not p.is_absolute():p=root/p
    p=p.resolve()
    if p.is_relative_to(outbox) or (name!="Read" and outbox.is_relative_to(p)):reason="work/outbox is write-only for agents (blinding); search a specific directory such as work/packets"
    elif any(x in str(p).replace("\\","/").lower() for x in ("synerplant_local_ml","tfm_a399_agent_system")):
        reason="EXTERNAL_TEST blinding: the ML package (model, predictions, TRAIN_DEV results) and the A399 project are not readable here"
if reason:
    print("TFM guard: "+reason,file=sys.stderr);sys.exit(2)
sys.exit(0)
