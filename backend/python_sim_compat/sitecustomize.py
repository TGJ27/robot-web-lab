from __future__ import annotations

import os

# Unitree's physical robot provides motion_switcher RPC. The local
# unitree_rl_mjlab MuJoCo bridge provides lowcmd/lowstate DDS but not that RPC.
# Robot Web Lab already switches the native controller to LL Debug before run.
if os.environ.get("RWL_MUJOCO_SIM") == "1":
    try:
        from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient

        def _rwl_check_mode(self):
            return 0, {"name": "", "form": ""}

        def _rwl_release_mode(self):
            return 0, None

        MotionSwitcherClient.CheckMode = _rwl_check_mode
        MotionSwitcherClient.ReleaseMode = _rwl_release_mode
    except Exception:
        pass
