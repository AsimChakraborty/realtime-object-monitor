from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _PROJECT_ROOT / "src"
for _path in (str(_PROJECT_ROOT), str(_SRC_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import time

from config.settings import CAMERAS, MODEL_PATH
from src.core.detection.yolo_detector import YOLODetector
from src.core.stream.worker import WorkerLoggers
from src.database.connection import DatabaseConnection
from src.service.detection_service import DetectionService
from src.service.status_service import StatusService
from src.utils.logging_setup import setup_logging


def main() -> None:
    """Run the detection / production-event pipeline."""
    loggers = setup_logging()
    app_log = loggers["app"]

    app_log.info("=" * 70)
    app_log.info("BAG DETECTION / PRODUCTION EVENT SYSTEM")
    app_log.info("=" * 70)
    app_log.info("Model: %s", MODEL_PATH)

    # Dedicated database/persistence layer.
    connection = DatabaseConnection.from_settings()
    event_repository = connection.event_repository()
    event_repository.ensure_initialized()

    status_service = StatusService(connection.status_repository())

    detector = YOLODetector(MODEL_PATH)

    service = DetectionService(
        detector=detector,
        status_service=status_service,
        event_repository=event_repository,
        cameras=CAMERAS,
        loggers=WorkerLoggers(
            app=loggers["app"],
            camera=loggers["camera"],
            detection=loggers["detection"],
        ),
    )

    try:
        service.start()
        app_log.info("All cameras started. Press Ctrl+C to stop.")
        service.run_forever()
    except KeyboardInterrupt:
        app_log.info("Stopping...")
        service.shutdown()
        app_log.info("Shutdown complete.")


if __name__ == "__main__":
    main()