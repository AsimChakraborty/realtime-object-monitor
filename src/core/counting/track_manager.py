from __future__ import annotations

import time
from datetime import datetime
from typing import Callable, Optional

from config.settings import TRACK_TIMEOUT as DEFAULT_TRACK_TIMEOUT
from core.production.events import ProductionEvent
from core.production.shifts import get_current_shift

# Callable that receives a produced event (no return value expected).
ProductionSink = Callable[[ProductionEvent], None]


class TrackManager:
    """
    ByteTrack state + production-event generation.

    Detection ID is the ByteTrack track ID.
    BagNo is an independent per-camera production sequence number.

    A production event is generated ONCE when a tracked bag's center crosses
    the configured production line. The manager is persistence-agnostic: it
    emits :class:`ProductionEvent` objects through an injected ``production_sink``
    callable (usually wired to the event repository + logging in the service layer).
    """

    def __init__(
        self,
        line_id: str,
        camera_id: str,
        line_y: int,
        bag_start_number: int,
        production_batch: str,
        production_sink: Optional[ProductionSink] = None,
        shift_fn: Callable[[Optional[datetime]], str] = get_current_shift,
        track_timeout: float = DEFAULT_TRACK_TIMEOUT,
    ):
        self.line_id = line_id
        self.camera_id = camera_id
        self.line_y = line_y
        self.next_bag_no = bag_start_number
        self.production_batch = production_batch
        self._production_sink = production_sink
        self._shift_fn = shift_fn
        self._track_timeout = track_timeout

        self.active_tracks = {}
        self.previous_positions = {}
        self.counted_ids = set()

        self.production_count = 0
        self.total_detections = 0
        self.completed_tracks = 0

    def get_direction(self, previous_y: float, current_y: float) -> Optional[str]:
        """Return 'DOWN'/'UP' when the track crosses the line, else None."""
        if previous_y < self.line_y <= current_y:
            return "DOWN"

        if previous_y > self.line_y >= current_y:
            return "UP"

        return None

    def update(self, detections: list[dict], current_time: float) -> int:
        """
        Incorporate the latest frame's detections.

        Args:
            detections: Normalized detections (each with ``track_id``,
                ``confidence``, ``center_y``).
            current_time: Timestamp (seconds) for tracking/lost-track logic.

        Returns:
            Number of currently active tracks.
        """
        now = datetime.now()
        seen_ids = set()

        for detection in detections:
            tid = int(detection["track_id"])
            conf = float(detection["confidence"])
            center_y = float(detection["center_y"])

            seen_ids.add(tid)

            if tid not in self.active_tracks:
                self.active_tracks[tid] = {
                    "start_time": now,
                    "last_seen": current_time,
                    "confidence_sum": conf,
                    "confidence_count": 1,
                }
                self.total_detections += 1
            else:
                info = self.active_tracks[tid]
                info["last_seen"] = current_time
                info["confidence_sum"] += conf
                info["confidence_count"] += 1

            previous_y = self.previous_positions.get(tid)

            if previous_y is not None:
                direction = self.get_direction(previous_y, center_y)

                if direction is not None and tid not in self.counted_ids:
                    self._record_production(now, tid, direction)

            self.previous_positions[tid] = center_y

        # Drop tracks that have not been seen for longer than the timeout.
        lost_ids = [
            tid
            for tid, info in list(self.active_tracks.items())
            if tid not in seen_ids
            and current_time - info["last_seen"] > self._track_timeout
        ]

        for tid in lost_ids:
            self.active_tracks.pop(tid, None)
            self.previous_positions.pop(tid, None)
            self.completed_tracks += 1

        return len(self.active_tracks)

    def _record_production(self, now: datetime, tid: int, direction: str) -> None:
        self.counted_ids.add(tid)

        bag_no = self.next_bag_no
        self.next_bag_no += 1
        self.production_count += 1

        event = ProductionEvent(
            timestamp=now.isoformat(timespec="seconds"),
            line_id=self.line_id,
            camera_id=self.camera_id,
            detection_id=tid,
            direction=direction,
            bag_no=bag_no,
            shift=self._shift_fn(now),
            production_batch=self.production_batch,
        )

        if self._production_sink is not None:
            self._production_sink(event)

    def get_stats(self) -> dict:
        return {
            "active_tracks": len(self.active_tracks),
            "completed_tracks": self.completed_tracks,
            "total_detections": self.total_detections,
            "production_count": self.production_count,
            "next_bag_no": self.next_bag_no,
        }