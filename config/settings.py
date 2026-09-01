
from __future__ import annotations

import os
import warnings
from pathlib import Path

from config.loader import load_environment


# ============================================================
# Load environment variables
# ============================================================

# Load .env before reading any environment variables.
load_environment()

BASE_DIR = Path(__file__).resolve().parent.parent

SRC_DIR = BASE_DIR / "src"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
MODELS_DIR = BASE_DIR / "model"


# ============================================================
# Helper functions
# ============================================================

def resolve_path(value: str | None, default: Path) -> Path:
    """
    Resolve a configured path.

    - Absolute paths are used as-is.
    - Relative paths are resolved relative to BASE_DIR.
    - Empty/missing values use the default path.
    """

    if not value:
        return default

    path = Path(value)

    if path.is_absolute():
        return path

    return BASE_DIR / path


# ============================================================
# Persistence / data paths
# ============================================================

MODEL_PATH = resolve_path(
    os.getenv("MODEL_PATH"),
    MODELS_DIR / "bag.pt",
)

CSV_PATH = resolve_path(
    os.getenv("CSV_PATH"),
    DATA_DIR / "production_events.csv",
)

STATUS_PATH = resolve_path(
    os.getenv("STATUS_PATH"),
    DATA_DIR / "status.json",
)

LIVE_FRAME_PATH = resolve_path(
    os.getenv("LIVE_FRAME_PATH"),
    DATA_DIR / "live_frame.jpg",
)


# ============================================================
# Database
# ============================================================

# Example:
#
# DATABASE_URL=postgresql://user:password@localhost:5432/bag_detection


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


EVENT_REPOSITORY = os.getenv(
    "EVENT_REPOSITORY",
    "csv",
).strip().lower()


# ============================================================
# Logging
# ============================================================

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
).strip().upper()

APPLICATION_LOG = LOGS_DIR / "application.log"
CAMERA_LOG = LOGS_DIR / "camera.log"
DETECTION_LOG = LOGS_DIR / "detection.log"

LOG_MAX_BYTES = int(
    os.getenv(
        "LOG_MAX_BYTES",
        str(5 * 1024 * 1024),
    )
)

LOG_BACKUP_COUNT = int(
    os.getenv(
        "LOG_BACKUP_COUNT",
        "3",
    )
)


# ============================================================
# Detection settings
# ============================================================

CONFIDENCE_THRESHOLD = float(
    os.getenv(
        "CONFIDENCE_THRESHOLD",
        "0.50",
    )
)

IOU_THRESHOLD = float(
    os.getenv(
        "IOU_THRESHOLD",
        "0.50",
    )
)

FRAME_SKIP = int(
    os.getenv(
        "FRAME_SKIP",
        "1",
    )
)

DEVICE = os.getenv(
    "DEVICE",
    "cpu",
).strip()


# ============================================================
# Tracking settings
# ============================================================

# Maximum amount of time a tracked object can remain
# inactive before it is considered lost.

TRACK_TIMEOUT = float(
    os.getenv(
        "TRACK_TIMEOUT",
        "3.0",
    )
)


# ============================================================
# Counting line
# ============================================================

# Position of the counting line as a fraction of
# frame height.
#
# 0.60 = 60% from the top of the frame.

LINE_HEIGHT_RATIO = float(
    os.getenv(
        "LINE_HEIGHT_RATIO",
        "0.60",
    )
)


# ============================================================
# RTSP / Camera settings
# ============================================================

RECONNECT_DELAY = int(
    os.getenv(
        "RECONNECT_DELAY",
        "5",
    )
)

MAX_FRAME_FAILURES = int(
    os.getenv(
        "MAX_FRAME_FAILURES",
        "30",
    )
)

HEARTBEAT_INTERVAL = int(
    os.getenv(
        "HEARTBEAT_INTERVAL",
        "2",
    )
)

OFFLINE_THRESHOLD = int(
    os.getenv(
        "OFFLINE_THRESHOLD",
        "10",
    )
)

HEARTBEAT_TIMEOUT = float(
    os.getenv(
        "HEARTBEAT_TIMEOUT",
        "5.0",
    )
)


# ============================================================
# Production settings
# ============================================================

SHIFTS = {
    "SHIFT-A": ("06:00", "14:00"),
    "SHIFT-B": ("14:00", "22:00"),
    "SHIFT-C": ("22:00", "06:00"),
}

DEFAULT_PRODUCTION_BATCH = os.getenv(
    "DEFAULT_PRODUCTION_BATCH",
    "BATCH-20260831-001",
).strip()

BAG_START_NUMBER = int(
    os.getenv(
        "BAG_START_NUMBER",
        "1",
    )
)


# ============================================================
# Camera configuration
# ============================================================

CAMERA_ID = os.getenv(
    "CAMERA_ID",
    "CAM-01",
).strip()

LINE_ID = os.getenv(
    "LINE_ID",
    "LINE-01",
).strip()

RTSP_URL = os.getenv(
    "RTSP_URL",
    "",
).strip()


CAMERAS = [
    {
        "camera_id": CAMERA_ID,
        "line_id": LINE_ID,
        "rtsp_url": RTSP_URL,
        "enabled": True,
        "reconnect_delay": RECONNECT_DELAY,
        "production_batch": DEFAULT_PRODUCTION_BATCH,
        "bag_start_number": BAG_START_NUMBER,
    },
]


# ============================================================
# Dashboard settings
# ============================================================

AUTO_REFRESH_SECONDS = int(
    os.getenv(
        "AUTO_REFRESH_SECONDS",
        "2",
    )
)

DEFAULT_CAMERA_ID = os.getenv(
    "CAMERA_ID",
    "CAM-01",
).strip()


# ============================================================
# Watchdog settings
# ============================================================

WATCHDOG_TIMEOUT = int(
    os.getenv(
        "WATCHDOG_TIMEOUT",
        "10",
    )
)

STATUS_UPDATE_INTERVAL = float(
    os.getenv(
        "STATUS_UPDATE_INTERVAL",
        "1.0",
    )
)


# ============================================================
# Runtime validation
# ============================================================

# These checks don't stop the application for optional
# configuration such as DATABASE_URL.

if not RTSP_URL:
    warnings.warn(
        "[WARNING] RTSP_URL is not configured. "
        "Camera connection will not start."
    )

if not MODEL_PATH.exists():
    warnings.warn(
        f"[WARNING] YOLO model not found: {MODEL_PATH}"
    )


# ============================================================
# Directory creation
# ============================================================

# Create runtime directories if they don't already exist.

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOGS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)