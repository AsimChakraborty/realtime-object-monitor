from __future__ import annotations

from dataclasses import dataclass


# Column order shared by the CSV store and the dashboard.
CSV_HEADERS = [
    "Timestamp",
    "Line ID",
    "Camera ID",
    "Detection ID",
    "Direction",
    "BagNo",
    "Shift",
    "Production Batch",
]


@dataclass(frozen=True)
class ProductionEvent:
    """A single production event recorded when a tracked bag crosses the line."""

    timestamp: str
    line_id: str
    camera_id: str
    detection_id: int
    direction: str
    bag_no: int
    shift: str
    production_batch: str

    def to_csv_row(self) -> list:
        """Serialize this event into a CSV row matching :data:`CSV_HEADERS`."""
        return [
            self.timestamp,
            self.line_id,
            self.camera_id,
            self.detection_id,
            self.direction,
            self.bag_no,
            self.shift,
            self.production_batch,
        ]