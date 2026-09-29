#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash -n scripts/pins.sh scripts/init_git_repo.sh scripts/bootstrap_submodules.sh scripts/verify_submodules.sh

grep -q 'path = third_party/unitree_rl_mjlab' .gitmodules
grep -q 'path = third_party/unitree_sdk2' .gitmodules
grep -q 'path = third_party/unitree_mujoco' .gitmodules
grep -q 'path = third_party/unitree_sdk2_python' .gitmodules
grep -q 'path = third_party/cyclonedds' .gitmodules
grep -q '1425b15f73bd4095f0df53709d7c389c3eb9e790' scripts/pins.sh
grep -q 'c753829882fba461ed07ba25aaabee0a25d83663' scripts/pins.sh
grep -q '1eb6642e3f3fdfb7fb13a9794fd6a2dd93ea0e7d' scripts/pins.sh

echo "PASS: scaffold structure and scripts"

grep -q '814556d15970dd2ecf1c9984e845ca02ab07e206' scripts/pins.sh
grep -q '5041f3560c088c99e5088b2b8520b69169621196' scripts/pins.sh
grep -q 'third_party/unitree_sdk2_python' scripts/bootstrap_submodules.sh
grep -q 'third_party/cyclonedds' scripts/bootstrap_submodules.sh
