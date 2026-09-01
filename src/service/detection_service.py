from __future__ import annotations

import threading
import time
from typing import Optional
from core.detection.yolo_detector import YOLODetector
from core.stream.worker import CameraContext, WorkerLoggers, run_camera_worker
from database.repository import EventRepository
from service.status_service import StatusService


class DetectionService:
    """
    Application-level orchestration of the detection pipeline.

    Loads the model once, starts one worker thread per enabled camera, and
    coordinates graceful shutdown. Depends only on core modules, repositories,
    and the status service - never on the Streamlit UI.
    """

    def __init__(
        self,
        detector: YOLODetector,
        status_service: StatusService,
        event_repository: EventRepository,
        cameras: list[dict],
        loggers: Optional[WorkerLoggers] = None,
    ):
        self.detector = detector
        self.status_service = status_service
        self.event_repository = event_repository
        self.cameras = cameras
        self.loggers = loggers
        self._threads: list[threading.Thread] = []
        self._running = False

    def start(self) -> None:
        """Load the model and start a worker thread for each enabled camera."""
        self.detector.load()

        active_cameras = [c for c in self.cameras if c.get("enabled", True)]

        if not active_cameras:
            raise RuntimeError("No enabled cameras configured.")

        self._running = True

        for camera in active_cameras:
            camera_id = camera["camera_id"]
            line_id = camera["line_id"]

            self.status_service.write_status(
                camera_id=camera_id,
                line_id=line_id,
                online=False,
                current_count=0,
                message="Initializing",
            )

            ctx = CameraContext(
                camera_info=camera,
                detector=self.detector,
                status_service=self.status_service,
                event_repository=self.event_repository,
                loggers=self.loggers,
            )

            thread = threading.Thread(
                target=run_camera_worker,
                args=(ctx,),
                daemon=True,
                name=f"Camera-{camera_id}",
            )
            thread.start()
            self._threads.append(thread)

    def shutdown(self) -> None:
        """Mark all cameras offline (workers persist counts via daemon threads)."""
        self._running = False

        for camera in self.cameras:
            if not camera.get("enabled", True):
                continue
            self.status_service.write_status(
                camera_id=camera["camera_id"],
                line_id=camera["line_id"],
                online=False,
                current_count=0,
                message="Shutting down",
            )

    def run_forever(self, poll_seconds: float = 5.0) -> None:
        """Block the calling thread, keeping the pipeline alive."""
        while self._running:
            time.sleep(poll_seconds)