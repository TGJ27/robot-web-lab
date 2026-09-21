from __future__ import annotations
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).expanduser().resolve()
required = [
    root / "simulate/config.yaml",
    root / "simulate/src/physics_joystick.h",
    root / "simulate/src/unitree_sdk2_bridge.h",
    root / "simulate/src/main.cc",
    root / "deploy/robots/g1/main.cpp",
    root / "deploy/robots/g1/src/State_Mimic.cpp",
    root / "deploy/robots/g1/config/config.yaml",
    root / "deploy/include/FSM/CtrlFSM.h",
]
missing = [p for p in required if not p.exists()]
if missing:
    raise SystemExit("Not a compatible unitree_rl_mjlab checkout; missing:\n  " + "\n  ".join(map(str, missing)))

changed: list[str] = []
def record(path: Path):
    rel = path.relative_to(root).as_posix()
    if rel not in changed:
        changed.append(rel)

def write_if_changed(path: Path, content: str):
    old = path.read_text() if path.exists() else None
    if old != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        record(path)

# ---------------------------------------------------------------------------
# Keyboard state shared by GLFW UI thread and virtual UnitreeJoystick thread.
# ---------------------------------------------------------------------------
keyboard_h = r'''#pragma once

#include <GLFW/glfw3.h>
#include <atomic>
#include <mutex>

namespace keyboard_input {

struct KeyboardState {
  bool w = false;
  bool s = false;
  bool a = false;
  bool d = false;
  bool q = false;
  bool e = false;
  bool key1 = false;
  bool key2 = false;
  bool key3 = false;
  bool keyU = false;
};

inline std::mutex state_mutex;
inline KeyboardState state;
inline std::atomic_bool debug_mode{false};

inline void set_key(int key, bool pressed) {
  std::lock_guard<std::mutex> lock(state_mutex);
  switch (key) {
    case GLFW_KEY_W: state.w = pressed; break;
    case GLFW_KEY_S: state.s = pressed; break;
    case GLFW_KEY_A: state.a = pressed; break;
    case GLFW_KEY_D: state.d = pressed; break;
    case GLFW_KEY_Q: state.q = pressed; break;
    case GLFW_KEY_E: state.e = pressed; break;
    case GLFW_KEY_1: state.key1 = pressed; break;
    case GLFW_KEY_2: state.key2 = pressed; break;
    case GLFW_KEY_3: state.key3 = pressed; break;
    case GLFW_KEY_U: state.keyU = pressed; break;
    default: break;
  }
}

inline KeyboardState snapshot() {
  std::lock_guard<std::mutex> lock(state_mutex);
  return state;
}

inline void set_debug_mode(bool enabled) { debug_mode.store(enabled); }
inline bool is_debug_mode() { return debug_mode.load(); }

}  // namespace keyboard_input
'''
write_if_changed(root / "simulate/src/keyboard_input.h", keyboard_h)

# ---------------------------------------------------------------------------
# Virtual Unitree joystick. Original FSM remains unchanged.
# 1 -> LT+B, 2 -> LT+Up, 3 -> RT+A, U -> RB+A.
# Trigger lead mimics a real user's trigger-before-button timing.
# ---------------------------------------------------------------------------
keyboard_joystick = r'''

// === G1 KEYBOARD JOYSTICK BEGIN ===
class KeyboardJoystick : public unitree::common::UnitreeJoystick
{
public:
    enum class Sequence { None, Passive, FixStand, Velocity, Mimic };

    KeyboardJoystick() : unitree::common::UnitreeJoystick()
    {
        LT.smooth = 1.0f;
        RT.smooth = 1.0f;
    }

    void update() override
    {
        using namespace std::chrono;
        const auto k = keyboard_input::snapshot();
        const auto now = steady_clock::now();
        poll_web_control(now);

        // In LL debug, keep the simulated wireless controller neutral.
        if (keyboard_input::is_debug_mode() || web_debug_mode_) {
            sequence_ = Sequence::None;
            prev1_ = k.key1; prev2_ = k.key2; prev3_ = k.key3; prevU_ = k.keyU;
            back(false); start(false); LB(false); RB(false);
            A(false); B(false); X(false); Y(false);
            up(false); down(false); left(false); right(false);
            LT(0.0f); RT(0.0f); lx(0.0f); ly(0.0f); rx(0.0f); ry(0.0f);
            return;
        }

        if (k.key1 && !prev1_) start_sequence(Sequence::Passive, now);
        if (k.key2 && !prev2_) start_sequence(Sequence::FixStand, now);
        if (k.key3 && !prev3_) start_sequence(Sequence::Velocity, now);
        if (k.keyU && !prevU_) start_sequence(Sequence::Mimic, now);
        prev1_ = k.key1; prev2_ = k.key2; prev3_ = k.key3; prevU_ = k.keyU;

        back(false); start(false); LB(false); RB(false);
        A(false); B(false); X(false); Y(false);
        up(false); down(false); left(false); right(false);

        float lt = 0.0f;
        float rt = 0.0f;
        if (sequence_ != Sequence::None) {
            const auto elapsed = duration_cast<milliseconds>(now - sequence_start_);
            const auto trigger_lead = milliseconds(250);
            const auto button_end   = milliseconds(450);
            const auto sequence_end = milliseconds(600);

            switch (sequence_) {
            case Sequence::Passive:
                lt = 1.0f;
                if (elapsed >= trigger_lead && elapsed < button_end) B(true);
                break;
            case Sequence::FixStand:
                lt = 1.0f;
                if (elapsed >= trigger_lead && elapsed < button_end) up(true);
                break;
            case Sequence::Velocity:
                rt = 1.0f;
                if (elapsed >= trigger_lead && elapsed < button_end) A(true);
                break;
            case Sequence::Mimic:
                if (elapsed < milliseconds(200)) { RB(true); A(true); }
                break;
            case Sequence::None:
                break;
            }

            if ((sequence_ == Sequence::Mimic && elapsed >= milliseconds(250)) ||
                (sequence_ != Sequence::Mimic && elapsed >= sequence_end)) {
                sequence_ = Sequence::None;
                lt = 0.0f;
                rt = 0.0f;
            }
        }
        LT(lt); RT(rt);

        // Trained velocity ranges: x [-0.5,1], y [-0.5,0.5], yaw [-1,1].
        const float forward = std::clamp(web_vx_ + (k.w ? 1.0f : 0.0f) + (k.s ? -0.5f : 0.0f), -0.5f, 1.0f);
        const float lateral = std::clamp(web_vy_ + (k.d ? 0.5f : 0.0f) + (k.a ? -0.5f : 0.0f), -0.5f, 0.5f);
        const float yaw     = std::clamp(web_yaw_ + (k.e ? 1.0f : 0.0f) + (k.q ? -1.0f : 0.0f), -1.0f, 1.0f);
        lx(lateral); ly(forward); rx(yaw); ry(0.0f);
    }

private:
    void poll_web_control(std::chrono::steady_clock::time_point now)
    {
        using namespace std::chrono;
        if (last_web_poll_.time_since_epoch().count() != 0 &&
            duration_cast<milliseconds>(now - last_web_poll_) < milliseconds(20)) return;
        last_web_poll_ = now;
        const char* dir = std::getenv("G1_SIM_RUNTIME_DIR");
        if (!dir || !*dir) return;

        {
            std::ifstream mode_file(std::string(dir) + "/control_mode");
            std::string mode;
            std::getline(mode_file, mode);
            web_debug_mode_ = (mode == "DEBUG");
        }

        std::ifstream in(std::string(dir) + "/web_control");
        unsigned long long seq = 0;
        std::string action;
        float vx = 0.0f, vy = 0.0f, yaw = 0.0f;
        if (!(in >> seq >> action >> vx >> vy >> yaw)) return;
        web_vx_ = vx; web_vy_ = vy; web_yaw_ = yaw;
        if (seq == web_seq_) return;
        web_seq_ = seq;
        if (action == "Passive") start_sequence(Sequence::Passive, now);
        else if (action == "FixStand") start_sequence(Sequence::FixStand, now);
        else if (action == "Velocity") start_sequence(Sequence::Velocity, now);
        else if (action == "Mimic") start_sequence(Sequence::Mimic, now);
    }

    void start_sequence(Sequence s, std::chrono::steady_clock::time_point now)
    {
        sequence_ = s;
        sequence_start_ = now;
    }
    Sequence sequence_{Sequence::None};
    std::chrono::steady_clock::time_point sequence_start_{};
    std::chrono::steady_clock::time_point last_web_poll_{};
    unsigned long long web_seq_{0};
    float web_vx_{0.0f}, web_vy_{0.0f}, web_yaw_{0.0f};
    bool web_debug_mode_{false};
    bool prev1_{false}, prev2_{false}, prev3_{false}, prevU_{false};
};
// === G1 KEYBOARD JOYSTICK END ===
'''

physics = root / "simulate/src/physics_joystick.h"
text = physics.read_text()
if '#include "keyboard_input.h"' not in text:
    needle = '#include "joystick/joystick.h"\n'
    if needle not in text:
        raise RuntimeError("physics_joystick.h include layout changed upstream")
    text = text.replace(needle, needle + '#include "keyboard_input.h"\n#include <chrono>\n#include <fstream>\n#include <sstream>\n#include <cstdlib>\n#include <algorithm>\n', 1)
elif '#include <chrono>' not in text:
    text = text.replace('#include "keyboard_input.h"\n', '#include "keyboard_input.h"\n#include <chrono>\n#include <fstream>\n#include <sstream>\n#include <cstdlib>\n#include <algorithm>\n', 1)
else:
    for inc in ['#include <fstream>', '#include <sstream>', '#include <cstdlib>', '#include <algorithm>']:
        if inc not in text:
            text = text.replace('#include <chrono>\n', '#include <chrono>\n' + inc + '\n', 1)

begin = text.find("// === G1 KEYBOARD JOYSTICK BEGIN ===")
if begin >= 0:
    end_marker = "// === G1 KEYBOARD JOYSTICK END ==="
    end = text.find(end_marker, begin)
    if end < 0:
        raise RuntimeError("keyboard joystick end marker missing")
    end += len(end_marker)
    text = text[:begin].rstrip() + keyboard_joystick + "\n" + text[end:].lstrip("\n")
elif "class KeyboardJoystick" in text:
    # Migrate the earlier package.
    cut = text.find("// Keyboard-backed replacement for the physical Unitree wireless controller.")
    if cut < 0:
        cut = text.find("class KeyboardJoystick")
    text = text[:cut].rstrip() + keyboard_joystick + "\n"
else:
    text = text.rstrip() + keyboard_joystick + "\n"
if text != physics.read_text():
    physics.write_text(text); record(physics)

# ---------------------------------------------------------------------------
# Simulator bridge selects keyboard virtual joystick.
# ---------------------------------------------------------------------------
bridge = root / "simulate/src/unitree_sdk2_bridge.h"
text = bridge.read_text()
if 'param::config.joystick_type == "keyboard"' not in text:
    pattern = r'(?m)^(?P<indent>[ \t]*)if\(param::config\.joystick_type == "xbox"\) \{'
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError("unitree_sdk2_bridge.h joystick block changed upstream")
    indent = m.group('indent')
    repl = (f'{indent}if(param::config.joystick_type == "keyboard") {{\n'
            f'{indent}    joystick = std::make_shared<KeyboardJoystick>();\n'
            f'{indent}}} else if(param::config.joystick_type == "xbox") {{')
    text = re.sub(pattern, repl, text, count=1)
    bridge.write_text(text); record(bridge)

# ---------------------------------------------------------------------------
# Simulator main: final callback region, LL/HL request files and hanger.
# ---------------------------------------------------------------------------
main = root / "simulate/src/main.cc"
text = main.read_text()
if '#include "keyboard_input.h"' not in text:
    needle = '#include "param.h"\n'
    if needle not in text:
        raise RuntimeError("main.cc param include changed upstream")
    text = text.replace(needle, needle + '#include "keyboard_input.h"\n', 1)
for inc in ['#include <fstream>\n', '#include <algorithm>\n']:
    if inc.strip() not in text:
        # Insert after keyboard header to keep patch localized.
        text = text.replace('#include "keyboard_input.h"\n', '#include "keyboard_input.h"\n' + inc, 1)

# Hanger starts released.
text = text.replace('bool enable_ = true;', 'bool enable_ = false;', 1)

# PhysicsLoop calls the browser hanger poller before its full definition below.
# Add an explicit declaration before the anonymous-namespace physics code so C++
# name lookup succeeds regardless of upstream function ordering.
if 'void poll_web_hanger();' not in text:
    band_singleton = 'inline ElasticBand elastic_band;'
    if band_singleton not in text:
        raise RuntimeError('main.cc elastic-band singleton changed upstream')
    text = text.replace(band_singleton, band_singleton + '\n\nvoid poll_web_hanger();', 1)

marker_a = '// user keyboard callback'
marker_b = '// run event loop'
if marker_a not in text or marker_b not in text:
    raise RuntimeError("main.cc keyboard callback markers changed upstream")
a = text.index(marker_a)
b = text.index(marker_b, a)
final_callback = r'''// user keyboard callback
// === G1 DUAL MODE HELPERS BEGIN ===
std::string g1_runtime_path(const std::string& name) {
  const char* dir = std::getenv("G1_SIM_RUNTIME_DIR");
  if (!dir || !*dir) return "";
  return std::string(dir) + "/" + name;
}

std::string read_runtime_value(const std::string& name) {
  const auto path = g1_runtime_path(name);
  if (path.empty()) return "";
  std::ifstream in(path);
  std::string value;
  std::getline(in, value);
  return value;
}

void write_runtime_value(const std::string& name, const std::string& value) {
  const auto path = g1_runtime_path(name);
  if (path.empty()) return;
  std::ofstream out(path, std::ios::trunc);
  out << value << std::endl;
}

void clear_hanger_force() {
  if (!m || !d) return;
  const int i = param::config.band_attached_link;
  if (i >= 0 && i + 2 < 6 * m->nbody) {
    d->xfrc_applied[i] = 0.0;
    d->xfrc_applied[i + 1] = 0.0;
    d->xfrc_applied[i + 2] = 0.0;
  }
}

void attach_hanger() {
  if (!d) return;

  // Real overhead spring/cable anchor. Attach with zero initial tension,
  // then UP/DOWN moves the physical anchor point itself.
  elastic_band.point_[0] = d->qpos[0];
  elastic_band.point_[1] = d->qpos[1];
  elastic_band.point_[2] = d->qpos[2] + 0.50;
  elastic_band.length_ = 0.50;
  elastic_band.stiffness_ = 2500.0;
  elastic_band.damping_ = 300.0;
  elastic_band.enable_ = true;
  clear_hanger_force();
  std::cout << "[HANGER] attached anchor_z=" << elastic_band.point_[2]
            << "m. UP=raise DOWN=lower RIGHT=release" << std::endl;
}

void release_hanger() {
  elastic_band.enable_ = false;
  clear_hanger_force();
  std::cout << "[HANGER] released" << std::endl;
}

void poll_web_hanger() {
  const auto path = g1_runtime_path("web_hanger");
  if (path.empty()) return;
  std::ifstream in(path);
  unsigned long long seq = 0;
  std::string action;
  if (!(in >> seq >> action)) return;
  static unsigned long long last_seq = 0;
  if (seq == last_seq) return;
  last_seq = seq;
  if (action == "attach") attach_hanger();
  else if (action == "release") release_hanger();
  else if (action == "raise" && elastic_band.enable_) {
    elastic_band.point_[2] += 0.10;
    std::cout << "[HANGER] web raise z=" << elastic_band.point_[2] << std::endl;
  } else if (action == "lower" && elastic_band.enable_) {
    const double min_anchor_z = d ? (d->qpos[2] + 0.05) : 0.05;
    elastic_band.point_[2] = std::max(min_anchor_z, elastic_band.point_[2] - 0.10);
    std::cout << "[HANGER] web lower z=" << elastic_band.point_[2] << std::endl;
  }
}
// === G1 DUAL MODE HELPERS END ===

void user_key_cb(GLFWwindow* window, int key, int scancode, int act, int mods) {
  if (act == GLFW_PRESS || act == GLFW_REPEAT) {
    keyboard_input::set_key(key, true);
  } else if (act == GLFW_RELEASE) {
    keyboard_input::set_key(key, false);
  }

  if (act == GLFW_PRESS) {
    // Simulator-level hanger: available in ALL HL and LL modes.
    if (param::config.enable_elastic_band == 1) {
      if (key == GLFW_KEY_LEFT) {
        attach_hanger();
      } else if (key == GLFW_KEY_RIGHT) {
        release_hanger();
      } else if (key == GLFW_KEY_UP && elastic_band.enable_) {
        elastic_band.point_[2] += 0.10;
        std::cout << "[HANGER] anchor raised to z=" << elastic_band.point_[2] << "m" << std::endl;
      } else if (key == GLFW_KEY_DOWN && elastic_band.enable_) {
        const double min_anchor_z = d ? (d->qpos[2] + 0.05) : 0.05;
        elastic_band.point_[2] = std::max(min_anchor_z, elastic_band.point_[2] - 0.10);
        std::cout << "[HANGER] anchor lowered to z=" << elastic_band.point_[2] << "m" << std::endl;
      }
    }

    const std::string control_mode = read_runtime_value("control_mode");
    if (key == GLFW_KEY_0) {
      if (control_mode == "HL" && read_runtime_value("fsm_state") == "Passive") {
        keyboard_input::set_debug_mode(true);
        write_runtime_value("request", "DEBUG");
        std::cout << "[MODE] LL debug requested" << std::endl;
      } else {
        std::cout << "[MODE] 0 ignored: LL can only be entered from HL Passive (press 1 first)" << std::endl;
      }
    } else if (key == GLFW_KEY_1 && control_mode == "DEBUG") {
      keyboard_input::set_debug_mode(false);
      write_runtime_value("request", "HL_PASSIVE");
      std::cout << "[MODE] HL Passive requested" << std::endl;
    }

    if (key == GLFW_KEY_BACKSPACE || key == GLFW_KEY_R) {
      mj_resetData(m, d);
      mj_forward(m, d);
    }
  }
}

'''
text = text[:a] + final_callback + text[b:]
# Poll browser hanger requests from the outer elastic-band block, even while
# the hanger is currently released. Normalize legacy patches that put
# the poll call inside `if (elastic_band.enable_)`, because that prevents a
# browser Attach request from ever enabling a released hanger.
physics_start = text.find('                if (param::config.enable_elastic_band == 1)')
physics_end = text.find('                // call mj_step', physics_start)
if physics_start < 0 or physics_end < 0:
    raise RuntimeError("main.cc elastic-band physics block changed upstream")
physics_segment = text[physics_start:physics_end]
physics_segment = re.sub(r'^[ \t]*poll_web_hanger\(\);[ \t]*\n+', '', physics_segment, flags=re.MULTILINE)
outer_band_needle = ('                if (param::config.enable_elastic_band == 1)\n'
                     '                {\n')
if outer_band_needle not in physics_segment:
    raise RuntimeError("main.cc elastic-band outer block changed upstream")
physics_segment = physics_segment.replace(outer_band_needle,
                    outer_band_needle + '                  poll_web_hanger();\n', 1)
text = text[:physics_start] + physics_segment + text[physics_end:]
if text != main.read_text():
    main.write_text(text); record(main)

# ---------------------------------------------------------------------------
# Simulator config: keyboard input + hanger subsystem enabled (released by default).
# ---------------------------------------------------------------------------
cfg = root / "simulate/config.yaml"
text = cfg.read_text()
new, n = re.subn(r'use_joystick:\s*[01][^\n]*',
                 'use_joystick: 1 # Robot Web Lab virtual keyboard/web joystick', text, count=1)
if n != 1:
    raise RuntimeError("simulate/config.yaml use_joystick entry changed upstream")
text = new
new, n = re.subn(r'joystick_type:\s*"(?:xbox|switch|keyboard)"[^\n]*',
                 'joystick_type: "keyboard" # keyboard, xbox, or switch', text, count=1)
if n != 1:
    raise RuntimeError("simulate/config.yaml joystick_type entry changed upstream")
text = new
new, n = re.subn(r'enable_elastic_band:\s*[01][^\n]*',
                 'enable_elastic_band: 1 # enabled; starts RELEASED; arrows control it', text, count=1)
if n != 1:
    raise RuntimeError("simulate/config.yaml elastic-band entry changed upstream")
text = new
if text != cfg.read_text():
    cfg.write_text(text); record(cfg)

# ---------------------------------------------------------------------------
# Keep original Unitree FSM. Undo earlier simplified keyboard FSM if present.
# ---------------------------------------------------------------------------
fsm = root / "deploy/robots/g1/config/config.yaml"
text = fsm.read_text()
restored = text
restored = restored.replace('FixStand: up.on_pressed', 'FixStand: LT + up.on_pressed')
restored = restored.replace('Passive: B.on_pressed', 'Passive: LT + B.on_pressed')
restored = restored.replace('Velocity: A.on_pressed', 'Velocity: RT + A.on_pressed')
if restored != text:
    fsm.write_text(restored); record(fsm)

# ---------------------------------------------------------------------------
# Disable unused terminal keyboard reader (g1_ctrl runs under supervisor).
# ---------------------------------------------------------------------------
g1main = root / "deploy/robots/g1/main.cpp"
text = g1main.read_text()
old = 'std::shared_ptr<Keyboard> FSMState::keyboard = std::make_shared<Keyboard>();\n'
new = 'std::shared_ptr<Keyboard> FSMState::keyboard = nullptr; // simulator virtual joystick owns input\n'
if old in text:
    g1main.write_text(text.replace(old, new, 1)); record(g1main)

# ---------------------------------------------------------------------------
# Publish the REAL g1_ctrl FSM state into runtime/fsm_state.
# ---------------------------------------------------------------------------
ctrlfsm = root / "deploy/include/FSM/CtrlFSM.h"
text = ctrlfsm.read_text()
if '#include <fstream>' not in text:
    if '#include <yaml-cpp/yaml.h>\n' in text:
        text = text.replace('#include <yaml-cpp/yaml.h>\n', '#include <yaml-cpp/yaml.h>\n#include <fstream>\n#include <cstdlib>\n', 1)
    elif '#include <spdlog/spdlog.h>\n' in text:
        text = text.replace('#include <spdlog/spdlog.h>\n', '#include <spdlog/spdlog.h>\n#include <fstream>\n#include <cstdlib>\n', 1)

helper = r'''
// === G1 FSM RUNTIME STATE BEGIN ===
inline void write_g1_sim_fsm_state(const std::string& state)
{
    const char* dir = std::getenv("G1_SIM_RUNTIME_DIR");
    if (!dir || !*dir) return;
    std::ofstream out(std::string(dir) + "/fsm_state", std::ios::trunc);
    out << state << std::endl;
}
// === G1 FSM RUNTIME STATE END ===
'''
if '// === G1 FSM RUNTIME STATE BEGIN ===' not in text:
    if 'class CtrlFSM\n' not in text:
        raise RuntimeError("CtrlFSM.h class marker changed upstream")
    text = text.replace('class CtrlFSM\n', helper + '\nclass CtrlFSM\n', 1)

start_old = '        currentState = states[0];\n        currentState->enter();\n'
start_new = start_old + '        write_g1_sim_fsm_state(currentState->getStateString());\n'
if start_new not in text:
    if start_old not in text:
        raise RuntimeError("CtrlFSM.h start block changed upstream")
    text = text.replace(start_old, start_new, 1)

trans_old = '                    currentState = state;\n                    currentState->enter();\n                    break;\n'
trans_new = ('                    currentState = state;\n'
             '                    currentState->enter();\n'
             '                    write_g1_sim_fsm_state(currentState->getStateString());\n'
             '                    break;\n')
if trans_new not in text:
    if trans_old not in text:
        raise RuntimeError("CtrlFSM.h transition block changed upstream")
    text = text.replace(trans_old, trans_new, 1)
if text != ctrlfsm.read_text():
    ctrlfsm.write_text(text); record(ctrlfsm)

# ---------------------------------------------------------------------------
# G1 Mimic PR #56 equivalent: fix Eigen dangling transpose + init ordering.
# ---------------------------------------------------------------------------
mimic = root / "deploy/robots/g1/src/State_Mimic.cpp"
text = mimic.read_text()
if 'static Eigen::Quaternionf init_quat = Eigen::Quaternionf::Identity();' not in text:
    old = 'static Eigen::Quaternionf init_quat;'
    if old not in text:
        raise RuntimeError("State_Mimic.cpp init_quat declaration changed upstream")
    text = text.replace(old, 'static Eigen::Quaternionf init_quat = Eigen::Quaternionf::Identity();', 1)

if 'const Eigen::Matrix3f rot = rot_.toRotationMatrix().transpose();' not in text:
    old = ('    auto rot_ = (init_quat * ref_quat_w).conjugate() * real_quat_w;\n'
           '    auto rot = rot_.toRotationMatrix().transpose();\n')
    if old not in text:
        raise RuntimeError("State_Mimic.cpp anchor orientation block changed upstream")
    new = ('    const Eigen::Quaternionf rot_ =\n'
           '        (init_quat * ref_quat_w).conjugate() * real_quat_w;\n'
           '    const Eigen::Matrix3f rot = rot_.toRotationMatrix().transpose();\n')
    text = text.replace(old, new, 1)

align_marker = 'init_quat = Eigen::Quaternionf(robot_yaw * ref_yaw.transpose());'
if align_marker not in text:
    old = '    motion = motion_; // set for specific motion\n    env->reset();\n'
    if old not in text:
        raise RuntimeError("State_Mimic.cpp enter reset block changed upstream")
    new = ('    motion = motion_; // set for specific motion\n\n'
           '    env->robot->update();\n'
           '    motion->reset(env->robot->data, time_range_[0]);\n'
           '    {\n'
           '        const Eigen::Matrix3f ref_yaw =\n'
           '            isaaclab::yawQuaternion(motion->root_quaternion()).toRotationMatrix();\n'
           '        const Eigen::Matrix3f robot_yaw =\n'
           '            isaaclab::yawQuaternion(robot_quat_w(env.get())).toRotationMatrix();\n'
           '        init_quat = Eigen::Quaternionf(robot_yaw * ref_yaw.transpose());\n'
           '    }\n\n'
           '    env->reset();\n')
    text = text.replace(old, new, 1)

old_thread = ('        motion->reset(env->robot->data, time_range_[0]);\n'
              '        auto ref_yaw = isaaclab::yawQuaternion(motion->root_quaternion()).toRotationMatrix();\n'
              '        auto robot_yaw = isaaclab::yawQuaternion(robot_quat_w(env.get())).toRotationMatrix();\n'
              '        init_quat = robot_yaw * ref_yaw.transpose();\n'
              '        env->reset();\n')
if old_thread in text:
    text = text.replace(old_thread, '        env->reset(); // init_quat is already valid\n', 1)
if text != mimic.read_text():
    mimic.write_text(text); record(mimic)

# ---------------------------------------------------------------------------
# Verification of critical invariants.
# ---------------------------------------------------------------------------
physics_text = physics.read_text()
main_text = main.read_text()
fsm_text = fsm.read_text()
mimic_text = mimic.read_text()
ctrl_text = ctrlfsm.read_text()
cfg_text = cfg.read_text()
assert 'k.keyU' in physics_text and 'k.key4' not in physics_text
assert 'web_control' in physics_text
assert 'web_vx_' in physics_text
assert 'web_debug_mode_' in physics_text
assert 'std::chrono::milliseconds(250)' in physics_text or 'milliseconds(250)' in physics_text
assert 'GLFW_KEY_0' in main_text
assert 'read_runtime_value("fsm_state") == "Passive"' in main_text
assert 'GLFW_KEY_LEFT' in main_text and 'GLFW_KEY_RIGHT' in main_text
assert 'web_hanger' in main_text and 'poll_web_hanger();' in main_text
assert 'void poll_web_hanger();' in main_text
assert main_text.index('void poll_web_hanger();') < main_text.index('poll_web_hanger();', main_text.index('if (param::config.enable_elastic_band == 1)'))
assert 'elastic_band.stiffness_ = 2500.0;' in main_text
assert 'elastic_band.point_[2] += 0.10;' in main_text
assert 'elastic_band.length_ = std::max(0.2' not in main_text
assert 'enable_elastic_band: 1' in cfg_text
assert 'use_joystick: 1' in cfg_text
assert 'FixStand: LT + up.on_pressed' in fsm_text
assert 'Mimic_Dance1_subject2: RB + A.on_pressed' in fsm_text
assert 'write_g1_sim_fsm_state(currentState->getStateString())' in ctrl_text
assert 'static Eigen::Quaternionf init_quat = Eigen::Quaternionf::Identity();' in mimic_text
assert 'const Eigen::Matrix3f rot' in mimic_text
assert align_marker in mimic_text
assert mimic_text.index(align_marker) < mimic_text.index('env->reset();')

if changed:
    print("Patched/normalized:")
    for item in changed:
        print("  -", item)
else:
    print("Already fully patched; no changes needed.")