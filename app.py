from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _PROJECT_ROOT / "src"
for _path in (str(_PROJECT_ROOT), str(_SRC_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import threading

import uvicorn

from config.settings import API_HOST, API_PORT, CAMERAS, MODEL_PATH
from src.api.endpoint import app as api_app
from src.core.detection.yolo_detector import YOLODetector
from src.core.stream.worker import WorkerLoggers
from src.database.connection import DatabaseConnection
from src.service.detection_service import DetectionService
from src.service.status_service import StatusService
from src.utils.logging_setup import setup_logging


def _start_api_server(log) -> uvicorn.Server:
    """
    Start the REST API server in a daemon thread.

    Returns the uvicorn ``Server`` so the caller can request a graceful
    shutdown. If the server cannot start, the exception is logged and the
    detection pipeline keeps running.
    """
    server = uvicorn.Server(
        uvicorn.Config(
            api_app,
            host=API_HOST,
            port=API_PORT,
            log_level="info",
        )
    )

    def _serve() -> None:
        try:
            server.run()
        except Exception:  # pragma: no cover - runtime failure path
            log.exception("API server terminated unexpectedly.")

    thread = threading.Thread(
        target=_serve,
        daemon=True,
        name="api-server",
    )
    thread.start()
    return server


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

    server: uvicorn.Server | None = None

    try:
        service.start()

        server = _start_api_server(app_log)
        app_log.info(
            "API server listening on http://%s:%d (docs at /docs)",
            API_HOST,
            API_PORT,
        )
        app_log.info("All cameras started. Press Ctrl+C to stop.")
        service.run_forever()
    except KeyboardInterrupt:
        app_log.info("Stopping...")
        if server is not None:
            server.should_exit = True
        service.shutdown()
        app_log.info("Shutdown complete.")


if __name__ == "__main__":
    main()