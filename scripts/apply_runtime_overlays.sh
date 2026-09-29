#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RL="$ROOT/third_party/unitree_rl_mjlab"
STATE_DIR="$ROOT/.rwl-checkpoints"
STATE_FILE="$STATE_DIR/runtime-overlays.state"
MODE="${1:-}"

PATCH_SCRIPTS=(
  scripts/apply_rl_mjlab_compat_patch.py
  scripts/apply_g1_patch.py
  scripts/apply_g1_23dof_mimic_patch.py
  scripts/apply_web_hl_patch.py
  scripts/apply_web_state_patch.py
  scripts/pins.sh
)

OVERLAY_CREATED_FILES=(
  simulate/src/keyboard_input.h
  simulate/src/rwl_headless_main.cc
)

die(){ echo "ERROR: $*" >&2; exit 1; }

[[ -d "$RL/.git" || -f "$RL/.git" ]] || die "unitree_rl_mjlab checkout is missing"
mkdir -p "$STATE_DIR"

for rel in "${PATCH_SCRIPTS[@]}"; do
  [[ -f "$ROOT/$rel" ]] || die "missing runtime overlay source: $rel"
done

source_key() {
  {
    printf 'rwl-runtime-overlay-schema-v5\n'
    for rel in "${PATCH_SCRIPTS[@]}"; do
      sha256sum "$ROOT/$rel"
    done
    git -C "$RL" rev-parse HEAD
  } | sha256sum | awk '{print $1}'
}

overlay_hash() {
  {
    git -C "$RL" diff --binary -- .
    for rel in "${OVERLAY_CREATED_FILES[@]}"; do
      if [[ -f "$RL/$rel" ]]; then
        printf 'FILE %s\n' "$rel"
        sha256sum "$RL/$rel"
      else
        printf 'MISSING %s\n' "$rel"
      fi
    done
  } | sha256sum | awk '{print $1}'
}

read_state_value() {
  local key="$1"
  [[ -f "$STATE_FILE" ]] || return 1
  sed -n "s/^${key}=//p" "$STATE_FILE" | head -n1
}

checkpoint_valid() {
  [[ -f "$STATE_FILE" ]] || return 1

  local saved_head saved_source saved_overlay
  saved_head="$(read_state_value head || true)"
  saved_source="$(read_state_value source || true)"
  saved_overlay="$(read_state_value overlay || true)"

  [[ -n "$saved_head" && -n "$saved_source" && -n "$saved_overlay" ]] || return 1
  [[ "$saved_head" == "$(git -C "$RL" rev-parse HEAD)" ]] || return 1
  [[ "$saved_source" == "$(source_key)" ]] || return 1
  [[ "$saved_overlay" == "$(overlay_hash)" ]] || return 1
}

if [[ "$MODE" == "--checkpoint-valid" ]]; then
  checkpoint_valid
  exit $?
fi

if [[ "$MODE" != "--force" ]] && checkpoint_valid; then
  echo "Robot Web Lab runtime overlays: verified checkpoint OK; no reapply needed."
  exit 0
fi

echo "Robot Web Lab runtime overlays: applying/repairing..."
python3 "$ROOT/scripts/apply_rl_mjlab_compat_patch.py" "$RL"
python3 "$ROOT/scripts/apply_g1_patch.py" "$RL"
python3 "$ROOT/scripts/apply_g1_23dof_mimic_patch.py" "$RL"
python3 "$ROOT/scripts/apply_web_hl_patch.py" "$RL"
python3 "$ROOT/scripts/apply_web_state_patch.py" "$RL"
python3 "$ROOT/scripts/validate_runtime_overlays.py" "$ROOT" "$RL"

head="$(git -C "$RL" rev-parse HEAD)"
src="$(source_key)"
ovl="$(overlay_hash)"

tmp="$STATE_FILE.tmp"
{
  printf 'head=%s\n' "$head"
  printf 'source=%s\n' "$src"
  printf 'overlay=%s\n' "$ovl"
} > "$tmp"
mv "$tmp" "$STATE_FILE"

echo "Robot Web Lab runtime overlays: applied and checkpointed."
