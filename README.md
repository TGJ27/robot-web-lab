# Robot Web Lab

**Current release: v0.1.0**

Robot Web Lab is a browser-based robotics development environment for simulation, robot control, telemetry, and low-level SDK experimentation. The first public release focuses on Unitree robots with a native MuJoCo runtime and a lightweight FastAPI + vanilla JavaScript interface.

> Robot Web Lab is an independent community project and is not an official Unitree Robotics project.

## What it includes

- Full-page **Robots / Build Manager** with local robot previews, selective package builds, build state, queue information, and environment details.
- Native **headless MuJoCo** simulation managed by the backend.
- **High-Level / Low-Level ownership switching** so only one command source owns the robot at a time.
- Low-Level code editor with read-only built-in SDK examples plus editable user workspace files.
- YAML-backed build profiles for per-example compiler, include, definition, and library requirements.
- Local/offline robot artwork for G1, G1 23DoF, Go2, H1-2, R1, H2, and A2.
- Local Three.js rendering after installation; no runtime CDN is required for the browser UI.

## Robot support

| Robot | Native simulation | Web High-Level control | Low-Level workflow |
| --- | --- | --- | --- |
| Unitree G1 | Yes | Yes | Yes |
| Unitree G1 23DoF | Yes | Not yet | Yes |
| Unitree Go2 | Yes | Not yet | Yes |
| Unitree H1-2 | Yes | Not yet | Yes |
| Unitree R1 | Yes | Not yet | Yes |
| Unitree H2 | Yes | Not yet | Yes |
| Unitree A2 | Yes | Not yet | No compatible SDK2 low-level example in the pinned revision |

Support depends on the pinned upstream revisions in `scripts/pins.sh`.

## Requirements

Robot Web Lab is intended for Ubuntu/Linux development machines. The installer uses Conda for Python and `apt` for native build dependencies. Git is required for the pinned Unitree submodules.

A normal installation needs internet access once to fetch the Git submodules, Python packages, Ubuntu build dependencies, and the pinned Three.js browser modules.

## Install

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/TGJ27/robot-web-lab.git
cd robot-web-lab
./install.sh
```

If you cloned without `--recurse-submodules`, run:

```bash
./scripts/bootstrap_submodules.sh
./install.sh
```

Then start Robot Web Lab:

```bash
./Robot-Web-Lab
```

Open:

```text
http://127.0.0.1:8080
```

The first launch starts with no robot pack built. Open **Robots / Build Manager**, choose the robot/package combination you need, and build it from the UI.

## Optional launcher settings

The launcher binds to localhost by default. To expose it on a trusted LAN:

```bash
RWL_HOST=0.0.0.0 ./Robot-Web-Lab
```

To change the port:

```bash
RWL_PORT=9000 ./Robot-Web-Lab
```

The default Conda environment is `robot-web-lab`. Override it before installation with `RWL_CONDA_ENV`.

## Repository layout

```text
backend/                 FastAPI application and native process management
frontend/                Browser UI, robot viewer, and local robot artwork
config/                  Example configuration
scripts/                 Dependency/bootstrap/native-build tooling
tests/                   API, UI-contract, runtime, and build tests
docs/                    Architecture notes
workspace/               Local user/build state (ignored except .gitkeep)
third_party/             Pinned Git submodules (created/fetched by Git)
build/                   Generated native build output (ignored)
run/                     Runtime PID/state files (ignored)
logs/                    Runtime logs (ignored)
```

## Development and tests

Install development requirements in a Python 3.11 environment:

```bash
python -m pip install -r requirements-dev.txt
pytest -q
bash tests/test_install.sh
bash tests/test_scaffold.sh
```

Some frontend syntax checks use Node.js when it is available.

## Dependency model

The Unitree repositories are not committed as copied source trees. They are pinned as Git submodules:

```text
third_party/unitree_rl_mjlab
third_party/unitree_sdk2
third_party/unitree_mujoco
```

Pinned commit IDs live in `scripts/pins.sh`. To verify a checked-out dependency set:

```bash
./scripts/verify_submodules.sh
```

Three.js files under `frontend/vendor/` are installer-managed and ignored by Git. `frontend/vendor/README.md` documents the pinned browser dependency.

## Generated/local files

Do not commit native build output, runtime state, Python caches, local Conda metadata, user workspace files, or downloaded frontend vendor modules. The included `.gitignore` covers these paths.

## Safety

Robot Web Lab can launch code that produces robot commands. Validate behavior in simulation first, understand the active control owner, and use appropriate physical safety procedures before connecting development code to real hardware.

## License

Robot Web Lab is released under the MIT License. See [LICENSE](LICENSE).

Upstream Unitree repositories and Three.js remain subject to their own licenses and terms.
