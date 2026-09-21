#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .rwl-conda ]]; then
  # shellcheck disable=SC1091
  source .rwl-conda
  exec "$RWL_CONDA_EXE" run --no-capture-output -n "$RWL_CONDA_ENV" python scripts/fetch_three.py
fi
exec python3 scripts/fetch_three.py
