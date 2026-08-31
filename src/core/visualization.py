from __future__ import annotations

from pathlib import Path

import cv2


def draw_detection(frame, box, track_id, confidence):
    """Draw a bounding box, center point, and label for a single detection."""
    x1, y1, x2, y2 = map(int, box)

    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    # cx = int((x1 + x2) / 2)
    # cy = int((y1 + y2) / 2)
    # cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)

    label = f"Detection ID: {track_id} | {confidence:.2f}"
    cv2.putText(
        frame,
        label,
        (x1, max(y1 - 10, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 0),
        2,
    )


def draw_overlay(frame, line_y, camera_id, line_id, production_count):
    """Draw the production line and info panel overlay on the frame."""
    height, width = frame.shape[:2]

    cv2.line(frame, (0, line_y), (width, line_y), (0, 0, 255), 3)
    cv2.putText(
        frame,
        "PRODUCTION LINE",
        (20, max(line_y - 10, 25)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 255),
        2,
    )

    cv2.rectangle(frame, (10, 10), (390, 105), (0, 0, 0), -1)

    cv2.putText(
        frame,
        f"Camera: {camera_id}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2,
    )

    cv2.putText(
        frame,
        f"Line: {line_id}",
        (20, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2,
    )

    cv2.putText(
        frame,
        f"Production: {production_count}",
        (20, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 0),
        2,
    )


def save_live_frame(frame, path: Path):
    """Atomically write the latest annotated frame to ``path``."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.jpg")
        if cv2.imwrite(str(tmp), frame):
            tmp.replace(path)
    except Exception:
        # A failed live-frame write should never crash the worker.
        pass