from __future__ import annotations

from datetime import datetime, time as dt_time

from config.settings import SHIFTS


def parse_hhmm(value: str) -> dt_time:
    """Parse a 'HH:MM' string into a ``datetime.time`` object."""
    hour, minute = map(int, value.split(":"))
    return dt_time(hour, minute)


def get_current_shift(now: datetime | None = None) -> str:
    """
    Determine the current production shift for the given time.

    Args:
        now: Time to evaluate (defaults to ``datetime.now()``).

    Returns:
        Shift name (e.g. ``"SHIFT-A"``) or ``"UNKNOWN"`` if no shift matches.
    """
    now = now or datetime.now()
    current = now.time()

    for name, (start_text, end_text) in SHIFTS.items():
        start = parse_hhmm(start_text)
        end = parse_hhmm(end_text)

        if start < end:
            # Normal shift, e.g. 06:00 -> 14:00.
            if start <= current < end:
                return name
        else:
            # Overnight shift, e.g. 22:00 -> 06:00.
            if current >= start or current < end:
                return name

    return "UNKNOWN"