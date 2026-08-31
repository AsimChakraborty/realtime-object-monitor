from __future__ import annotations

import csv
import json
import threading
from pathlib import Path

import pandas as pd

from config.settings import CSV_PATH, STATUS_PATH
from core.production.events import CSV_HEADERS, ProductionEvent
from database.repository import EventRepository, StatusRepository


def _empty_events_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CSV_HEADERS)


class CsvRepository(EventRepository, StatusRepository):
    """
    Default file-backed persistence.

    Production events are stored as CSV and status as JSON. Writes are
    thread-safe (locks) and atomic (temp-file + rename) so concurrent camera
    workers cannot corrupt the files. This is the primary store today; swap it
    for a real database by implementing the repository interfaces instead.
    """

    def __init__(
        self,
        csv_path: str | Path = CSV_PATH,
        status_path: str | Path = STATUS_PATH,
    ):
        self.csv_path = Path(csv_path)
        self.status_path = Path(status_path)
        self._csv_lock = threading.Lock()
        self._status_lock = threading.Lock()

    # ------------------------------------------------------------
    # EventRepository
    # ------------------------------------------------------------
    def ensure_initialized(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(CSV_HEADERS)

    def append_event(self, event: ProductionEvent) -> None:
        self.ensure_initialized()

        with self._csv_lock:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(event.to_csv_row())

    def read_events(self, as_dataframe: bool = True):
        if not self.csv_path.exists():
            return _empty_events_df() if as_dataframe else []

        df = pd.read_csv(self.csv_path)

        for col in CSV_HEADERS:
            if col not in df.columns:
                df[col] = None

        if as_dataframe:
            return df

        events: list[ProductionEvent] = []
        for _, row in df.iterrows():
            events.append(
                ProductionEvent(
                    timestamp=str(row.get("Timestamp", "")),
                    line_id=str(row.get("Line ID", "")),
                    camera_id=str(row.get("Camera ID", "")),
                    detection_id=int(row.get("Detection ID", 0) or 0),
                    direction=str(row.get("Direction", "")),
                    bag_no=int(row.get("BagNo", 0) or 0),
                    shift=str(row.get("Shift", "")),
                    production_batch=str(row.get("Production Batch", "")),
                )
            )
        return events

    # ------------------------------------------------------------
    # StatusRepository
    # ------------------------------------------------------------
    def read_status(self) -> dict:
        default = {"cameras": {}, "summary": {}}

        if not self.status_path.exists():
            return default

        try:
            with open(self.status_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def write_status(self, payload: dict) -> None:
        with self._status_lock:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.status_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp.replace(self.status_path)