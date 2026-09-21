from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any


class InvalidTransition(RuntimeError):
    pass


@dataclass
class HangerState:
    attached: bool = False
    height: float = 0.0


@dataclass
class RuntimeState:
    robot_id: str | None
    control_owner: str = "none"
    fsm_mode: str = "Unavailable"
    velocity: dict[str, float] = field(default_factory=lambda: {"vx": 0.0, "vy": 0.0, "yaw": 0.0})
    hanger: HangerState = field(default_factory=HangerState)
    connected: bool = False
    sim_time: float = 0.0
    rpy: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    gyro: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    joint_positions: list[float] = field(default_factory=list)
    joint_velocities: list[float] = field(default_factory=list)
    policy_hz: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=128); self._subscribers.add(queue); return queue
    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
    async def publish(self, event: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                try: queue.get_nowait()
                except asyncio.QueueEmpty: pass
            await queue.put(event)


class MockRuntimeAdapter:
    _allowed_high_transitions = {
        "Passive": {"FixStand"}, "FixStand": {"Passive", "Velocity"},
        "Velocity": {"Passive", "Mimic"}, "Mimic": {"Passive", "Velocity"},
    }
    def __init__(self, robot_id: str | None, joint_count: int = 0):
        if robot_id is None:
            self.state = RuntimeState(robot_id=None)
        else:
            self.state = RuntimeState(robot_id=robot_id, control_owner="high", fsm_mode="Passive", connected=False,
                                      joint_positions=[0.0]*joint_count, joint_velocities=[0.0]*joint_count, policy_hz=50.0)
    def snapshot(self) -> RuntimeState:
        s=self.state
        return RuntimeState(s.robot_id,s.control_owner,s.fsm_mode,dict(s.velocity),HangerState(s.hanger.attached,s.hanger.height),s.connected,s.sim_time,list(s.rpy),list(s.gyro),list(s.joint_positions),list(s.joint_velocities),s.policy_hz)
    def set_robot(self, robot_id: str | None, joint_count: int | None = None) -> None:
        self.__init__(robot_id, joint_count or 0)
    def set_connected(self, connected: bool) -> None:
        self.state.connected = bool(connected)
    def _require_robot(self) -> None:
        if self.state.robot_id is None: raise InvalidTransition("Build and select a robot first")
    def set_fsm_mode(self, mode: str) -> None:
        self._require_robot()
        if self.state.control_owner != "high":
            if mode == "Passive": self.return_to_passive(); return
            raise InvalidTransition("High-level FSM is unavailable while LL Debug owns control")
        if mode == self.state.fsm_mode: return
        if mode not in self._allowed_high_transitions.get(self.state.fsm_mode,set()):
            raise InvalidTransition(f"Cannot transition {self.state.fsm_mode} -> {mode}")
        self.state.fsm_mode=mode
        if mode != "Velocity": self.state.velocity={"vx":0.0,"vy":0.0,"yaw":0.0}
    def enter_low_level(self) -> None:
        self._require_robot()
        if self.state.control_owner != "high" or self.state.fsm_mode != "Passive":
            raise InvalidTransition("LL Debug can only be entered from High-Level Passive")
        self.state.control_owner="low"; self.state.fsm_mode="LL Debug"; self.state.velocity={"vx":0.0,"vy":0.0,"yaw":0.0}
    def return_to_passive(self) -> None:
        self._require_robot(); self.state.control_owner="high"; self.state.fsm_mode="Passive"; self.state.velocity={"vx":0.0,"vy":0.0,"yaw":0.0}
    def set_velocity(self,vx:float,vy:float,yaw:float)->None:
        self._require_robot()
        if self.state.control_owner != "high" or self.state.fsm_mode != "Velocity": raise InvalidTransition("Velocity commands require High-Level Velocity mode")
        self.state.velocity={"vx":float(vx),"vy":float(vy),"yaw":float(yaw)}
    def hanger(self,action:str)->None:
        self._require_robot()
        if action=="attach": self.state.hanger.attached=True
        elif action=="release": self.state.hanger.attached=False
        elif action=="raise": self.state.hanger.height=round(self.state.hanger.height+0.1,6)
        elif action=="lower": self.state.hanger.height=round(self.state.hanger.height-0.1,6)
        else: raise ValueError(f"Unknown hanger action: {action}")
    def reset(self)->None:
        robot=self.state.robot_id; count=len(self.state.joint_positions); self.__init__(robot,count)
