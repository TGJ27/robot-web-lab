import asyncio

import pytest

from backend.runtime import MockRuntimeAdapter, InvalidTransition, EventHub


def test_runtime_starts_high_passive_and_switches_to_low_only_from_passive():
    runtime = MockRuntimeAdapter("unitree_g1")
    assert runtime.snapshot().control_owner == "high"
    assert runtime.snapshot().fsm_mode == "Passive"

    runtime.set_fsm_mode("FixStand")
    with pytest.raises(InvalidTransition):
        runtime.enter_low_level()

    runtime.set_fsm_mode("Passive")
    runtime.enter_low_level()
    assert runtime.snapshot().control_owner == "low"
    assert runtime.snapshot().fsm_mode == "LL Debug"

    runtime.return_to_passive()
    assert runtime.snapshot().control_owner == "high"
    assert runtime.snapshot().fsm_mode == "Passive"


def test_runtime_velocity_and_hanger_commands_update_snapshot():
    runtime = MockRuntimeAdapter("unitree_g1")
    runtime.set_fsm_mode("FixStand")
    runtime.set_fsm_mode("Velocity")
    runtime.set_velocity(0.25, -0.1, 0.3)
    runtime.hanger("attach")
    runtime.hanger("raise")
    state = runtime.snapshot()
    assert state.velocity == {"vx": 0.25, "vy": -0.1, "yaw": 0.3}
    assert state.hanger.attached is True
    assert state.hanger.height == pytest.approx(0.1)


def test_runtime_rejects_invalid_fsm_sequence():
    runtime = MockRuntimeAdapter("unitree_g1")
    with pytest.raises(InvalidTransition):
        runtime.set_fsm_mode("Velocity")
    with pytest.raises(InvalidTransition):
        runtime.set_fsm_mode("Mimic")


def test_event_hub_publish_subscribe():
    async def scenario():
        hub = EventHub()
        queue = hub.subscribe()
        await hub.publish({"type": "test", "value": 3})
        assert await asyncio.wait_for(queue.get(), timeout=0.2) == {"type": "test", "value": 3}
        hub.unsubscribe(queue)
        assert hub.subscriber_count == 0
    asyncio.run(scenario())
