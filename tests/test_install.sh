#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for file in install.sh Robot-Web-Lab requirements.txt environment.yml environment-python-sdk.yml scripts/fetch_three.sh scripts/fetch_three.py; do
  [[ -f "$file" ]] || { echo "missing $file" >&2; exit 1; }
done

bash -n install.sh
bash -n Robot-Web-Lab
bash -n scripts/fetch_three.sh
bash -n scripts/install_python_sdk.sh

grep -q 'bootstrap_submodules.sh' install.sh
grep -q 'conda' install.sh
grep -q 'install_python_sdk.sh' install.sh
grep -q 'RWL_SKIP_PYTHON_SDK' install.sh
grep -q 'CYCLONEDDS_HOME' scripts/install_python_sdk.sh
grep -q 'robot-web-lab-python-sdk' install.sh
grep -q 'CYCLONEDDS_HOME' install.sh
grep -q 'unitree_sdk2_python' install.sh
grep -q ' run --no-capture-output -n ' Robot-Web-Lab
! grep -q '\.venv' install.sh
! grep -q '\.venv' Robot-Web-Lab
! grep -q 'native_build.py' install.sh
grep -q 'three.module.js' scripts/fetch_three.py
grep -q 'three.core.js' scripts/fetch_three.py
grep -q 'STLLoader.js' scripts/fetch_three.py
grep -q 'uvicorn' Robot-Web-Lab
grep -q 'fastapi' requirements.txt
grep -q 'uvicorn' requirements.txt
grep -q 'RWL_HOST:-127.0.0.1' Robot-Web-Lab

echo "PASS: Conda install and launcher contract"

bash -n scripts/apply_runtime_overlays.sh
grep -q 'apply_runtime_overlays.sh' install.sh
grep -q 'Preserving checkpointed Robot Web Lab overlays' scripts/bootstrap_submodules.sh
