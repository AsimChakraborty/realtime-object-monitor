
from __future__ import annotations

from functools import lru_cache

from database.connection import DatabaseConnection
from database.repository import EventRepository, StatusRepository


@lru_cache(maxsize=1)
def get_database_connection() -> DatabaseConnection:
    """Return the process-wide database connection (cached)."""
    return DatabaseConnection.from_settings()


@lru_cache(maxsize=1)
def get_event_repository() -> EventRepository:
    """Return the shared event repository (cached)."""
    repo = get_database_connection().event_repository()
    repo.ensure_initialized()
    return repo


@lru_cache(maxsize=1)
def get_status_repository() -> StatusRepository:
    """Return the shared status repository (cached)."""
    return get_database_connection().status_repository()
