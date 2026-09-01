from __future__ import annotations

import logging
from typing import Optional

import cv2


def open_capture(url: str) -> Optional[cv2.VideoCapture]:
    """
    Open an RTSP/stream capture handle with a small buffer for low latency.

    Args:
        url: RTSP URL (or local video path).

    Returns:
        A ``cv2.VideoCapture`` instance, or ``None`` if opening failed.
    """
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        return cap
    except Exception as exc:
        logging.warning("Failed to open capture %s: %s", url, exc)
        return None