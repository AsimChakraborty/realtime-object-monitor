from __future__ import annotations

import threading
from datetime import datetime

from database.repository import StatusRepository


class StatusService:
    """
    Orchestrates status/heartbeat persistence.

    Builds the fully merged per-camera status plus a global summary and hands
    the completed payload to a :class:`StatusRepository` for storage. The lock
    guards the read-modify-write, while the repository's own lock makes the
    actual file write atomic.
    """

    def __init__(self, repository: StatusRepository):
        self._repository = repository
        self._lock = threading.Lock()

    def write_status(
        self,
        camera_id: str,
        line_id: str,
        online: bool,
        current_count: int,
        fps: float = 0.0,
        message: str = "",
        total_detections: int = 0,
        production_count: int = 0,
        last_detection: str = "",
    ) -> None:
        with self._lock:
            status = self._repository.read_status()
            status.setdefault("cameras", {})

            heartbeat = datetime.now().isoformat(timespec="seconds")

            status["cameras"][camera_id] = {
                "camera_id": camera_id,
                "line_id": line_id,
                "online": online,
                "current_count": current_count,
                "production_count": production_count,
                "total_detections": total_detections,
                "fps": round(fps, 1),
                "message": message,
                "last_detection": last_detection,
                "timestamp": heartbeat,
                "last_heartbeat": heartbeat,
            }

            cameras = status["cameras"]

            status["summary"] = {
                "total_cameras": len(cameras),
                "online_cameras": sum(
                    1 for x in cameras.values() if x.get("online", False)
                ),
                "total_active_bags": sum(
                    x.get("current_count", 0) for x in cameras.values()
                ),
                "total_production_count": sum(
                    x.get("production_count", 0) for x in cameras.values()
                ),
                "last_update": heartbeat,
            }

            self._repository.write_status(status)

    def read_status(self) -> dict:
        return self._repository.read_status()