import logging
from pathlib import Path
import time

from gcs.config_manager import ConfigManager
from gcs.events import Event, EventBus
from gcs.input_handler import InputPoller
from gcs.logging_setup import setup_logging


def main() -> None:
    logger = setup_logging(Path("logs"), level=logging.INFO)
    logger.info("Starting ROV GCS Phase 1 (headless foundation)...")

    event_bus = EventBus()
    config = ConfigManager(Path("config"), event_bus)

    def on_any_event(event: Event) -> None:
        if event.name == "input.axis" and event.payload.get("value") == 0.0:
            return  # Keep console clean when sticks are centered
        logger.info("EVENT %-28s | %s", event.name, event.payload)

    def on_key_event(event: Event) -> None:
        if event.payload.get("pressed") and event.payload.get("action") == "reload_config":
            config.reload()

    event_bus.subscribe("*", on_any_event)
    event_bus.subscribe("input.key", on_key_event)

    poller = InputPoller(config=config, event_bus=event_bus)
    poller.start()

    try:
        while True:
            event_bus.dispatch_pending()
            time.sleep(0.01)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by operator (Ctrl+C)")
    finally:
        poller.stop()
        poller.join(timeout=2.0)
        event_bus.dispatch_pending()
        logger.info("GCS Phase 1 exited cleanly.")


if __name__ == "__main__":
    main()
    