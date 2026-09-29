#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/pins.sh"
cd "$ROOT"

setup_repo() {
    local name="$1"
    local path="$2"
    local url="$3"
    local sha="$4"

    if [[ -d "$path/.git" || -f "$path/.git" ]]; then
        echo "Updating $name..."
        git -C "$path" fetch origin "$sha" --depth=1 2>/dev/null \
            || git -C "$path" fetch origin
    else
        echo "Cloning $name..."
        rm -rf "$path"
        git clone "$url" "$path"
    fi

    # Preserve rl_mjlab only when its checkpoint matches the exact current
    # overlay diff, generated overlay files, patch-script hashes, and pin.
    # Otherwise reset cleanly; install.sh reapplies the overlays immediately.
    local current=""
    current="$(git -C "$path" rev-parse HEAD 2>/dev/null || true)"
    if [[ "$name" == "unitree_rl_mjlab" &&
          "$current" == "$sha" &&
          -x "$ROOT/scripts/apply_runtime_overlays.sh" ]] &&
       bash "$ROOT/scripts/apply_runtime_overlays.sh" --checkpoint-valid >/dev/null 2>&1; then
        echo "Preserving verified Robot Web Lab runtime overlays for $name."
    else
        git -C "$path" checkout --detach -f "$sha"
        git -C "$path" reset --hard "$sha"
    fi
}

mkdir -p third_party

# Normal Git clone: initialize registered submodules first.
if [[ -d .git ]]; then
    git submodule sync --recursive
    git submodule update --init --recursive
fi

setup_repo \
    "unitree_rl_mjlab" \
    "third_party/unitree_rl_mjlab" \
    "$UNITREE_RL_MJLAB_URL" \
    "$UNITREE_RL_MJLAB_SHA"

setup_repo \
    "unitree_sdk2" \
    "third_party/unitree_sdk2" \
    "$UNITREE_SDK2_URL" \
    "$UNITREE_SDK2_SHA"

setup_repo \
    "unitree_mujoco" \
    "third_party/unitree_mujoco" \
    "$UNITREE_MUJOCO_URL" \
    "$UNITREE_MUJOCO_SHA"

setup_repo \
    "unitree_sdk2_python" \
    "third_party/unitree_sdk2_python" \
    "$UNITREE_SDK2_PYTHON_URL" \
    "$UNITREE_SDK2_PYTHON_SHA"

setup_repo \
    "cyclonedds" \
    "third_party/cyclonedds" \
    "$CYCLONEDDS_URL" \
    "$CYCLONEDDS_SHA"

echo
echo "Pinned Unitree dependencies are ready:"
echo "  unitree_rl_mjlab: $(git -C third_party/unitree_rl_mjlab rev-parse HEAD)"
echo "  unitree_sdk2:     $(git -C third_party/unitree_sdk2 rev-parse HEAD)"
echo "  unitree_mujoco:   $(git -C third_party/unitree_mujoco rev-parse HEAD)"
echo "  unitree_sdk2_python: $(git -C third_party/unitree_sdk2_python rev-parse HEAD)"
echo "  cyclonedds:          $(git -C third_party/cyclonedds rev-parse HEAD)"
