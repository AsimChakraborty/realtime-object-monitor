from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config.settings import CSV_PATH, DATABASE_URL, EVENT_REPOSITORY, STATUS_PATH
from database.repository import EventRepository, StatusRepository


@dataclass(frozen=True)
class DatabaseSettings:
    """
    Configuration describing which persistence backend to use.

    Today only the ``csv`` backend exists. Keeping this as a settings object
    means a future backend (e.g. PostgreSQL) can be selected by changing
    ``backend``/``database_url`` without touching core or service code.
    """

    backend: str = EVENT_REPOSITORY
    csv_path: Path = CSV_PATH
    status_path: Path = STATUS_PATH
    database_url: str = DATABASE_URL


class DatabaseConnection:
    """
    The application's single entry point to persistence.

    A connection owns the concrete store and exposes factory methods for the
    two repository interfaces. This is the "visible, dedicated database module"
    boundary: swap backends here and the rest of the app is unchanged.
    """

    def __init__(self, settings: DatabaseSettings | None = None):
        self.settings = settings or DatabaseSettings()
        self._event_repo: EventRepository | None = None
        self._status_repo: StatusRepository | None = None

    def _build_repository(self):
        """Return a concrete backend implementation for the configured backend."""
        backend = self.settings.backend
        from database.csv_repository import CsvRepository

        if backend == "csv":
            return CsvRepository(
                csv_path=self.settings.csv_path,
                status_path=self.settings.status_path,
            )

        raise ValueError(f"Unsupported EVENT_REPOSITORY backend: {backend!r}")

    def event_repository(self) -> EventRepository:
        if self._event_repo is None:
            self._event_repo = self._build_repository()
        return self._event_repo

    def status_repository(self) -> StatusRepository:
        if self._status_repo is None:
            repo = self._build_repository()
            self._event_repo = self._event_repo or repo
            self._status_repo = repo
        return self._status_repo

    @classmethod
    def from_settings(cls, settings: DatabaseSettings | None = None) -> "DatabaseConnection":
        return cls(settings=settings or DatabaseSettings())