#!/usr/bin/env bash
set -Eeuo pipefail
trap 'rc=$?; echo "ERROR: install.sh failed at line ${LINENO}: ${BASH_COMMAND}" >&2; exit $rc' ERR
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say(){ printf '\n==> %s\n' "$*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }

wait_for_apt() {
  if ! command -v apt-get >/dev/null 2>&1; then return 0; fi
  local waited=0
  while sudo fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if (( waited >= 300 )); then die "Timed out waiting for Ubuntu package manager lock."; fi
    printf 'Waiting for Ubuntu package manager... %ss\r' "$waited"
    sleep 2; waited=$((waited+2))
  done
  if (( waited > 0 )); then echo; fi
  return 0
}

install_native_dependencies() {
  [[ "${RWL_SKIP_SYSTEM_DEPS:-0}" == "1" ]] && { say "Skipping native Ubuntu dependencies (RWL_SKIP_SYSTEM_DEPS=1)"; return; }
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "WARNING: apt-get not found. Install CMake/C++/MuJoCo build dependencies manually before building a robot." >&2
    return
  fi
  say "Installing native build dependencies (no robot is built yet)"
  wait_for_apt
  sudo apt-get update
  wait_for_apt
  sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y \
    build-essential cmake git pkg-config psmisc curl wget \
    libyaml-cpp-dev libboost-all-dev libeigen3-dev libspdlog-dev libfmt-dev \
    libglfw3-dev libxinerama-dev libxcursor-dev libxi-dev libgl1-mesa-dev zlib1g-dev
}

ENV_NAME="${RWL_CONDA_ENV:-robot-web-lab}"
PY_SDK_ENV_NAME="${RWL_PYTHON_SDK_ENV:-robot-web-lab-python-sdk}"
CONDA_BIN="${CONDA_EXE:-}"

find_conda() {
  if [[ -n "$CONDA_BIN" && -x "$CONDA_BIN" ]]; then return 0; fi
  if command -v conda >/dev/null 2>&1; then
    CONDA_BIN="$(command -v conda)"
    return 0
  fi
  local candidate
  for candidate in \
    "$HOME/miniconda3/bin/conda" \
    "$HOME/anaconda3/bin/conda" \
    "$HOME/miniforge3/bin/conda" \
    "$HOME/mambaforge/bin/conda" \
    "$HOME/.robot-web-lab/miniconda3/bin/conda"; do
    if [[ -x "$candidate" ]]; then
      CONDA_BIN="$candidate"
      return 0
    fi
  done
  return 1
}

install_miniconda() {
  [[ "$(uname -s)" == "Linux" ]] || die "Automatic Miniconda setup currently supports Linux only. Install Conda manually, then rerun install.sh."
  local arch url installer prefix
  case "$(uname -m)" in
    x86_64|amd64) arch="x86_64" ;;
    aarch64|arm64) arch="aarch64" ;;
    *) die "Unsupported architecture for automatic Miniconda install: $(uname -m)" ;;
  esac
  prefix="$HOME/.robot-web-lab/miniconda3"
  url="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${arch}.sh"
  installer="$(mktemp --suffix=.sh)"
  trap 'rm -f "$installer"' RETURN
  say "Downloading Miniconda"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "$url" -o "$installer"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$installer" "$url"
  else
    die "curl or wget is required to download Miniconda."
  fi
  say "Installing Miniconda locally at $prefix"
  bash "$installer" -b -p "$prefix"
  CONDA_BIN="$prefix/bin/conda"
}


install_python_sdk_environment() {
  [[ "${RWL_SKIP_PYTHON_SDK:-0}" == "1" ]] && { say "Skipping Unitree SDK2 Python environment"; return; }

  local sdk_py="$ROOT/third_party/unitree_sdk2_python"
  local dds_src="$ROOT/third_party/cyclonedds"
  local dds_build="$ROOT/build/python-sdk/cyclonedds/build"
  local dds_prefix="$ROOT/build/python-sdk/cyclonedds/install"
  local jobs="${RWL_BUILD_JOBS:-$(nproc 2>/dev/null || echo 4)}"

  [[ -f "$sdk_py/setup.py" ]] || die "Missing third_party/unitree_sdk2_python"
  [[ -f "$dds_src/CMakeLists.txt" ]] || die "Missing third_party/cyclonedds"

  if "$CONDA_BIN" env list | awk '{print $1}' | grep -Fxq "$PY_SDK_ENV_NAME"; then
    say "Updating Unitree Python SDK Conda environment: $PY_SDK_ENV_NAME"
    "$CONDA_BIN" install -n "$PY_SDK_ENV_NAME" -y python=3.11 pip
  else
    say "Creating Unitree Python SDK Conda environment: $PY_SDK_ENV_NAME"
    "$CONDA_BIN" env create -n "$PY_SDK_ENV_NAME" -f environment-python-sdk.yml -y
  fi

  say "Building pinned CycloneDDS"
  cmake -S "$dds_src" -B "$dds_build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$dds_prefix" \
    -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF -DENABLE_SSL=OFF
  cmake --build "$dds_build" --target install -j "$jobs"

  say "Installing Unitree SDK2 Python"
  CYCLONEDDS_HOME="$dds_prefix" "$CONDA_BIN" run --no-capture-output -n "$PY_SDK_ENV_NAME" \
    python -m pip install --upgrade pip setuptools wheel
  CYCLONEDDS_HOME="$dds_prefix" "$CONDA_BIN" run --no-capture-output -n "$PY_SDK_ENV_NAME" \
    python -m pip install -e "$sdk_py"

  local env_prefix
  env_prefix="$("$CONDA_BIN" run -n "$PY_SDK_ENV_NAME" python -c 'import sys; print(sys.prefix)')"
  mkdir -p "$env_prefix/etc/conda/activate.d" "$env_prefix/etc/conda/deactivate.d"

  cat > "$env_prefix/etc/conda/activate.d/robot-web-lab-python-sdk.sh" <<EOF
export RWL_PYTHON_SDK_ROOT="$sdk_py"
export CYCLONEDDS_HOME="$dds_prefix"
export _RWL_OLD_LD_LIBRARY_PATH="\${LD_LIBRARY_PATH-}"
export LD_LIBRARY_PATH="$dds_prefix/lib:\${LD_LIBRARY_PATH-}"
EOF

  cat > "$env_prefix/etc/conda/deactivate.d/robot-web-lab-python-sdk.sh" <<'EOF'
export LD_LIBRARY_PATH="${_RWL_OLD_LD_LIBRARY_PATH-}"
unset _RWL_OLD_LD_LIBRARY_PATH
unset RWL_PYTHON_SDK_ROOT
unset CYCLONEDDS_HOME
EOF

  printf 'RWL_CONDA_EXE=%q\nRWL_PYTHON_SDK_ENV=%q\nCYCLONEDDS_HOME=%q\n' \
    "$CONDA_BIN" "$PY_SDK_ENV_NAME" "$dds_prefix" > "$ROOT/.rwl-python-sdk-conda"

  CYCLONEDDS_HOME="$dds_prefix" LD_LIBRARY_PATH="$dds_prefix/lib:${LD_LIBRARY_PATH:-}" \
    "$CONDA_BIN" run --no-capture-output -n "$PY_SDK_ENV_NAME" \
    python -c 'import unitree_sdk2py, cyclonedds; print("Unitree SDK2 Python ready")'
}

say "Robot Web Lab setup"

if ! find_conda; then
  if [[ "${RWL_AUTO_INSTALL_CONDA:-}" == "1" ]]; then
    install_miniconda
  elif [[ -t 0 ]]; then
    printf 'Conda was not found. Install Miniconda locally for Robot Web Lab? [Y/n] '
    read -r answer
    case "${answer:-Y}" in
      y|Y|yes|YES) install_miniconda ;;
      *) die "Conda is required. Install Miniconda/Anaconda/Miniforge and rerun install.sh." ;;
    esac
  else
    die "Conda is required. Install Conda first, or rerun with RWL_AUTO_INSTALL_CONDA=1."
  fi
fi

[[ -x "$CONDA_BIN" ]] || die "Conda executable not usable: $CONDA_BIN"
say "Using Conda: $CONDA_BIN"

if "$CONDA_BIN" env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  say "Updating existing Conda environment: $ENV_NAME"
  "$CONDA_BIN" install -n "$ENV_NAME" -y python=3.11 pip
else
  say "Creating Conda environment: $ENV_NAME"
  "$CONDA_BIN" env create -n "$ENV_NAME" -f environment.yml -y
fi

say "Installing Robot Web Lab Python dependencies into Conda environment"
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install --upgrade pip wheel
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install -r requirements.txt

# Save the exact Conda executable/environment before any frontend/native setup.
printf 'RWL_CONDA_EXE=%q\nRWL_CONDA_ENV=%q\n' "$CONDA_BIN" "$ENV_NAME" > .rwl-conda

if [[ "${RWL_SKIP_THREE:-0}" != "1" ]]; then
  say "Installing local Three.js browser dependency"
  "$CONDA_BIN" run --no-capture-output -n "$ENV_NAME" python scripts/fetch_three.py
else
  say "Skipping Three.js download because RWL_SKIP_THREE=1"
fi

if [[ "${RWL_SKIP_SUBMODULES:-0}" != "1" ]]; then
  command -v git >/dev/null 2>&1 || die "git is required to fetch pinned Unitree dependencies."
  say "Fetching pinned Unitree dependencies"
  # Run through bash so source archives/ZIPs do not depend on the executable bit
  # being preserved by the extraction tool. bootstrap_submodules.sh supports
  # both a normal Git clone and a source tree without .git metadata.
  bash "$ROOT/scripts/bootstrap_submodules.sh"
  say "Checking Robot Web Lab runtime overlays"
  bash "$ROOT/scripts/apply_runtime_overlays.sh"
else
  say "Skipping Unitree dependencies because RWL_SKIP_SUBMODULES=1"
fi

# Native build tools are needed before the local CycloneDDS build.
install_native_dependencies

# Create the isolated Unitree SDK2 Python environment.
if [[ "${RWL_SKIP_PYTHON_SDK:-0}" != "1" ]]; then
  say "Preparing Unitree SDK2 Python environment"
  bash "$ROOT/scripts/install_python_sdk.sh"
else
  say "Skipping Unitree SDK2 Python because RWL_SKIP_PYTHON_SDK=1"
fi


mkdir -p workspace/examples workspace/mimic logs run
chmod +x Robot-Web-Lab scripts/*.sh

# Convenience launcher. Do not require root.
mkdir -p "$HOME/.local/bin"
ln -sfn "$ROOT/Robot-Web-Lab" "$HOME/.local/bin/Robot-Web-Lab"

say "Verifying Python sources inside Conda environment"
"$CONDA_BIN" run -n "$ENV_NAME" python -m compileall -q backend

cat <<MSG

Robot Web Lab web environment is installed in Conda environment: $ENV_NAME
Unitree SDK2 Python environment: $PY_SDK_ENV_NAME
  Activate with: conda activate $PY_SDK_ENV_NAME
No robot pack has been built yet. First launch opens the selective Robot Build Manager.

Start it with:
  ./Robot-Web-Lab

or, if ~/.local/bin is in PATH:
  Robot-Web-Lab

Default web address:
  http://127.0.0.1:8080

The server binds to 127.0.0.1 by default.
For trusted-LAN access run: RWL_HOST=0.0.0.0 ./Robot-Web-Lab
Set RWL_PORT to change the port.
Set RWL_CONDA_ENV before install to use a different Conda environment name.
MSG
