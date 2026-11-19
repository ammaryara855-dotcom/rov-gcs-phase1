from gcs.events import Event, EventBus
from gcs.input_handler import apply_deadzone


def test_deadzone_zeros_small_values():
    assert apply_deadzone(0.05, 0.15) == 0.0
    assert apply_deadzone(-0.14, 0.15) == 0.0


def test_deadzone_scales_outside_range():
    assert apply_deadzone(0.15, 0.15) == 0.0
    assert abs(apply_deadzone(1.0, 0.10) - 1.0) < 1e-6
    assert abs(apply_deadzone(-0.55, 0.10) - (-0.5)) < 1e-6


def test_event_bus_delivers_to_subscriber():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("test.event", received.append)

    bus.publish(Event(name="test.event", payload={"x": 42}))
    count = bus.dispatch_pending()

    assert count == 1
    assert len(received) == 1
    assert received[0].payload["x"] == 42