#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die(){ echo "ERROR: $*" >&2; exit 1; }
say(){ printf '\n==> %s\n' "$*"; }

[[ -f "$ROOT/.rwl-conda" ]] || die ".rwl-conda is missing. Run ./install.sh first."
# shellcheck disable=SC1091
source "$ROOT/.rwl-conda"

CONDA_BIN="${RWL_CONDA_EXE:?}"
PY_SDK_ENV_NAME="${RWL_PYTHON_SDK_ENV:-robot-web-lab-python-sdk}"
SDK_PY="$ROOT/third_party/unitree_sdk2_python"
DDS_SRC="$ROOT/third_party/cyclonedds"
DDS_BUILD="$ROOT/build/python-sdk/cyclonedds/build"
DDS_PREFIX="$ROOT/build/python-sdk/cyclonedds/install"
JOBS="${RWL_BUILD_JOBS:-$(nproc 2>/dev/null || echo 4)}"

[[ -f "$SDK_PY/setup.py" ]] || die "unitree_sdk2_python submodule is missing"
[[ -f "$DDS_SRC/CMakeLists.txt" ]] || die "cyclonedds submodule is missing"

if "$CONDA_BIN" env list | awk '{print $1}' | grep -Fxq "$PY_SDK_ENV_NAME"; then
  say "Updating Unitree SDK2 Python Conda environment: $PY_SDK_ENV_NAME"
  "$CONDA_BIN" install -n "$PY_SDK_ENV_NAME" -y python=3.11 pip
else
  say "Creating Unitree SDK2 Python Conda environment: $PY_SDK_ENV_NAME"
  "$CONDA_BIN" env create -n "$PY_SDK_ENV_NAME" -f "$ROOT/environment-python-sdk.yml" -y
fi

say "Building pinned CycloneDDS"
cmake -S "$DDS_SRC" -B "$DDS_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$DDS_PREFIX" \
  -DBUILD_TESTING=OFF \
  -DBUILD_EXAMPLES=OFF \
  -DENABLE_SSL=OFF
cmake --build "$DDS_BUILD" --target install -j "$JOBS"

say "Installing Unitree SDK2 Python"
CYCLONEDDS_HOME="$DDS_PREFIX" \
  "$CONDA_BIN" run --no-capture-output -n "$PY_SDK_ENV_NAME" \
  python -m pip install --upgrade pip setuptools wheel

CYCLONEDDS_HOME="$DDS_PREFIX" \
  "$CONDA_BIN" run --no-capture-output -n "$PY_SDK_ENV_NAME" \
  python -m pip install -e "$SDK_PY"

ENV_PREFIX="$("$CONDA_BIN" run -n "$PY_SDK_ENV_NAME" python -c 'import sys; print(sys.prefix)')"
PYTHON_BIN="$ENV_PREFIX/bin/python"

mkdir -p "$ENV_PREFIX/etc/conda/activate.d" "$ENV_PREFIX/etc/conda/deactivate.d"
cat > "$ENV_PREFIX/etc/conda/activate.d/robot-web-lab-python-sdk.sh" <<EOF
export RWL_PYTHON_SDK_ROOT="$SDK_PY"
export CYCLONEDDS_HOME="$DDS_PREFIX"
export _RWL_OLD_LD_LIBRARY_PATH="\${LD_LIBRARY_PATH-}"
export LD_LIBRARY_PATH="$DDS_PREFIX/lib:\${LD_LIBRARY_PATH-}"
EOF

cat > "$ENV_PREFIX/etc/conda/deactivate.d/robot-web-lab-python-sdk.sh" <<'EOF'
export LD_LIBRARY_PATH="${_RWL_OLD_LD_LIBRARY_PATH-}"
unset _RWL_OLD_LD_LIBRARY_PATH
unset RWL_PYTHON_SDK_ROOT
unset CYCLONEDDS_HOME
EOF

printf '%s\n%s\n' "$PYTHON_BIN" "$DDS_PREFIX" > "$ROOT/.rwl-python-sdk-runtime"

say "Verifying Unitree SDK2 Python"
CYCLONEDDS_HOME="$DDS_PREFIX" \
LD_LIBRARY_PATH="$DDS_PREFIX/lib:${LD_LIBRARY_PATH:-}" \
  "$PYTHON_BIN" -c 'import unitree_sdk2py, cyclonedds; print("Unitree SDK2 Python ready")'
