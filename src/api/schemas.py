
from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

API_V1_PREFIX = "/api/v1"


# ============================================================
# Response envelope
# ============================================================

class ErrorDetail(BaseModel):
    """Machine-readable error information."""

    code: str = Field(..., examples=["NOT_FOUND"], description="Stable error code.")
    message: str = Field(..., description="Human-readable error description.")


class ApiResponse(BaseModel, Generic[T]):
    """Consistent JSON envelope for every endpoint response."""

    success: bool = Field(True, description="Whether the request succeeded.")
    data: T | None = Field(None, description="Payload on success.")
    error: ErrorDetail | None = Field(None, description="Error details on failure.")


# ============================================================
# Production events
# ============================================================

class ProductionEventSchema(BaseModel):
    """A single production event (bag crossing the counting line)."""

    timestamp: str = Field(
        ...,
        min_length=1,
        examples=["2026-09-01T12:34:56"],
        description="ISO-8601 timestamp of the detection.",
    )
    line_id: str = Field(..., min_length=1, examples=["LINE-01"])
    camera_id: str = Field(..., min_length=1, examples=["CAM-01"])
    detection_id: int = Field(..., ge=0, description="Tracker ID of the bag.")
    direction: Literal["UP", "DOWN"] = Field(..., description="Crossing direction.")
    bag_no: int = Field(..., ge=0, description="Sequential bag number.")
    shift: str = Field(..., min_length=1, examples=["SHIFT-A"])
    production_batch: str = Field(..., min_length=1, examples=["BATCH-20260901-001"])

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "timestamp": "2026-09-01T12:34:56",
            "line_id": "LINE-01",
            "camera_id": "CAM-01",
            "detection_id": 7,
            "direction": "DOWN",
            "bag_no": 42,
            "shift": "SHIFT-A",
            "production_batch": "BATCH-20260901-001",
        }
    })


class EventListResponse(BaseModel):
    """Paginated list of production events."""

    events: list[ProductionEventSchema] = Field(default_factory=list)
    total: int = Field(..., ge=0, description="Total matching events before pagination.")
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


# ============================================================
# Status
# ============================================================

class CameraStatusSchema(BaseModel):
    """Runtime heartbeat status of a single camera."""

    model_config = ConfigDict(extra="allow")

    camera_id: str = ""
    line_id: str = ""
    online: bool = False
    current_count: int = 0
    production_count: int = 0
    total_detections: int = 0
    fps: float = 0.0
    message: str = ""
    last_detection: str = ""
    timestamp: str = ""
    last_heartbeat: str = ""


class SystemStatusSchema(BaseModel):
    """Merged per-camera status plus the global summary."""

    cameras: dict[str, CameraStatusSchema] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Reports
# ============================================================

class ReportSummarySchema(BaseModel):
    """Aggregate production metrics for a reporting period."""

    period: Literal["today", "week", "month", "all"]
    total_events: int = Field(..., ge=0)
    up_count: int = Field(..., ge=0)
    down_count: int = Field(..., ge=0)
    unique_bags: int = Field(..., ge=0)
    by_shift: dict[str, int] = Field(default_factory=dict)
    by_camera: dict[str, int] = Field(default_factory=dict)


# ============================================================
# Health / meta
# ============================================================

class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: Literal["ok"] = "ok"
    version: str = Field(..., description="API version.")
    time: str = Field(..., description="Current server time (ISO-8601).")


class CameraInfoSchema(BaseModel):
    """Public (non-secret) view of a configured camera."""

    camera_id: str
    line_id: str
    enabled: bool
