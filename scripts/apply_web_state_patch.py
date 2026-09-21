#!/usr/bin/env python3
"""Install Robot Web Lab native state export and headless MuJoCo target."""
from pathlib import Path
import re
import sys

root=Path(sys.argv[1]).expanduser().resolve()
main=root/'simulate/src/main.cc'
cmake=root/'simulate/CMakeLists.txt'
headless=root/'simulate/src/rwl_headless_main.cc'
if not main.is_file() or not cmake.is_file(): raise SystemExit(f'Missing compatible simulate tree under {root}')

# Keep the original viewer executable compatible with the browser state bridge for
# debugging, even though Robot Web Lab launches the dedicated headless target.
s=main.read_text()
if '// === ROBOT WEB LAB STATE BRIDGE BEGIN ===' not in s:
    if '#include <fstream>' not in s:
        needle='#include <iostream>\n'
        if needle not in s: raise SystemExit('main.cc include layout changed')
        s=s.replace(needle,needle+'#include <fstream>\n',1)
    needle='  mjData *d = nullptr;\n'
    if needle not in s: raise SystemExit('main.cc mjData declaration changed')
    bridge=r'''

  // === ROBOT WEB LAB STATE BRIDGE BEGIN ===
  void rwl_poll_runtime_action()
  {
    if (!m || !d) return;
    static double next_poll = 0.0;
    static unsigned long last_seq = 0;
    if (d->time < next_poll) return;
    next_poll = d->time + 0.02;
    const char* dir = std::getenv("G1_SIM_RUNTIME_DIR");
    if (!dir || !*dir) return;
    std::ifstream in(std::string(dir) + "/web_runtime");
    unsigned long seq = 0;
    std::string action;
    if (!(in >> seq >> action) || seq == last_seq) return;
    last_seq = seq;
    if (action == "reset") {
      mj_resetData(m, d);
      mj_forward(m, d);
    }
  }

  void rwl_write_web_state()
  {
    if (!m || !d) return;
    rwl_poll_runtime_action();
    static double next_write = 0.0;
    if (d->time < next_write) return;
    next_write = d->time + (1.0 / 30.0);
    const char* dir = std::getenv("G1_SIM_RUNTIME_DIR");
    if (!dir || !*dir) return;
    const std::string target = std::string(dir) + "/native_state";
    const std::string tmp = target + ".tmp";
    std::ofstream out(tmp, std::ios::trunc);
    if (!out) return;
    out.precision(10);
    out << d->time << " " << m->nq;
    for (int i = 0; i < m->nq; ++i) out << " " << d->qpos[i];
    out << "\n";
    out.close();
    std::rename(tmp.c_str(), target.c_str());
  }
  // === ROBOT WEB LAB STATE BRIDGE END ===
'''
    s=s.replace(needle,needle+bridge,1)
if 'rwl_write_web_state();' not in s.split('// === ROBOT WEB LAB STATE BRIDGE END ===',1)[1]:
    s=s.replace('mj_step(m, d);\n', 'mj_step(m, d);\n              rwl_write_web_state();\n', 1)
main.write_text(s)

headless_source=r'''// Robot Web Lab headless MuJoCo runtime. No native viewer/window is created.
#include <mujoco/mujoco.h>
#include <unitree/robot/channel/channel_factory.hpp>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

#include "param.h"
#include "unitree_sdk2_bridge.h"

#define NUM_MOTOR_IDL_GO 20

namespace {
std::atomic_bool keep_running{true};

std::filesystem::path executable_dir() {
  char buf[4096];
  const auto n = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
  if (n <= 0) return std::filesystem::current_path();
  buf[n] = '\0';
  return std::filesystem::path(buf).parent_path();
}

struct ElasticBand {
  double stiffness=2500.0, damping=300.0, length=0.50;
  bool enabled=false;
  std::vector<double> point{0.0,0.0,3.0};
  void clear(mjModel* m, mjData* d) {
    const int body=param::config.band_attached_link/6;
    if (!m || !d || body<0 || body>=m->nbody) return;
    for (int i=0;i<3;++i) d->xfrc_applied[6*body+i]=0.0;
  }
  void attach(mjModel* m, mjData* d) {
    if (!m || !d || m->nq<3) return;
    point[0]=d->qpos[0]; point[1]=d->qpos[1]; point[2]=d->qpos[2]+0.50;
    length=0.50; stiffness=2500.0; damping=300.0; enabled=true; clear(m,d);
  }
  void release(mjModel* m, mjData* d) { enabled=false; clear(m,d); }
  void apply(mjModel* m, mjData* d) {
    if (!enabled || !m || !d || m->nq < 3 || m->nv < 3) return;
    const int body = param::config.band_attached_link / 6;
    if (body < 0 || body >= m->nbody) return;
    double dx[3]{point[0]-d->qpos[0],point[1]-d->qpos[1],point[2]-d->qpos[2]};
    const double dist=std::sqrt(dx[0]*dx[0]+dx[1]*dx[1]+dx[2]*dx[2]);
    if (dist < 1e-9) return;
    const double dir[3]{dx[0]/dist,dx[1]/dist,dx[2]/dist};
    const double v=d->qvel[0]*dir[0]+d->qvel[1]*dir[1]+d->qvel[2]*dir[2];
    const double force=stiffness*(dist-length)-damping*v;
    for (int i=0;i<3;++i) d->xfrc_applied[6*body+i]=force*dir[i];
  }
};

void atomic_state_write(mjModel* m, mjData* d) {
  static double next_write=0.0;
  if (!m || !d || d->time < next_write) return;
  next_write=d->time+(1.0/30.0);
  const char* dir=std::getenv("G1_SIM_RUNTIME_DIR");
  if (!dir || !*dir) return;
  const std::string target=std::string(dir)+"/native_state";
  const std::string tmp=target+".tmp";
  std::ofstream out(tmp,std::ios::trunc);
  if (!out) return;
  out.precision(10); out<<d->time<<" "<<m->nq;
  for (int i=0;i<m->nq;++i) out<<" "<<d->qpos[i];
  out<<"\n"; out.close(); std::rename(tmp.c_str(),target.c_str());
}

void poll_runtime(mjModel* m, mjData* d, ElasticBand& band) {
  static unsigned long reset_seq=0, hanger_seq=0;
  const char* dir=std::getenv("G1_SIM_RUNTIME_DIR");
  if (!dir || !*dir) return;
  {
    std::ifstream in(std::string(dir)+"/web_runtime"); unsigned long seq=0; std::string action;
    if ((in>>seq>>action) && seq!=reset_seq) { reset_seq=seq; if (action=="reset") { mj_resetData(m,d); mj_forward(m,d); } }
  }
  {
    std::ifstream in(std::string(dir)+"/web_hanger"); unsigned long seq=0; std::string action;
    if ((in>>seq>>action) && seq!=hanger_seq) {
      hanger_seq=seq;
      if (action=="attach") band.attach(m,d);
      else if (action=="release") band.release(m,d);
      else if (action=="raise" && band.enabled) band.point[2]+=0.10;
      else if (action=="lower" && band.enabled) band.point[2]=std::max(d->qpos[2]+0.05,band.point[2]-0.10);
    }
  }
}

void stop_handler(int) { keep_running.store(false); }
}

int main(int argc,char** argv) {
  std::signal(SIGINT,stop_handler); std::signal(SIGTERM,stop_handler);
  const auto simulate_dir=executable_dir().parent_path();
  param::config.load_from_yaml((simulate_dir/"config.yaml").string());
  param::helper(argc,argv);
  if (param::config.robot_scene.is_relative()) param::config.robot_scene=simulate_dir.parent_path()/param::config.robot_scene;

  char error[1024]{};
  mjModel* m=mj_loadXML(param::config.robot_scene.c_str(),nullptr,error,sizeof(error));
  if (!m) { std::cerr<<"Failed to load MuJoCo model: "<<error<<std::endl; return 2; }
  mjData* d=mj_makeData(m);
  if (!d) { mj_deleteModel(m); return 3; }
  mj_forward(m,d);

  unitree::robot::ChannelFactory::Instance()->Init(param::config.domain_id,param::config.interface);
  const int body_id=std::max(0,mj_name2id(m,mjOBJ_BODY,"torso_link")>=0?mj_name2id(m,mjOBJ_BODY,"torso_link"):mj_name2id(m,mjOBJ_BODY,"base_link"));
  param::config.band_attached_link=6*body_id;
  std::unique_ptr<UnitreeSDK2BridgeBase> bridge;
  if (m->nu>NUM_MOTOR_IDL_GO) bridge=std::make_unique<G1Bridge>(m,d); else bridge=std::make_unique<Go2Bridge>(m,d);
  bridge->start();

  ElasticBand band; // starts released; browser Attach enables support
  auto next=std::chrono::steady_clock::now();
  while (keep_running.load()) {
    poll_runtime(m,d,band);
    if (band.enabled) band.apply(m,d);
    mj_step(m,d);
    atomic_state_write(m,d);
    next += std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(m->opt.timestep));
    std::this_thread::sleep_until(next);
  }
  bridge.reset();
  mj_deleteData(d); mj_deleteModel(m); return 0;
}
'''
headless.write_text(headless_source)

c=cmake.read_text()
begin='# === ROBOT WEB LAB HEADLESS TARGET BEGIN ==='
if begin not in c:
    c += r'''

# === ROBOT WEB LAB HEADLESS TARGET BEGIN ===
add_executable(rwl_mujoco_headless
  src/rwl_headless_main.cc
  src/joystick/joystick.cc
)
target_include_directories(rwl_mujoco_headless PRIVATE
  mujoco/include
  src/lodepng
)
target_link_libraries(rwl_mujoco_headless PRIVATE
  pthread
  mujoco
  yaml-cpp
  unitree_sdk2
  boost_program_options
  fmt
)
# === ROBOT WEB LAB HEADLESS TARGET END ===
'''
cmake.write_text(c)

# LL-only robot packs must never require a physical gamepad. If the G1 virtual
# keyboard patch is already present, it owns this setting instead.
physics=root/'simulate/src/physics_joystick.h'; cfg=root/'simulate/config.yaml'
if physics.is_file() and cfg.is_file() and 'class KeyboardJoystick' not in physics.read_text():
    c=cfg.read_text(); c,n=re.subn(r'use_joystick:\s*[01][^\n]*','use_joystick: 0 # LL/browser build: no physical gamepad required',c,count=1)
    if n!=1: raise SystemExit('simulate/config.yaml use_joystick entry changed')
    cfg.write_text(c)
print('Robot Web Lab headless/state bridge ready:', headless)
