#!/usr/bin/env python3
"""Install Robot Web Lab's robot-agnostic browser High-Level control bridge.

The upstream rl_mjlab controllers all consume joystick state from
FSMState::lowstate->joystick.  G1 previously got web/keyboard control indirectly
through the simulator's virtual joystick, but the other deploy controllers did
not reliably receive that bridge.  This patch overlays Robot Web Lab's
web_control file directly onto the controller-side joystick for every deploy
controller (G1, G1-23DoF, Go2, H1-2, A2 and R1).
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).expanduser().resolve()
fsm = root / "deploy/include/FSM/FSMState.h"
ctrl = root / "deploy/include/FSM/CtrlFSM.h"
if not fsm.is_file() or not ctrl.is_file():
    raise SystemExit(f"Missing compatible rl_mjlab deploy headers under {root}")

# ---------------------------------------------------------------------------
# Controller-side web joystick overlay.
# ---------------------------------------------------------------------------
s = fsm.read_text(encoding="utf-8")
for inc in (
    "#include <algorithm>",
    "#include <chrono>",
    "#include <cstdlib>",
    "#include <fstream>",
    "#include <string>",
):
    if inc not in s:
        if "#pragma once\n" not in s:
            raise RuntimeError("FSMState.h pragma-once layout changed upstream")
        s = s.replace("#pragma once\n", "#pragma once\n" + inc + "\n", 1)

begin = "// === ROBOT WEB LAB WEB CONTROL BEGIN ==="
end = "// === ROBOT WEB LAB WEB CONTROL END ==="
bridge = r'''
// === ROBOT WEB LAB WEB CONTROL BEGIN ===
namespace rwl_web_control
{
inline const char* runtime_dir()
{
    const char* dir = std::getenv("RWL_SIM_RUNTIME_DIR");
    if (dir && *dir) return dir;
    // Backward compatibility with the original G1-only integration.
    dir = std::getenv("G1_SIM_RUNTIME_DIR");
    return (dir && *dir) ? dir : nullptr;
}

struct WebInput
{
    unsigned long long last_seq = 0;
    float vx = 0.0f;
    float vy = 0.0f;
    float yaw = 0.0f;
    std::string action;
    std::chrono::steady_clock::time_point action_start{};
    std::chrono::steady_clock::time_point last_poll{};
};

inline WebInput& input()
{
    static WebInput value;
    return value;
}

inline void apply(unitree::common::UnitreeJoystick& joystick)
{
    using namespace std::chrono;
    auto& web = input();
    const auto now = steady_clock::now();

    if (web.last_poll.time_since_epoch().count() == 0 ||
        duration_cast<milliseconds>(now - web.last_poll) >= milliseconds(20))
    {
        web.last_poll = now;
        const char* dir = runtime_dir();
        if (dir)
        {
            std::ifstream in(std::string(dir) + "/web_control");
            unsigned long long seq = 0;
            std::string action;
            float vx = 0.0f, vy = 0.0f, yaw = 0.0f;
            if (in >> seq >> action >> vx >> vy >> yaw)
            {
                // Always keep the newest commanded axes, even when the action is '-'.
                web.vx = std::clamp(vx, -0.5f, 1.0f);
                web.vy = std::clamp(vy, -0.5f, 0.5f);
                web.yaw = std::clamp(yaw, -1.0f, 1.0f);
                if (seq != web.last_seq)
                {
                    web.last_seq = seq;
                    if (action == "Passive" || action == "FixStand" ||
                        action == "Velocity" || action == "Mimic")
                    {
                        web.action = action;
                        web.action_start = now;
                    }
                }
            }
        }
    }

    // Browser control owns the simulated controller while the native HL
    // controller is running.  Reset buttons every cycle, then synthesize the
    // same Unitree button chords used by the upstream FSM configuration.
    joystick.back(false); joystick.start(false);
    joystick.LB(false); joystick.RB(false);
    joystick.A(false); joystick.B(false); joystick.X(false); joystick.Y(false);
    joystick.up(false); joystick.down(false); joystick.left(false); joystick.right(false);

    float lt = 0.0f;
    float rt = 0.0f;
    if (!web.action.empty())
    {
        const auto elapsed = duration_cast<milliseconds>(now - web.action_start);
        const auto trigger_lead = milliseconds(250);
        const auto button_end = milliseconds(450);
        const auto sequence_end = milliseconds(600);

        if (web.action == "Passive")
        {
            lt = 1.0f;
            if (elapsed >= trigger_lead && elapsed < button_end) joystick.B(true);
        }
        else if (web.action == "FixStand")
        {
            lt = 1.0f;
            if (elapsed >= trigger_lead && elapsed < button_end) joystick.up(true);
        }
        else if (web.action == "Velocity")
        {
            rt = 1.0f;
            if (elapsed >= trigger_lead && elapsed < button_end) joystick.A(true);
        }
        else if (web.action == "Mimic")
        {
            if (elapsed < milliseconds(200))
            {
                joystick.RB(true);
                joystick.A(true);
            }
        }

        const bool mimic_done = web.action == "Mimic" && elapsed >= milliseconds(250);
        const bool normal_done = web.action != "Mimic" && elapsed >= sequence_end;
        if (mimic_done || normal_done)
        {
            web.action.clear();
            lt = 0.0f;
            rt = 0.0f;
        }
    }

    joystick.LT(lt);
    joystick.RT(rt);
    // Preserve the same axis convention used by the original working G1 web
    // joystick bridge.  Upstream velocity observations handle their own signs.
    joystick.lx(web.vy);
    joystick.ly(web.vx);
    joystick.rx(web.yaw);
    joystick.ry(0.0f);
}
} // namespace rwl_web_control
// === ROBOT WEB LAB WEB CONTROL END ===
'''

if begin in s:
    b = s.index(begin)
    e = s.index(end, b) + len(end)
    s = s[:b] + bridge.strip() + s[e:]
else:
    marker = "class FSMState : public BaseState"
    if marker not in s:
        raise RuntimeError("FSMState.h class marker changed upstream")
    s = s.replace(marker, bridge + "\n\n" + marker, 1)

old_pre = """    void pre_run()\n    {\n        lowstate->update();\n        if(keyboard) keyboard->update();\n    }\n"""
new_pre = """    void pre_run()\n    {\n        lowstate->update();\n        if(keyboard) keyboard->update();\n        rwl_web_control::apply(lowstate->joystick);\n    }\n"""
if new_pre not in s:
    if old_pre not in s:
        raise RuntimeError("FSMState.h pre_run block changed upstream")
    s = s.replace(old_pre, new_pre, 1)
fsm.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------------------
# Publish the real native FSM state for the web UI for every robot.
# ---------------------------------------------------------------------------
s = ctrl.read_text(encoding="utf-8")
for inc in ("#include <cstdlib>", "#include <fstream>"):
    if inc not in s:
        # Insert after any existing #pragma/include preamble.
        lines = s.splitlines()
        insert_at = 1 if lines and lines[0].startswith("#pragma once") else 0
        lines.insert(insert_at, inc)
        s = "\n".join(lines) + ("\n" if ctrl.read_text(encoding="utf-8").endswith("\n") else "")

# Normalize the old G1-only helper if present.
g1_begin = "// === G1 FSM RUNTIME STATE BEGIN ==="
g1_end = "// === G1 FSM RUNTIME STATE END ==="
if g1_begin in s and g1_end in s:
    b = s.index(g1_begin)
    e = s.index(g1_end, b) + len(g1_end)
    s = s[:b] + s[e:]

state_begin = "// === ROBOT WEB LAB FSM STATE BEGIN ==="
state_end = "// === ROBOT WEB LAB FSM STATE END ==="
state_helper = r'''
// === ROBOT WEB LAB FSM STATE BEGIN ===
inline void rwl_write_fsm_state(const std::string& state)
{
    const char* dir = std::getenv("RWL_SIM_RUNTIME_DIR");
    if (!dir || !*dir) dir = std::getenv("G1_SIM_RUNTIME_DIR");
    if (!dir || !*dir) return;
    std::ofstream out(std::string(dir) + "/fsm_state", std::ios::trunc);
    if (out) out << state << std::endl;
}
// === ROBOT WEB LAB FSM STATE END ===
'''
if state_begin in s:
    b = s.index(state_begin)
    e = s.index(state_end, b) + len(state_end)
    s = s[:b] + state_helper.strip() + s[e:]
else:
    marker = "class CtrlFSM"
    if marker not in s:
        raise RuntimeError("CtrlFSM.h class marker changed upstream")
    s = s.replace(marker, state_helper + "\n\n" + marker, 1)

# Replace either old G1 helper calls or add generic calls where needed.
s = s.replace("write_g1_sim_fsm_state(currentState->getStateString());", "rwl_write_fsm_state(currentState->getStateString());")
start_old = "        currentState = states[0];\n        currentState->enter();\n"
start_new = start_old + "        rwl_write_fsm_state(currentState->getStateString());\n"
if start_new not in s:
    if start_old not in s:
        raise RuntimeError("CtrlFSM.h initial-state block changed upstream")
    s = s.replace(start_old, start_new, 1)
trans_old = "                    currentState = state;\n                    currentState->enter();\n                    break;\n"
trans_new = (
    "                    currentState = state;\n"
    "                    currentState->enter();\n"
    "                    rwl_write_fsm_state(currentState->getStateString());\n"
    "                    break;\n"
)
if trans_new not in s:
    if trans_old not in s:
        raise RuntimeError("CtrlFSM.h transition block changed upstream")
    s = s.replace(trans_old, trans_new, 1)
ctrl.write_text(s, encoding="utf-8")

# Critical invariants.
assert "rwl_web_control::apply(lowstate->joystick);" in fsm.read_text(encoding="utf-8")
assert 'std::getenv("RWL_SIM_RUNTIME_DIR")' in fsm.read_text(encoding="utf-8")
assert "rwl_write_fsm_state(currentState->getStateString());" in ctrl.read_text(encoding="utf-8")
print("Robot Web Lab multi-robot web High-Level control bridge ready.")
