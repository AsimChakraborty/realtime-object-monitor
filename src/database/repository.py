from __future__ import annotations

from abc import ABC, abstractmethod

from core.production.events import ProductionEvent


class EventRepository(ABC):
    """
    Persistence boundary for production events.

    Implementations decide WHERE events are stored (CSV, SQL, etc.) and HOW
    they are read back. Core logic only depends on this interface.
    """

    @abstractmethod
    def ensure_initialized(self) -> None:
        """Create any required directories/files/objects on first use."""
        raise NotImplementedError

    @abstractmethod
    def append_event(self, event: ProductionEvent) -> None:
        """Append a single production event to the store."""
        raise NotImplementedError

    @abstractmethod
    def read_events(self, as_dataframe: bool = True):
        """
        Read all production events.

        Args:
            as_dataframe: When True, return a pandas DataFrame (for the
                dashboard). Otherwise return a list of ProductionEvent.

        Returns:
            Events in the requested representation.
        """
        raise NotImplementedError


class StatusRepository(ABC):
    """
    Persistence boundary for runtime camera/system status (heartbeat).
    """

    @abstractmethod
    def read_status(self) -> dict:
        """Read the current status payload (dict)."""
        raise NotImplementedError

    @abstractmethod
    def write_status(self, payload: dict) -> None:
        """Persist a complete status payload (already merged + summarized)."""
        raise NotImplementedError