import logging
import threading
import time

import pygame

from gcs.config_manager import ConfigManager
from gcs.events import Event, EventBus

logger = logging.getLogger("gcs.input")


def apply_deadzone(value: float, deadzone: float) -> float:
    """Zero out small stick drift and smoothly rescale remaining range to [-1.0, 1.0]."""
    dz = max(0.0, min(deadzone, 0.99))
    if abs(value) < dz:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    scaled = (abs(value) - dz) / (1.0 - dz)
    return max(-1.0, min(1.0, sign * scaled))


class InputPoller(threading.Thread):
    """Polls controller and keyboard inputs at a fixed rate in its own thread."""

    def __init__(self, config: ConfigManager, event_bus: EventBus) -> None:
        super().__init__(name="InputPollerThread", daemon=True)
        self.config = config
        self.event_bus = event_bus
        self._stop_event = threading.Event()
        self._joysticks: dict[int, pygame.joystick.JoystickType] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        pygame.init()
        pygame.joystick.init()
        self._scan_existing_joysticks()

        try:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()
                rate_hz = max(1.0, self.config.get_poll_rate_hz())
                period = 1.0 / rate_hz

                self._poll_pygame_events()

                sleep_for = period - (time.monotonic() - loop_start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                else:
                    logger.debug("Input loop overran period (%.4fs)", -sleep_for)
        finally:
            pygame.joystick.quit()
            pygame.quit()
            logger.info("Input poller stopped cleanly")

    def _scan_existing_joysticks(self) -> None:
        count = pygame.joystick.get_count()
        for idx in range(count):
            self._connect_joystick(idx)

    def _connect_joystick(self, index: int) -> None:
        try:
            joy = pygame.joystick.Joystick(index)
            joy.init()
            joy_id = joy.get_instance_id()
            name = joy.get_name()
            self._joysticks[joy_id] = joy
            logger.info("Controller connected: id=%s name='%s'", joy_id, name)
            self.config.apply_profile_for_device(name)
            self.event_bus.publish(
                Event(name="input.device_connected", payload={"id": joy_id, "name": name})
            )
        except pygame.error as exc:
            logger.warning("Failed to initialize joystick index %s: %s", index, exc)

    def _disconnect_joystick(self, instance_id: int) -> None:
        joy = self._joysticks.pop(instance_id, None)
        name = joy.get_name() if joy else f"id={instance_id}"
        logger.warning("Controller disconnected: %s (id=%s)", name, instance_id)
        self.event_bus.publish(
            Event(name="input.device_disconnected", payload={"id": instance_id, "name": name})
        )

    def _poll_pygame_events(self) -> None:
        profile = self.config.get_profile()
        axis_map: dict[str, str] = profile.get("axes", {})
        button_map: dict[str, str] = profile.get("buttons", {})
        key_map: dict[str, str] = profile.get("keys", {})
        deadzone = self.config.get_deadzone()

        try:
            events = pygame.event.get()
        except pygame.error as exc:
            logger.warning("Pygame event poll error (possible hotplug): %s", exc)
            return

        for ev in events:
            if ev.type == pygame.JOYDEVICEADDED:
                self._connect_joystick(ev.device_index)

            elif ev.type == pygame.JOYDEVICEREMOVED:
                self._disconnect_joystick(ev.instance_id)

            elif ev.type == pygame.JOYAXISMOTION:
                action = axis_map.get(str(ev.axis), f"axis_{ev.axis}")
                clean_val = apply_deadzone(float(ev.value), deadzone)
                self.event_bus.publish(
                    Event(
                        name="input.axis",
                        payload={
                            "device_id": ev.instance_id,
                            "axis": ev.axis,
                            "action": action,
                            "value": clean_val,
                        },
                    )
                )

            elif ev.type == pygame.JOYBUTTONDOWN or ev.type == pygame.JOYBUTTONUP:
                pressed = ev.type == pygame.JOYBUTTONDOWN
                action = button_map.get(str(ev.button), f"button_{ev.button}")
                self.event_bus.publish(
                    Event(
                        name="input.button",
                        payload={
                            "device_id": ev.instance_id,
                            "button": ev.button,
                            "action": action,
                            "pressed": pressed,
                        },
                    )
                )

            elif ev.type == pygame.JOYHATMOTION:
                self.event_bus.publish(
                    Event(
                        name="input.hat",
                        payload={
                            "device_id": ev.instance_id,
                            "hat": ev.hat,
                            "value": ev.value,  # (x, y) tuple
                        },
                    )
                )

            elif ev.type == pygame.KEYDOWN or ev.type == pygame.KEYUP:
                key_name = pygame.key.name(ev.key)
                pressed = ev.type == pygame.KEYDOWN
                action = key_map.get(key_name, f"key_{key_name}")
                self.event_bus.publish(
                    Event(
                        name="input.key",
                        payload={
                            "key": key_name,
                            "action": action,
                            "pressed": pressed,
                        },
                    )
                )
                