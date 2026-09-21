# Architecture

Robot Web Lab separates the browser UI, application state, native process control, and upstream robot dependencies.

```text
Browser (HTML/CSS/JavaScript)
        │ REST + WebSocket
        ▼
FastAPI backend
├── robot registry + settings
├── selective native build manager
├── low-level workspace + build profiles
├── low-level process runner
├── model/asset service
└── native supervisor
        │
        ├── unitree_rl_mjlab (MuJoCo simulation + controllers)
        ├── unitree_sdk2     (DDS / low-level examples)
        └── unitree_mujoco   (additional robot models)
```

## Control ownership

High-Level and Low-Level execution are mutually exclusive. The backend coordinates ownership transitions so a low-level program is not launched while a high-level controller still owns command output.

## Native runtime

MuJoCo runs as a native headless process. The browser remains the visual front end and receives state through the FastAPI application. Runtime PID/state files live under `run/` and are intentionally not committed.

## Selective builds

Robot Web Lab does not build every upstream target during installation. Robot packs are built from the Robots / Build Manager, while low-level SDK examples are compiled on demand. Generated native artifacts live under `build/` and `workspace/` and are intentionally ignored by Git.

## Upstream dependencies

Unitree repositories are represented as pinned Git submodules under `third_party/`. Their pinned revisions are defined in `scripts/pins.sh`. Project code does not vendor those repositories into this repository.

Three.js browser modules are downloaded by `install.sh` into `frontend/vendor/` and are served locally after installation.
