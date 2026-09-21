#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/pins.sh"
cd "$ROOT"

fail=0
check_one() {
  local name="$1" path="$2" expected="$3"
  if [[ ! -d "$path/.git" && ! -f "$path/.git" ]]; then
    echo "FAIL  $name is not initialized: $path"
    fail=1
    return
  fi
  local actual
  actual="$(git -C "$path" rev-parse HEAD)"
  if [[ "$actual" == "$expected" ]]; then
    echo "PASS  $name @ $actual"
  else
    echo "FAIL  $name"
    echo "      expected: $expected"
    echo "      actual:   $actual"
    fail=1
  fi
}

check_one "unitree_rl_mjlab" third_party/unitree_rl_mjlab "$UNITREE_RL_MJLAB_SHA"
check_one "unitree_sdk2" third_party/unitree_sdk2 "$UNITREE_SDK2_SHA"
check_one "unitree_mujoco" third_party/unitree_mujoco "$UNITREE_MUJOCO_SHA"

exit "$fail"
