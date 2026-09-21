#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash -n scripts/pins.sh scripts/init_git_repo.sh scripts/bootstrap_submodules.sh scripts/verify_submodules.sh

grep -q 'path = third_party/unitree_rl_mjlab' .gitmodules
grep -q 'path = third_party/unitree_sdk2' .gitmodules
grep -q 'path = third_party/unitree_mujoco' .gitmodules
grep -q '1425b15f73bd4095f0df53709d7c389c3eb9e790' scripts/pins.sh
grep -q 'c753829882fba461ed07ba25aaabee0a25d83663' scripts/pins.sh
grep -q '1eb6642e3f3fdfb7fb13a9794fd6a2dd93ea0e7d' scripts/pins.sh

echo "PASS: scaffold structure and scripts"
