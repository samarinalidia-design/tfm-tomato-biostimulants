import json,shlex,sys
try:data=json.load(sys.stdin)
except Exception:sys.exit(2)
if data.get("tool_name")=="Bash":
    try:p=shlex.split((data.get("tool_input") or {}).get("command") or "")
    except ValueError:sys.exit(2)
    if len(p)<3 or p[2] in ("sql","study","packet","review-export","human-audit-export","export"):
        print("Independent verifier cannot inspect prior database values or another task packet",file=sys.stderr);sys.exit(2)
sys.exit(0)
