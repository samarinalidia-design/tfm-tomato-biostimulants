#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$#" -lt 1 ]; then
  echo 'Usage: bash install_macos_linux.sh "/absolute/path/TFM_CORPUS_NORMALIZED" ["/absolute/path/workbook.xlsx"]'
  exit 2
fi
if [ "$#" -ge 2 ]; then
  python3 tools/bootstrap.py --corpus "$1" --workbook "$2"
else
  python3 tools/bootstrap.py --corpus "$1"
fi
echo 'Next: source .venv/bin/activate ; claude ; /tfm-finalize'
